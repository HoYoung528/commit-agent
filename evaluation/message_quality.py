"""생성 메시지 품질 정성 평가.

제목 유사도는 사람이 쓴 메시지를 정답으로 두기 때문에, 도구가 더 설명력 있는
메시지를 써도 점수가 낮아진다. 실제로 `chore: fmt` 라고만 적힌 커밋에 대해
생성 쪽은 무엇을 왜 바꿨는지 적었는데 유사도는 낮게 나왔다. 그래서 정답 대조가
아니라 쌍대 비교로 잰다 — 같은 diff에 대해 사람이 쓴 메시지와 생성 메시지를
어느 쪽이 어느 쪽인지 알리지 않고 나란히 놓고 고르게 한다.

계획서 6) 검증의 "실제 메시지 대비 설명력 및 자연스러움을 살펴보는 정성 평가"에
해당한다.

생성과 같은 모델로 판정하므로 자기 출력을 선호하는 편향을 배제할 수 없다.
어느 쪽이 사람 것인지 알리지 않고, 순서를 뒤집어 한 번 더 재서 판정이 뒤집히는
비율을 함께 낸다. 도구가 이긴 수치는 상한으로 읽어야 한다.

    python -m evaluation.message_quality --limit 2   # 적은 건수로 먼저 확인
    python -m evaluation.message_quality             # 전체
    python -m evaluation.message_quality --flip      # 순서를 뒤집어 재측정
    python -m evaluation.message_quality --report    # 저장된 결과로 표만
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from commit_agent.agent.prompts.commit_message import strip_trailers
from commit_agent.change_analysis import analyze, change_metrics, render_patches
from commit_agent.core.llm import LLMError, get_chat_model, translate_errors
from commit_agent.git_integration import get_commit_diff
from evaluation import corpus, run

RESULT_FILE = run.RESULTS / "message_quality.json"
REPORT_FILE = run.RESULTS / "message_quality.md"

# 판정에 쓸 패치 길이 상한. 기본값(10만 자)은 생성용이라 판정에는 과하다.
# 판정자는 메시지가 변경을 맞게 설명하는지만 확인하면 되므로 더 짧아도 된다.
PATCH_LIMIT = 10_000

# 제목 끝에 붙는 PR 번호. 사람이 쓴 메시지에만 있어서 그대로 두면 판정자가
# 어느 쪽이 사람 것인지 바로 알아버린다. 블라인드가 깨지면 비교가 무의미하다.
PR_REF = re.compile(r"\s*\(#\d+\)\s*$")

Choice = Literal["A", "B", "tie"]


class Verdict(BaseModel):
    """판정 결과. 축을 나눠야 어디서 갈렸는지 보인다."""

    accuracy: Choice = Field(description="변경 내용을 사실과 다르지 않게 설명한 쪽")
    usefulness: Choice = Field(description="나중에 이 커밋을 찾는 사람에게 더 도움이 되는 쪽")
    overall: Choice = Field(description="커밋 메시지로서 더 나은 쪽")
    reason: str = Field(description="한 문장 근거")


SYSTEM_PROMPT = """\
당신은 커밋 메시지의 품질을 심사합니다.

같은 코드 변경에 대해 작성된 두 메시지 A와 B가 주어집니다. 어느 쪽이 누가 썼는지는
알려주지 않습니다. 변경 내용을 직접 읽고 판단하세요.

세 가지를 각각 고르세요. 모두 A, B, tie 중 하나입니다.

- accuracy: 변경 내용을 사실과 다르지 않게 설명한 쪽. 변경에 없는 내용을 적었거나
  변경 범위를 잘못 말한 쪽이 열등합니다. 짧다는 이유로 열등하지는 않습니다.
- usefulness: 나중에 히스토리를 훑으며 이 커밋을 찾는 사람에게 더 도움이 되는 쪽.
  무엇을 왜 바꿨는지 알 수 있어야 합니다.
- overall: 커밋 메시지로서 더 나은 쪽.

길이가 길다고 좋은 것도, 짧다고 좋은 것도 아닙니다. 변경 규모에 비해 적절한지
보세요. 판단이 어려우면 tie를 고르세요."""

USER_TEMPLATE = """\
## 변경 규모
{metrics}

## 변경 내용
{patches}

## 메시지 A
{a}

