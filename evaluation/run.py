"""평가 실행.

    python -m evaluation.run              # 전부 실행
    python -m evaluation.run --report     # 저장된 결과로 표만 다시 만든다

생성 결과는 저장소별 JSON으로 남긴다. 지표를 바꿔 다시 집계할 때 LLM을
다시 부르지 않기 위해서다.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from commit_agent.agent.nodes.generate_message import generate_message_node
from commit_agent.agent.schemas import CommitAgentState
from commit_agent.change_analysis import analyze
from commit_agent.core import get_settings
from commit_agent.core.embeddings import get_embedding_model
from commit_agent.core.llm import LLMError
from commit_agent.core.project_config import ProjectConfig
from commit_agent.core.vector_store import get_store
from commit_agent.git_integration import get_commit_diff
from commit_agent.rag.services import index_commits, retrieve_commits
from evaluation import corpus, metrics

# 언어가 서로 다르고(TS·Python·Go), 규약 준수율이 높고, PR을 squash로 합쳐
# 얕은 클론에서도 사람이 쓴 커밋이 충분히 남는 저장소를 골랐다.
REPOS = [
    "vercel/ai",
    "crewAIInc/crewAI",
    "goreleaser/goreleaser",
]

PER_TYPE = 5  # 타입별 표본 수
HISTORY_LIMIT = 1200  # 커밋을 몇 개까지 훑을지
INDEX_LIMIT = 500  # 인덱싱할 커밋 수 상한
EVAL_RATIO = 0.2  # 최신 몇 할을 평가 대상으로 뗄지
RETRIEVE_LIMIT = 5

WORK = Path(__file__).parent / "work"
RESULTS = Path(__file__).parent / "results"

# 대상 저장소는 모두 영어로 커밋한다. 허용 타입은 좁히지 않는다 —
# 설정으로 알려주면 분류 과제가 쉬워져 실제 판단 능력을 재지 못한다.
PROJECT = ProjectConfig(
    language="en",
    issue_mapping=False,
    propose_issue=False,
    branch_suggest=False,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="저장된 결과로 표만 만든다")
    parser.add_argument("--repos", nargs="*", default=REPOS)
    args = parser.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    for slug in args.repos:
        if not args.report:
            run_repo(slug)

    write_report(args.repos)


def run_repo(slug: str) -> None:
    """저장소 하나를 평가하고 생성 결과를 저장한다."""
    print(f"\n=== {slug} ===", flush=True)

    repo = corpus.clone(slug, WORK, depth=HISTORY_LIMIT)
    refs = corpus.collect(repo, limit=HISTORY_LIMIT)
    print(f"  규약 준수 커밋 {len(refs)}건", flush=True)

    evaluation_pool = corpus.split_at(repo, refs, eval_ratio=EVAL_RATIO)
    sample = corpus.stratified_sample(evaluation_pool, per_type=PER_TYPE)
    print(f"  평가 대상 {len(evaluation_pool)}건 중 {len(sample)}건 추출", flush=True)

    client = _store_for(slug)
    embeddings = get_embedding_model()
    result = index_commits(
        repo, client, embeddings, limit=INDEX_LIMIT,
        on_progress=lambda done, total: print(f"\r  인덱싱 {done}/{total}", end="", flush=True),
    )
    print(f"\r  인덱싱 {result.indexed}건 완료" + " " * 20, flush=True)

    records = []
    for i, ref in enumerate(sample, 1):
        diff_text = get_commit_diff(repo, ref.sha)
        analysis = analyze(diff_text)

        hits = retrieve_commits(
            client, embeddings, analysis,
            limit=RETRIEVE_LIMIT, exclude_ids={ref.sha},
        )

        records.append(
            {
                **asdict(ref),
                "with_rag": _generate(analysis, hits),
                "without_rag": _generate(analysis, []),
                "retrieved": [h.metadata.get("message", "") for h in hits],
            }
        )
        print(f"\r  생성 {i}/{len(sample)}", end="", flush=True)

    client.close()
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{slug.replace('/', '__')}.json"
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\r  생성 {len(records)}건 → {path.name}" + " " * 20, flush=True)


def _generate(analysis, hits) -> str:
    """메시지를 만든다. 실패하면 빈 문자열로 남겨 집계에서 형식 위반으로 센다."""
    state = CommitAgentState(
        diff_text="",
        project=PROJECT,
        analysis=analysis,
        retrieved_commits=hits,
    )
    try:
        return generate_message_node(state).get("commit_message") or ""
    except LLMError as exc:
        print(f"\n  생성 실패: {exc}", file=sys.stderr, flush=True)
        return ""


def _store_for(slug: str):
    """저장소마다 별도 벡터 스토어를 쓴다. 로컬 모드는 한 프로세스만 접근 가능하다."""
    path = WORK / "stores" / slug.replace("/", "__")
    settings = get_settings().model_copy(update={"vector_store_path": str(path)})
    return get_store(settings)


# 평가를 돌리기 전에 정해 둔 기준. 결과를 보고 고치지 않는다.
CRITERIA = [
    ("타입 일치율 70% 이상", lambda w, o: w.type_match_rate >= 0.70),
    ("타입 일치율이 RAG 미적용 대비 20%p 이상 개선", lambda w, o: w.type_match_rate - o.type_match_rate >= 0.20),
    ("scope 유무 일치율 80% 이상", lambda w, o: w.scope_presence_rate >= 0.80),
    ("RAG 적용이 모든 지표에서 우위", lambda w, o: (
        w.type_match_rate > o.type_match_rate
        and w.scope_presence_rate > o.scope_presence_rate
        and w.text_similarity > o.text_similarity
    )),
]


def write_report(slugs: list[str]) -> None:
    """저장된 결과를 모아 마크다운 표로 만든다."""
    embeddings = get_embedding_model()
    lines = ["# 커밋 메시지 생성 정확도 평가", "", _method(slugs), "", "## 저장소별 결과", ""]
    overall: dict[str, list[metrics.Comparison]] = {"with": [], "without": []}

    for slug in slugs:
        path = RESULTS / f"{slug.replace('/', '__')}.json"
        if not path.exists():
            continue

        records = json.loads(path.read_text(encoding="utf-8"))
        lines += [f"### {slug}", "", metrics.HEADER_ROW]

        for arm, label in (("without_rag", "RAG 미적용"), ("with_rag", "RAG 적용")):
            comparisons = [
                metrics.compare(corpus.CommitRef(r["sha"], r["type"], r["scope"], r["subject"]), r[arm])
                for r in records
            ]
            overall["with" if arm == "with_rag" else "without"] += comparisons
            summary = metrics.summarize(
                comparisons, semantic=metrics.semantic_similarity(embeddings, comparisons)
            )
            lines.append(summary.as_row(label))

        lines += ["", _samples(records), ""]

    lines += ["## 전체", "", metrics.HEADER_ROW]
    totals = {}
    for key, label in (("without", "RAG 미적용"), ("with", "RAG 적용")):
        totals[key] = metrics.summarize(
            overall[key], semantic=metrics.semantic_similarity(embeddings, overall[key])
        )
        lines.append(totals[key].as_row(label))

    lines += ["", _verdict(totals["with"], totals["without"])]

    out = RESULTS / "report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n보고서 → {out}")


def _method(slugs: list[str]) -> str:
    """어떤 조건으로 측정했는지 남긴다. 숫자만 있으면 나중에 해석할 수 없다."""
    return "\n".join([
        "## 평가 방법",
        "",
        "계획서의 검증 방법을 따른다 — 특정 시점 이전 커밋만 인덱싱하고, 그 이후 커밋은",
        "diff만 입력해 메시지를 생성한 뒤 실제 커밋 메시지와 비교한다.",
        "",
        f"- 대상 저장소: {', '.join(slugs)}",
        f"- 커밋 수집 깊이: {HISTORY_LIMIT}건. 머지 커밋, 봇 커밋, 규약을 벗어난 커밋은 제외",
        f"- 시점 분할: 최신 {EVAL_RATIO:.0%}를 평가 대상으로 떼어내고 나머지를 인덱싱",
        f"- 인덱싱: 분할 지점 이전 최대 {INDEX_LIMIT}건. 봇 커밋도 포함(실사용과 동일)",
        f"- 표본 추출: 타입별 최대 {PER_TYPE}건. 무작위로 뽑으면 fix에 몰려 분류 능력을 재지 못함",
        f"- 검색: 유사 커밋 상위 {RETRIEVE_LIMIT}건을 프롬프트 예시로 제시. 정답 커밋은 제외",
        "- 생성: 이슈 매핑·초안 제안·브랜치 제안은 끔. 허용 타입은 좁히지 않음",
        "",
        "지표는 실제 커밋 메시지 첫 줄과 비교한다. 제목 유사도는 문자 단위(difflib),",
        "의미 유사도는 임베딩 코사인이다.",
    ])


def _verdict(with_rag, without_rag) -> str:
    """사전에 정한 기준과 대조한다."""
    lines = ["## 사전 기준 대비", "", "| 기준 | 판정 |", "| --- | --- |"]
    for label, check in CRITERIA:
        lines.append(f"| {label} | {'충족' if check(with_rag, without_rag) else '**미달**'} |")

    met = sum(1 for _, check in CRITERIA if check(with_rag, without_rag))
    lines += ["", f"{len(CRITERIA)}개 중 {met}개 충족."]
    return "\n".join(lines)


def _samples(records: list[dict], count: int = 3) -> str:
    """정성 평가용으로 생성/실제 쌍을 몇 개 보여준다."""
    lines = ["<details><summary>생성 예시</summary>", ""]
    for r in records[:count]:
        scope = f"({r['scope']})" if r["scope"] else ""
        lines += [
            f"- 실제: `{r['type']}{scope}: {r['subject']}`",
            f"  - RAG 적용: `{_first_line(r['with_rag'])}`",
            f"  - RAG 미적용: `{_first_line(r['without_rag'])}`",
        ]
    lines += ["", "</details>"]
    return "\n".join(lines)


def _first_line(message: str) -> str:
    return message.splitlines()[0] if message.strip() else "(생성 실패)"


if __name__ == "__main__":
    main()
