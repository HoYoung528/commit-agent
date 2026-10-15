"""`analyze_diff` 노드.

유일하게 외부 호출이 없는 노드다. 가짜 객체 없이 그대로 돌린다.
"""

from __future__ import annotations

from commit_agent.agent.nodes import analyze_diff_node
from commit_agent.agent.schemas import CommitAgentState


def test_diff를_파싱해_상태에_담는다(state):
    result = analyze_diff_node(state)

    analysis = result["analysis"]
    assert not analysis.is_empty()
    assert [f.path for f in analysis.files] == ["src/commit_agent/core/llm.py"]


def test_빈_diff면_빈_분석을_돌려준다():
    result = analyze_diff_node(CommitAgentState(diff_text=""))

    assert result["analysis"].is_empty()


def test_노이즈_파일만_있으면_제외_목록에_남는다():
    diff = """\
diff --git a/uv.lock b/uv.lock
index 1111111..2222222 100644
--- a/uv.lock
+++ b/uv.lock
@@ -1,3 +1,3 @@
-version = 1
+version = 2
"""
    result = analyze_diff_node(CommitAgentState(diff_text=diff))

    analysis = result["analysis"]
    assert analysis.is_empty()
    assert analysis.excluded == ["uv.lock"]
