"""이슈 매핑 정확도 평가.

커밋 메시지에 `Fixes #123` 처럼 이슈를 명시한 커밋이 정답 자료다. 사람이
직접 연결한 것이라 해석의 여지가 없다. 그 커밋의 diff로 메시지를 만들고,
도구가 같은 이슈를 찾아내는지 본다.

후보 풀은 저장소 커밋들이 참조한 이슈 전체다. 실사용에서 열린 이슈 수백 건
중에 고르는 것과 규모가 비슷하다.

    python -m evaluation.issue_mapping --collect   # 커밋·이슈 쌍 수집
    python -m evaluation.issue_mapping             # 인덱싱 + 매핑 측정
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from commit_agent.agent.nodes.generate_message import generate_message_node
from commit_agent.agent.prompts import issue_match as prompts
from commit_agent.agent.schemas import CommitAgentState, IssueMatch
from commit_agent.change_analysis import analyze
from commit_agent.core.embeddings import get_embedding_model
from commit_agent.core.llm import LLMError, get_chat_model, translate_errors
from commit_agent.git_integration.schemas import IssueInfo
from commit_agent.rag.schemas import Collection, SearchHit
from commit_agent.rag.services import ensure_collection, retrieve_issues, upsert
from commit_agent.rag.services.issue_indexer import _to_document
from evaluation import corpus, run

SLUG = "vercel/ai"
PAIRS_FILE = run.WORK / "issue_pairs.json"
RESULT_FILE = run.RESULTS / "issue_mapping.json"

# 커밋 메시지에서 이슈를 닫는 표현. GitHub이 인정하는 키워드를 따른다
REF = re.compile(
    r"\b(?:closes|close|closed|fixes|fix|fixed|resolves|resolve|resolved)"
    r"\s*:?\s*#(\d+)",
    re.IGNORECASE,
)

SAMPLE_SIZE = 40  # 이슈를 참조한 커밋
NEGATIVE_SIZE = 20  # 참조가 없는 커밋. 오탐을 재려면 필요하다
RETRIEVE_LIMIT = 5


@dataclass(frozen=True)
class Case:
    sha: str
    subject: str
    answer: int | None  # 정답 이슈 번호. 없으면 "관련 이슈 없음"이 정답


def collect() -> None:
    """커밋에서 이슈 참조를 뽑고 해당 이슈를 받아 둔다."""
    token = (dotenv_values(".env").get("GITHUB_TOKEN") or "").strip()
    repo = corpus.clone(SLUG, run.WORK, depth=run.HISTORY_LIMIT)

    pairs = []
    for commit in repo.iter_commits(max_count=run.HISTORY_LIMIT, no_merges=True):
        matched = REF.search(str(commit.message))
        if matched:
            pairs.append({
                "sha": commit.hexsha,
                "issue": int(matched.group(1)),
                "subject": str(commit.message).splitlines()[0],
            })

    numbers = sorted({p["issue"] for p in pairs})
    issues: dict[str, dict] = {}
    for i, number in enumerate(numbers, 1):
        fetched = _fetch_issue(token, number)
        if fetched:
            issues[str(number)] = fetched
        if i % 50 == 0:
            print(f"  이슈 {i}/{len(numbers)}", flush=True)

    PAIRS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PAIRS_FILE.write_text(
        json.dumps({"pairs": pairs, "issues": issues}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"커밋-이슈 쌍 {len(pairs)}건, 이슈 {len(issues)}건 → {PAIRS_FILE.name}")


def _fetch_issue(token: str, number: int) -> dict | None:
    """이슈 하나를 받는다. PR이거나 없으면 None."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{SLUG}/issues/{number}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    try:
        data = json.load(urllib.request.urlopen(request))
    except urllib.error.HTTPError:
        return None

    if "pull_request" in data:
        return None

    return {
        "number": number,
        "title": data["title"],
        "body": (data["body"] or "")[:4000],
        "state": data["state"],
        "labels": [label["name"] for label in data["labels"]],
        "url": data["html_url"],
    }


