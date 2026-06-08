"""O2 调试阶段 — KB 上下文缓存单元测试（≥2 条）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat_orchestrator import (
    set_kb_cache,
    get_kb_cache,
    detect_contrast_query,
    _simple_keywords,
    _kb_context_cache,
)


class TestKBContextCache(unittest.TestCase):
    """O2 — KB 上下文缓存行为测试。"""

    def setUp(self):
        _kb_context_cache.clear()

    def tearDown(self):
        _kb_context_cache.clear()

    def test_cache_hit_when_keywords_overlap(self):
        """缓存命中：新 query 与 last_query 有 ≥2 个相同关键词时返回缓存条目。"""
        conv_id = "test-conv-01"
        set_kb_cache(conv_id, "后卫名单有哪些人", "gsheet-001", ["chunk-1", "chunk-2"])

        # 新 query 与上轮有关键词重叠
        cached = get_kb_cache(conv_id, "那后卫名单里谁是 SSR")
        self.assertIsNotNone(cached, "should return cached entry when keywords overlap")
        self.assertEqual(cached["last_doc_id"], "gsheet-001")

    def test_cache_miss_topic_switch_clears(self):
        """话题切换：关键词重叠 < 2 时缓存被清，返回 None。"""
        conv_id = "test-conv-02"
        set_kb_cache(conv_id, "后卫名单有哪些人", "gsheet-001", ["chunk-1"])

        # 完全无关的话题
        cached = get_kb_cache(conv_id, "今天天气怎么样")
        self.assertIsNone(cached, "should return None after topic switch")
        self.assertNotIn(conv_id, _kb_context_cache, "cache should be cleared after topic switch")

    def test_contrast_query_detection(self):
        """对比查询信号词检测。"""
        self.assertTrue(detect_contrast_query("对比后卫名单和中锋名单有什么差异"))
        self.assertTrue(detect_contrast_query("有什么区别"))
        self.assertTrue(detect_contrast_query("VS 阵容比较"))
        self.assertFalse(detect_contrast_query("后卫名单有哪些人"))
        self.assertFalse(detect_contrast_query("今天天气怎么样"))

    def test_keyword_overlap_two_or_more(self):
        """关键词重叠检测：≥2 个相同词才算命中。"""
        set_kb_cache("conv-3", "后卫名单有哪些人 球员名单", "doc-1", [])
        # "后卫" "名单" 两个词重叠
        self.assertIsNotNone(get_kb_cache("conv-3", "那后卫名单里有谁"))
        # 重新设置，然后测试只有一个词重叠
        set_kb_cache("conv-4", "后卫名单有哪些人", "doc-2", [])
        # "名单" 只有一个词重叠
        self.assertIsNone(get_kb_cache("conv-4", "球员名单"))


if __name__ == "__main__":
    unittest.main()