## 메시지 B
{b}"""


def clean(message: str) -> str:
    """비교에 넣기 전에 양쪽에서 같은 것을 걷어낸다.

    서명 꼬리말과 제목 끝의 PR 번호는 사람이 쓴 메시지에만 붙어 있어,
    남겨 두면 내용이 아니라 형식으로 출처가 드러난다.
    """
    lines = strip_trailers(message).splitlines()
    if not lines:
        return ""

    lines[0] = PR_REF.sub("", lines[0])
    return "\n".join(lines).strip()


def context(repo, sha: str) -> tuple[str, str]:
    """판정자에게 보여줄 변경 요약과 패치를 만든다.

    도구가 본 것과 같은 전처리를 거친다. `analyze` 는 LLM을 부르지 않으므로
    비용이 들지 않는다.
    """
    analysis = analyze(
        get_commit_diff(repo, sha),
        max_chars_per_file=PATCH_LIMIT,
        max_total_chars=PATCH_LIMIT,
    )
    return change_metrics(analysis), render_patches(analysis)


def judge(metrics: str, patches: str, a: str, b: str) -> Verdict:
    """두 메시지를 비교한다."""
    model = get_chat_model().with_structured_output(Verdict)
    with translate_errors():
        result = model.invoke([
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_TEMPLATE.format(
                    metrics=metrics or "(없음)", patches=patches or "(내용 없음)", a=a, b=b
                ),
            },
        ])

    return result if isinstance(result, Verdict) else Verdict.model_validate(result)


def evaluate(*, flip: bool, limit: int | None) -> None:
    """저장된 생성 결과를 사람이 쓴 메시지와 비교한다.

    생성은 다시 하지 않는다. 10주차 측정에서 남긴 결과를 그대로 쓰므로
    판정 호출만 비용이 든다.
    """
    records = []
    position = 0  # 전체를 통틀어 번갈아 센다

    for slug in run.REPOS:
        path = run.RESULTS / f"{slug.replace('/', '__')}.json"
        if not path.exists():
            print(f"{slug}: 생성 결과가 없습니다. run.py 를 먼저 돌리세요.", file=sys.stderr)
            continue

        repo = corpus.clone(slug, run.WORK, depth=run.HISTORY_LIMIT)
        saved = json.loads(path.read_text(encoding="utf-8"))
        if limit:
            saved = saved[:limit]

        print(f"\n=== {slug} ({len(saved)}건)", flush=True)
        for i, entry in enumerate(saved, 1):
            # 한쪽을 늘 A에 두면 위치 편향이 그대로 결과에 섞인다. 무작위로
            # 섞으면 배치가 치우칠 수 있어 번갈아 둔다. 건수가 짝수면 정확히
            # 반씩이고, `--flip` 은 같은 배치를 그대로 뒤집는다
            tool_first = position % 2 == 0
            if flip:
                tool_first = not tool_first
            position += 1

            records.append(_compare(repo, slug, entry, tool_first=tool_first))
            print(f"\r  판정 {i}/{len(saved)}", end="", flush=True)
        print()

    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n판정 {len(records)}건 → {RESULT_FILE.name}")
    report()


def _compare(repo, slug: str, entry: dict, *, tool_first: bool) -> dict:
    """한 커밋에 대해 사람 메시지와 생성 메시지를 비교한다."""
    sha = entry["sha"]
    human = clean(str(repo.commit(sha).message))
    tool = clean(entry.get("with_rag") or "")

    blank = {
        "sha": sha, "slug": slug, "tool_first": tool_first,
        "human": human, "tool": tool,
        "accuracy": None, "usefulness": None, "overall": None,
        "reason": "", "judged": False,
    }

    # 생성이 비어 있으면 비교할 것이 없다. 사람 승으로 세면 생성 실패가
    # 품질 열위로 섞이므로 집계에서 뺀다
    if not tool or not human:
        return blank

    metrics, patches = context(repo, sha)
    a, b = (tool, human) if tool_first else (human, tool)

    try:
        verdict = judge(metrics, patches, a, b)
    except LLMError as exc:
        print(f"\n  판정 실패 {sha[:8]}: {exc}", file=sys.stderr, flush=True)
        return blank

    return {
        **blank,
        # A·B를 "도구/사람"으로 되돌려 저장한다. 순서가 섞여 있어 그대로
        # 두면 집계할 수 없다
        "accuracy": _side(verdict.accuracy, tool_first),
        "usefulness": _side(verdict.usefulness, tool_first),
        "overall": _side(verdict.overall, tool_first),
        "reason": verdict.reason,
        "judged": True,
    }


def _side(choice: Choice, tool_first: bool) -> str:
    """A·B 선택을 도구·사람으로 바꾼다."""
    if choice == "tie":
        return "tie"
    picked_a = choice == "A"
    return "tool" if picked_a == tool_first else "human"


def report() -> None:
    """저장된 판정으로 표를 만든다."""
    if not RESULT_FILE.exists():
        print("판정 결과가 없습니다.", file=sys.stderr)
        return

    records = json.loads(RESULT_FILE.read_text(encoding="utf-8"))
    measured = [r for r in records if r.get("judged")]
    skipped = len(records) - len(measured)
    if not measured:
        print("집계할 판정이 없습니다.", file=sys.stderr)
        return

    lines = [
        "# 생성 메시지 품질 정성 평가",
        "",
        "같은 변경에 대해 사람이 쓴 메시지와 생성 메시지를 출처를 가린 채 비교.",
        f"판정 {len(measured)}건" + (f", 제외 {skipped}건" if skipped else "") + ".",
        "",
        "| 축 | 생성 우세 | 무승부 | 사람 우세 |",
        "| --- | --- | --- | --- |",
    ]

    for axis, label in (("accuracy", "정확성"), ("usefulness", "유용성"), ("overall", "종합")):
        counts = {side: sum(1 for r in measured if r[axis] == side) for side in ("tool", "tie", "human")}
        lines.append(
            f"| {label} "
            f"| {counts['tool']} ({_pct(counts['tool'], len(measured))}) "
            f"| {counts['tie']} ({_pct(counts['tie'], len(measured))}) "
            f"| {counts['human']} ({_pct(counts['human'], len(measured))}) |"
        )

    lines += _by_human_effort(measured) + _by_position(measured)

    lines += ["", "## 저장소별 종합", "", "| 저장소 | 생성 우세 | 무승부 | 사람 우세 |", "| --- | --- | --- | --- |"]
    for slug in run.REPOS:
        group = [r for r in measured if r["slug"] == slug]
        if not group:
            continue
        counts = {side: sum(1 for r in group if r["overall"] == side) for side in ("tool", "tie", "human")}
        lines.append(
            f"| {slug} | {counts['tool']} | {counts['tie']} | {counts['human']} |"
        )

    lines += [
        "",
        "생성과 같은 모델로 판정했으므로 자기 출력을 선호하는 편향을 배제할 수 없다.",
        "생성이 우세한 수치는 상한으로 읽어야 한다.",
    ]

    REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[4:]))
    print(f"\n보고서 → {REPORT_FILE}")


def _by_human_effort(measured: list[dict]) -> list[str]:
    """사람이 본문까지 썼는지로 나눈다.

    전체 승률만 보면 이 도구가 어디에 쓸모 있는지가 가려진다. 사람이 한 줄로
    끝낸 커밋과 본문까지 쓴 커밋은 비교의 난이도가 전혀 다르다.
    """
    lines = [
        "",
        "## 사람이 들인 공에 따라",
        "",
        "| 사람 쪽 메시지 | 건수 | 생성 우세 | 사람 우세 |",
        "| --- | --- | --- | --- |",
    ]

    for label, has_body in (("한 줄만", False), ("본문까지 씀", True)):
        group = [r for r in measured if (len(r["human"].splitlines()) > 1) == has_body]
        if not group:
            continue
        tool = sum(1 for r in group if r["overall"] == "tool")
        human = sum(1 for r in group if r["overall"] == "human")
        lines.append(
            f"| {label} | {len(group)} "
            f"| {tool} ({_pct(tool, len(group))}) "
            f"| {human} ({_pct(human, len(group))}) |"
        )

    return lines


def _by_position(measured: list[dict]) -> list[str]:
    """어느 자리에 놓였을 때 이겼는지. 위치 편향의 크기를 보여 준다."""
    picked_a = sum(1 for r in measured if (r["overall"] == "tool") == r["tool_first"])
    rows = []
    for first in (True, False):
        group = [r for r in measured if r["tool_first"] == first]
        if not group:
            continue
        tool = sum(1 for r in group if r["overall"] == "tool")
        rows.append(
            f"| 생성이 {'A' if first else 'B'}에 놓임 | {len(group)} "
            f"| {tool} ({_pct(tool, len(group))}) |"
        )

    return [
        "",
        "## 위치 편향",
        "",
        "생성·사람을 번갈아 A·B에 놓았다. 한쪽 자리에서만 이기면 내용이 아니라",
        "자리 때문에 이긴 것이다.",
        "",
        "| 배치 | 건수 | 생성 우세 |",
        "| --- | --- | --- |",
        *rows,
        "",
        f"A를 고른 비율 {picked_a}/{len(measured)} ({_pct(picked_a, len(measured))}). "
        "50%에 가까울수록 자리에 끌리지 않았다는 뜻이다.",
    ]


def _pct(part: int, total: int) -> str:
    return f"{part * 100 // total}%" if total else "-"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--flip", action="store_true", help="A·B 순서를 뒤집어 재측정")
    parser.add_argument("--limit", type=int, help="저장소별 판정 건수 상한. 확인용")
    parser.add_argument("--report", action="store_true", help="저장된 결과로 표만 만든다")
    args = parser.parse_args()

    if args.report:
        report()
        return

    evaluate(flip=args.flip, limit=args.limit)


if __name__ == "__main__":
    main()
