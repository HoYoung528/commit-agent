"""생성 메시지와 실제 커밋 메시지를 비교한다.

정량 지표는 타입 일치, scope 일치, 제목 유사도다. 제목은 문자 단위와 의미
단위를 함께 본다 — 문자 유사도는 같은 뜻을 다른 단어로 쓰면 낮게 나오고,
임베딩 유사도는 표현이 달라도 뜻이 같으면 높게 나온다.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from langchain_core.embeddings import Embeddings

from evaluation.corpus import CommitRef, parse_header


@dataclass(frozen=True)
class Comparison:
    """한 커밋에 대한 비교 결과."""

    sha: str
    actual: str
    generated: str
    type_match: bool
    scope_presence_match: bool
    scope_value_match: bool | None  # 양쪽 모두 scope가 있을 때만 판단
    text_similarity: float
    parsed: bool  # 생성 결과가 규약 형식을 지켰는지


def compare(ref: CommitRef, generated: str) -> Comparison:
    """실제 커밋과 생성 메시지를 맞춰 본다."""
    parsed = parse_header(generated)

    if parsed is None:
        return Comparison(
            sha=ref.sha,
            actual=ref.header,
            generated=generated.splitlines()[0] if generated else "",
            type_match=False,
            scope_presence_match=False,
            scope_value_match=None,
            text_similarity=0.0,
            parsed=False,
        )

    gen_type, gen_scope, gen_subject = parsed
    both_have_scope = bool(ref.scope) and bool(gen_scope)

    return Comparison(
        sha=ref.sha,
        actual=ref.header,
        generated=f"{gen_type}{f'({gen_scope})' if gen_scope else ''}: {gen_subject}",
        type_match=gen_type == ref.type,
        scope_presence_match=bool(ref.scope) == bool(gen_scope),
        scope_value_match=(gen_scope == ref.scope) if both_have_scope else None,
        text_similarity=SequenceMatcher(None, ref.subject, gen_subject).ratio(),
        parsed=True,
    )


@dataclass(frozen=True)
class Summary:
    """표본 전체 집계."""

    count: int
    parsed_rate: float
    type_match_rate: float
    scope_presence_rate: float
    scope_value_rate: float | None
    text_similarity: float
    semantic_similarity: float | None = None

    def as_row(self, label: str) -> str:
        """마크다운 표의 한 줄."""
        scope_value = "-" if self.scope_value_rate is None else f"{self.scope_value_rate:.0%}"
        semantic = "-" if self.semantic_similarity is None else f"{self.semantic_similarity:.3f}"
        return (
            f"| {label} | {self.count} | {self.parsed_rate:.0%} | "
            f"{self.type_match_rate:.0%} | {self.scope_presence_rate:.0%} | "
            f"{scope_value} | {self.text_similarity:.3f} | {semantic} |"
        )


HEADER_ROW = (
    "| 구분 | 표본 | 형식 준수 | 타입 일치 | scope 유무 일치 | scope 값 일치 | 제목 유사도 | 의미 유사도 |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- |"
)


def summarize(
    comparisons: list[Comparison], *, semantic: float | None = None
) -> Summary:
    """비교 결과를 비율로 집계한다."""
    if not comparisons:
        raise ValueError("비교 결과가 없습니다.")

    total = len(comparisons)
    with_scope_value = [c.scope_value_match for c in comparisons if c.scope_value_match is not None]

    return Summary(
        count=total,
        parsed_rate=_rate(c.parsed for c in comparisons),
        type_match_rate=_rate(c.type_match for c in comparisons),
        scope_presence_rate=_rate(c.scope_presence_match for c in comparisons),
        scope_value_rate=(sum(with_scope_value) / len(with_scope_value)) if with_scope_value else None,
        text_similarity=sum(c.text_similarity for c in comparisons) / total,
        semantic_similarity=semantic,
    )


def semantic_similarity(
    embeddings: Embeddings, comparisons: list[Comparison]
) -> float | None:
    """제목 쌍의 임베딩 코사인 유사도 평균.

    표현이 달라도 뜻이 같으면 높게 나오므로 문자 유사도를 보완한다.
    """
    pairs = [(c.actual, c.generated) for c in comparisons if c.parsed]
    if not pairs:
        return None

    texts = [t for pair in pairs for t in pair]
    vectors = embeddings.embed_documents(texts)

    scores = [_cosine(vectors[i], vectors[i + 1]) for i in range(0, len(vectors), 2)]
    return sum(scores) / len(scores)


def _rate(flags) -> float:
    values = list(flags)
    return sum(values) / len(values)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
