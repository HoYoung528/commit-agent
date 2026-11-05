"""평가 지표 계산.

보고서에 들어가는 숫자를 만드는 코드다. 비교 규칙이 틀리면 결과 해석이
전부 어긋나므로 경계 조건을 고정한다.
"""

from __future__ import annotations

import pytest

from evaluation.corpus import CommitRef, parse_header, stratified_sample
from evaluation.metrics import compare, summarize


def ref(commit_type="feat", scope="core", subject="add retry to api calls"):
    return CommitRef("a" * 40, commit_type, scope, subject)


def test_규약_밖의_메시지는_형식_위반으로_센다():
    result = compare(ref(), "updated some files")

    assert not result.parsed
    assert not result.type_match
    assert result.text_similarity == 0.0


def test_타입과_scope가_모두_맞으면_일치로_센다():
    result = compare(ref(), "feat(core): add retry to api calls")

    assert result.parsed
    assert result.type_match
    assert result.scope_presence_match
    assert result.scope_value_match
    assert result.text_similarity == 1.0


def test_scope_값이_달라도_유무는_일치로_센다():
    result = compare(ref(scope="core"), "feat(cli): add retry")

    assert result.scope_presence_match
    assert not result.scope_value_match


def test_실제에_scope가_없는데_붙이면_불일치():
    result = compare(ref(scope=None), "feat(core): add retry")

    assert not result.scope_presence_match
    # 한쪽에만 scope가 있으면 값 비교는 하지 않는다
    assert result.scope_value_match is None


def test_양쪽_모두_scope가_없으면_유무_일치():
    result = compare(ref(scope=None), "feat: add retry")

    assert result.scope_presence_match
    assert result.scope_value_match is None


def test_느낌표가_붙은_헤더도_읽는다():
    assert parse_header("feat(api)!: drop v1") == ("feat", "api", "drop v1")


def test_본문이_있어도_첫_줄만_본다():
    result = compare(ref(), "feat(core): add retry to api calls\n\n- 백오프 적용")

    assert result.type_match
    assert result.text_similarity == 1.0


def test_scope_값_일치율은_양쪽에_scope가_있는_표본만_센다():
    comparisons = [
        compare(ref(scope="core"), "feat(core): x"),  # 값 일치
        compare(ref(scope="core"), "feat(cli): x"),  # 값 불일치
        compare(ref(scope=None), "feat: x"),  # 비교 대상 아님
    ]

    summary = summarize(comparisons)

    assert summary.count == 3
    assert summary.scope_value_rate == pytest.approx(0.5)
    assert summary.scope_presence_rate == pytest.approx(1.0)


def test_scope가_있는_표본이_없으면_값_일치율은_없음():
    summary = summarize([compare(ref(scope=None), "feat: x")])

    assert summary.scope_value_rate is None


def test_표본이_비면_집계하지_않는다():
    with pytest.raises(ValueError):
        summarize([])


def test_타입별로_고르게_뽑는다():
    refs = [ref("fix", subject=f"f{i}") for i in range(20)]
    refs += [ref("docs", subject=f"d{i}") for i in range(3)]

    picked = stratified_sample(refs, per_type=5)

    assert sum(1 for r in picked if r.type == "fix") == 5
    # 모자라면 있는 만큼만 가져온다
    assert sum(1 for r in picked if r.type == "docs") == 3


def test_같은_씨앗이면_같은_표본을_뽑는다():
    refs = [ref("fix", subject=f"f{i}") for i in range(20)]

    assert stratified_sample(refs, per_type=5) == stratified_sample(refs, per_type=5)