def index_pool(client, embeddings, issues: dict[str, dict]) -> int:
    """받아 둔 이슈를 인덱싱한다.

    `index_issues` 는 GitHub에서 열린 이슈만 받아 오므로 쓸 수 없다. 평가에서는
    이미 닫힌 이슈가 정답이라 저장해 둔 것을 직접 넣는다.
    """
    documents = [
        _to_document(
            IssueInfo(
                number=i["number"], title=i["title"], body=i["body"],
                state=i["state"], labels=i["labels"], url=i["url"],
            )
        )
        for i in issues.values()
    ]

    ensure_collection(client, Collection.ISSUES, len(embeddings.embed_query("x")))
    for start in range(0, len(documents), 50):
        batch = documents[start : start + 50]
        upsert(client, Collection.ISSUES, batch, embeddings.embed_documents([d.text for d in batch]))
        print(f"\r  이슈 인덱싱 {min(start + 50, len(documents))}/{len(documents)}", end="", flush=True)

    print()
    return len(documents)


def judge(message: str, hits: list[SearchHit]) -> IssueMatch:
    """후보 중 관련 있는 이슈가 있는지 LLM에게 묻는다."""
    model = get_chat_model().with_structured_output(IssueMatch)
    with translate_errors():
        result = model.invoke([
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompts.build_user_prompt(message, hits)},
        ])

    return result if isinstance(result, IssueMatch) else IssueMatch.model_validate(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect", action="store_true", help="커밋·이슈 쌍을 수집한다")
    parser.add_argument("--rejudge", action="store_true", help="저장된 기록으로 판단만 다시 돌린다")
    args = parser.parse_args()

    if args.collect:
        collect()
        return

    if args.rejudge:
        rejudge()
        return

    data = json.loads(PAIRS_FILE.read_text(encoding="utf-8"))
    issues = data["issues"]
    cases = _build_cases(data)
    print(f"평가 대상 {len(cases)}건 (정답 있음 {sum(1 for c in cases if c.answer)}건)")

    repo = corpus.clone(SLUG, run.WORK, depth=run.HISTORY_LIMIT)
    client = run._store_for(SLUG)
    embeddings = get_embedding_model()
    print(f"  이슈 풀 {index_pool(client, embeddings, issues)}건")

    records = []
    for i, case in enumerate(cases, 1):
        records.append(_evaluate(repo, client, embeddings, case))
        print(f"\r  매핑 {i}/{len(cases)}", end="", flush=True)

    client.close()
    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\r  매핑 {len(records)}건 → {RESULT_FILE.name}" + " " * 20)
    _report(records)


def _build_cases(data: dict) -> list[Case]:
    """정답이 있는 커밋과 없는 커밋을 함께 모은다."""
    issues = data["issues"]
    positives = [
        Case(p["sha"], p["subject"], p["issue"])
        for p in data["pairs"] if str(p["issue"]) in issues
    ][:SAMPLE_SIZE]

    referenced = {p["sha"] for p in data["pairs"]}
    repo = corpus.clone(SLUG, run.WORK, depth=run.HISTORY_LIMIT)
    negatives = []
    for commit in repo.iter_commits(max_count=run.HISTORY_LIMIT, no_merges=True):
        if commit.hexsha in referenced:
            continue
        negatives.append(Case(commit.hexsha, str(commit.message).splitlines()[0], None))
        if len(negatives) >= NEGATIVE_SIZE:
            break

    return positives + negatives


def _evaluate(repo, client, embeddings, case: Case) -> dict:
    """메시지를 만들고 매핑한 결과를 기록한다."""
    from commit_agent.git_integration import get_commit_diff

    analysis = analyze(get_commit_diff(repo, case.sha))
    state = CommitAgentState(diff_text="", project=run.PROJECT, analysis=analysis)

    # 생성에 실패하면 빈 채로 둔다. 실제 커밋 제목으로 대신하면 정답을
    # 쿼리로 쓰는 셈이라 검색·매핑 수치가 통째로 부풀려진다.
    try:
        message = generate_message_node(state).get("commit_message") or ""
    except LLMError as exc:
        print(f"\n  생성 실패: {exc}", file=sys.stderr)
        return _blank(case)

    hits = retrieve_issues(client, embeddings, message, limit=RETRIEVE_LIMIT)
    candidates = [int(h.metadata["number"]) for h in hits]

    try:
        matched = judge(message, hits).issue_number if hits else None
    except LLMError as exc:
        print(f"\n  판단 실패: {exc}", file=sys.stderr)
        return {**_blank(case), "message": message, "candidates": candidates}

    return {
        "sha": case.sha, "subject": case.subject, "answer": case.answer,
        "message": message, "candidates": candidates, "matched": matched,
        "judged": True,
    }


def _blank(case: Case) -> dict:
    """측정하지 못한 기록. 집계에서 제외된다."""
    return {
        "sha": case.sha, "subject": case.subject, "answer": case.answer,
        "message": "", "candidates": [], "matched": None, "judged": False,
    }


def _report(records: list[dict]) -> None:
    # 생성이나 판단에 실패한 기록은 집계에서 뺀다. 섞으면 실패가 오답으로 세어진다
    measured = [r for r in records if r.get("judged")]
    skipped = len(records) - len(measured)
    if skipped:
        print(f"\n측정 실패 {skipped}건은 집계에서 제외", file=sys.stderr)

    positives = [r for r in measured if r["answer"]]
    negatives = [r for r in measured if not r["answer"]]
    if not positives:
        print("\n집계할 기록이 없습니다.")
        return

    recalled = sum(1 for r in positives if r["answer"] in r["candidates"])
    correct = sum(1 for r in positives if r["matched"] == r["answer"])
    picked_when_recalled = sum(
        1 for r in positives if r["answer"] in r["candidates"] and r["matched"] == r["answer"]
    )
    false_positive = sum(1 for r in negatives if r["matched"])

    print()
    print(f"정답 있는 커밋 {len(positives)}건")
    print(f"  검색 적중 (상위 {RETRIEVE_LIMIT}건에 정답 포함): {recalled}/{len(positives)} ({_pct(recalled, len(positives))})")
    print(f"  매핑 정확 (정답 이슈를 고름):              {correct}/{len(positives)} ({_pct(correct, len(positives))})")
    print(f"  검색 적중 시 판단 정확:                    {picked_when_recalled}/{recalled} ({_pct(picked_when_recalled, recalled)})")
    print()
    print(f"정답 없는 커밋 {len(negatives)}건")
    print(f"  오탐 (엉뚱한 이슈를 붙임):                 {false_positive}/{len(negatives)} ({_pct(false_positive, len(negatives))})")


def _pct(part: int, total: int) -> str:
    return f"{part * 100 // total}%" if total else "-"



def rejudge() -> None:
    """저장된 기록으로 판단 단계만 다시 돌린다.

    API 한도나 일시 오류로 판단이 비었을 때, 메시지 생성과 검색을 다시 하지
    않고 남은 것만 채운다. 비싼 단계를 두 번 치르지 않기 위한 경로다.

        python -m evaluation.issue_mapping --rejudge
    """
    records = json.loads(RESULT_FILE.read_text(encoding="utf-8"))

    repo = corpus.clone(SLUG, run.WORK, depth=run.HISTORY_LIMIT)
    client = run._store_for(SLUG)
    embeddings = get_embedding_model()

    done = 0
    for i, record in enumerate(records, 1):
        # 판단까지 끝난 기록만 건너뛴다. "matched가 비었나"로 보면 관련 이슈가
        # 없다고 판단한 정상 기록까지 다시 돌리게 된다
        if record.get("judged"):
            continue

        message = record.get("message", "").strip()
        # 메시지가 없거나 실제 커밋 제목이 들어간 기록은 생성부터 다시 한다
        if not message or message.splitlines()[0].strip() == record["subject"].strip():
            record.update(_evaluate(repo, client, embeddings,
                                    Case(record["sha"], record["subject"], record["answer"])))
            done += 1
            print(f"\r  보완 {i}/{len(records)} (재생성)", end="", flush=True)
            continue

        hits = retrieve_issues(client, embeddings, message, limit=RETRIEVE_LIMIT)
        record["candidates"] = [int(h.metadata["number"]) for h in hits]
        try:
            record["matched"] = judge(message, hits).issue_number if hits else None
            record["judged"] = True
        except LLMError as exc:
            print(f"\n  판단 실패: {exc}", file=sys.stderr)
            break

        done += 1
        print(f"\r  보완 {i}/{len(records)}", end="", flush=True)

    client.close()
    RESULT_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\r  보완 {done}건 완료" + " " * 20)
    _report(records)


if __name__ == "__main__":
    main()
