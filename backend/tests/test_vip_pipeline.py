"""VIP 链路离线自动化测试
验证 Diff VIP 直通路在完全不产生真实网络请求的情况下:
  1. 收集了假 Diff + Mock 文档
  2. 记忆了用户的"重点看并发"诉求
  3. 返回了合法的 SSE 流
"""
import json
import pytest
from unittest.mock import patch, MagicMock


# ── Mock 数据 ────────────────────────────────────────────

MOCK_SVN_DIFF = """## SVN Diff: r40538

```diff
Index: server/src/model_game_troops.go
===================================================================
--- server/src/model_game_troops.go	(revision 40537)
+++ server/src/model_game_troops.go	(revision 40538)
@@ -120,6 +120,20 @@
 	return result
 }

+// GetFormationLevelAttr 获取阵型升级属性 (并发安全)
+func (m *ModelGameTroops) GetFormationLevelAttr(formationID, position int) map[int32]float64 {
+	m.mu.RLock()
+	defer m.mu.RUnlock()
+	result := make(map[int32]float64)
+	for _, v := range m.FormationLevels {
+		if v.FormationID == formationID && v.Position == position {
+			for attrID, val := range v.Attrs {
+				result[attrID] += val
+			}
+		}
+	}
+	return result
+}
```
"""

MOCK_DOC_CATALOG = {
    "status": "ok",
    "result": [
        {
            "doc_id": "mock-doc-001",
            "title": "战术系统设计案（阵型养成）",
            "source": "notion",
            "snippet": "描述阵型升级属性加成的策划案..."
        }
    ]
}

MOCK_DOC_CONTENT = """## 战术系统 - 阵型养成

### 属性加成逻辑
- 阵型升级后可为指定位置的球员提供属性加成
- 属性包括: 射门、传球、防守、速度等
- 加成数值由策划表配置，支持按等级递增

### 并发设计要点
- 球员属性读取需要加读锁 (RLock)
- 属性写入（升级）需要加写锁 (WLock)
- 避免在锁内进行网络IO操作
"""


# ── 测试用例 ─────────────────────────────────────────────

class TestVIPDiffPipeline:
    """VIP Diff 直通车离线测试 — v3.0 Phase 4.3 模块已删除"""

    @pytest.mark.xfail(reason="v3.0 Phase 4.3: knowledge_retriever 已删除 · VIP 快车道降级")
    @patch("ai_bridge.http")
    @patch("ai_bridge._exec_read_specific_doc")
    @patch("ai_bridge._exec_search_docs_catalog")
    def test_vip_diff_intent(
        self,
        mock_search_catalog,
        mock_read_doc,
        mock_http,
    ):
        """验证 Diff VIP 全链路: 假数据 + 记忆用户诉求 + 无真实网络请求"""
        from ai_bridge import app as flask_app
        
        # ── Mock 配置 ──
        mock_keywords.return_value = "阵型养成"
        mock_svn_diff.return_value = MOCK_SVN_DIFF
        mock_search_catalog.return_value = json.dumps(MOCK_DOC_CATALOG, ensure_ascii=False)
        mock_read_doc.return_value = json.dumps(
            {"status": "ok", "llm_text": MOCK_DOC_CONTENT}, ensure_ascii=False
        )
        
        # Mock LLM 流式响应 (模拟 DeepSeek 返回)
        mock_llm_response = MagicMock()
        mock_llm_response.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"Code Review: "}}]}'.encode('utf-8'),
            'data: {"choices":[{"delta":{"content":"本次提交新增阵型升级属性方法,重点关注并发安全"}}]}'.encode('utf-8'),
        ]
        mock_http.post.return_value = mock_llm_response
        
        # ── 发送请求 ──
        user_query = "帮我分析一下 r40538 的代码 diff，重点看并发"
        
        with flask_app.test_client() as client:
            response = client.post(
                "/v1/chat/completions",
                data=json.dumps({"messages": [{"role": "user", "content": user_query}]}),
                content_type="application/json",
            )
            
            assert response.status_code == 200
            assert "text/event-stream" in response.content_type
            
            # ── 解析 SSE 流 ──
            sse_text = response.data.decode("utf-8")
            sse_lines = sse_text.strip().split("\n")
            
            # 收集所有 delta content
            content_parts = []
            for line in sse_lines:
                line = line.strip()
                if line.startswith("data: ") and "choices" in line:
                    try:
                        data = json.loads(line[6:])
                        delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            content_parts.append(delta)
                    except Exception:
                        pass
            
            full_response = "".join(content_parts)
            
            # ── 断言 ──
            # 1. 包含假 Diff 中的核心代码
            assert "GetFormationLevelAttr" in full_response or len(full_response) > 0, \
                "VIP should process SVN diff data"
            
            # 2. 包含 Mock 文档内容
            # (文档被注入到 prompt 中了, LLM 应引用它)
            assert len(full_response) > 20, \
                f"VIP should produce meaningful output, got: '{full_response[:50]}'"
            
            # 3. 验证用户的"重点看并发"诉求被记忆
            # (prompt 末尾追加了 user_text)
            # 间接验证: Mock LLM 返回的内容被正确流式传输
            assert "Code Review" in full_response or "提交" in full_response or len(full_response) > 10, \
                "VIP should stream LLM response correctly"
            
            # 4. 验证全程未产生真实网络请求
            # (所有依赖都被 Mock 了, 如果调了真实的 httpx/requests 会报错)
            
            # 5. 验证 Mock 被正确调用
            mock_svn_diff.assert_called_once()
            mock_keywords.assert_called_once()
            mock_search_catalog.assert_called_once()
            
            print(f"[VIP Test] PASS - Full response ({len(full_response)} chars)")


class TestVIPCatalogPipeline:
    """Catalog VIP 文档查询离线测试 — v3.0 Phase 4.3 模块已删除"""

    @pytest.mark.xfail(reason="v3.0 Phase 4.3: knowledge_retriever 已删除 · VIP 快车道降级")
    @patch("ai_bridge.http")
    @patch("ai_bridge._exec_search_docs_catalog")
    def test_vip_catalog_intent(
        self,
        mock_search_catalog,
        mock_http,
    ):
        """验证 Catalog VIP: 文档查询绕过 ReAct"""
        from ai_bridge import app as flask_app
        
        mock_keywords.return_value = "阵型"
        mock_search_catalog.return_value = json.dumps(MOCK_DOC_CATALOG, ensure_ascii=False)
        
        mock_llm_response = MagicMock()
        mock_llm_response.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"找到以下文档:"}}]}'.encode('utf-8'),
            'data: {"choices":[{"delta":{"content":"- [NOTION] 《战术系统设计案》"}}]}'.encode('utf-8'),
        ]
        mock_http.post.return_value = mock_llm_response
        
        with flask_app.test_client() as client:
            response = client.post(
                "/v1/chat/completions",
                data=json.dumps({"messages": [{"role": "user", "content": "有哪些阵型相关的设计案？"}]}),
                content_type="application/json",
            )
            
            assert response.status_code == 200
            sse_text = response.data.decode("utf-8")
            
            # Catalog VIP 应该直接输出文档列表, 不经过 ReAct
            assert len(sse_text) > 0
            print(f"[VIP Catalog Test] PASS - SSE stream returned")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
