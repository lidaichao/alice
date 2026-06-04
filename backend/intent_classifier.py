"""
IntentClassifier — 工程意图分类管道
移植自白泽 Baize engineering-intent-service.js
在 L1 检索前对用户消息进行意图分类，实现：
  - dangerous: 直接拦截危险操作
  - engineering_write: 写操作需确认
  - jira_operation: Jira 写操作需确认卡
  - engineering_readonly: 只读查询，放行
  - ordinary_chat: 普通对话，放行
"""

import re
import logging

logger = logging.getLogger("intent-classifier")

# ══════════════════════════════════════════════════════════════
#  规则集（移植自 Baize engineering-intent-service.js）
# ══════════════════════════════════════════════════════════════

# 危险操作 —— 直接拦截
DANGEROUS_PATTERNS = [
    re.compile(r'\b(rm\s+-rf|reset\s+--hard|clean\s+-f|push\s+--force|force\s+push)\b', re.I),
    re.compile(r'(删除|清空|销毁).*(全部|所有|整个)'),
    re.compile(r'(读取|查看|打开|看看|看|读).*(\.env|密钥|secret|token|api\s*key|apikey)', re.I),
    re.compile(r'(格式化|format)\s*(硬盘|磁盘|系统)'),
    re.compile(r'\b(drop\s+(database|table)|truncate\s+table|delete\s+from)\b', re.I),
    # SQL 注入特征
    re.compile(r'\b(SELECT\s+\*?\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|CREATE\s+TABLE|ALTER\s+TABLE)\b', re.I),
    re.compile(r'(\b1\s*=\s*1\b|\bOR\s+1\b|\b--\s*$|\bUNION\s+SELECT\b)', re.I),
    # 系统命令注入
    re.compile(r'\b(sudo|su\s+-|chmod\s+\+777|chown\s+root|dd\s+if=|mkfs\.)\b', re.I),
    re.compile(r'(\$\(.*\)|`[^`]+`|&&\s*rm\b|\|\s*sh\b)', re.I),
    # 模板/SSTI 注入
    re.compile(r'(\{\{.*\}\}|__import__|eval\(|exec\(|\.system\(|\.popen\(|os\.system)', re.I),
]

# Jira Issue 状态流转 —— 优先于泛化「工程写」
JIRA_ISSUE_STATUS_PATTERNS = [
    re.compile(
        r'(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9]).*'
        r'(?:改成|改为|更新|修改|设置|流转|transition).*(?:完成|关闭|resolved|进行中|待办|done|closed)',
        re.I,
    ),
    re.compile(
        r'(?:把|将|帮).{0,20}(?:jira|任务|issue).{0,30}'
        r'(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9]).{0,40}'
        r'(?:改成|改为|完成|关闭|流转)',
        re.I,
    ),
    re.compile(
        r'(?:jira|任务|issue).{0,20}(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9]).{0,30}'
        r'(?:状态|state).{0,12}(?:改成|改为|更新|设为|置为).{0,12}(?:完成|关闭|resolved|done)',
        re.I,
    ),
]

# Jira 写操作 —— 需要确认卡
JIRA_WRITE_PATTERNS = [
    re.compile(r'(创建|新建|添加|增加).*(Jira|jira)?.*(任务|issue|bug|需求|story|子任务|subtask|缺陷)'),
    re.compile(r'\b(create|add|new)\s+(task|issue|bug|story|subtask)\b', re.I),
    re.compile(r'(帮我|请).*(创建|建|开).*(Jira|jira|单)'),
    re.compile(r'(修改|更新|改|编辑|删除|关闭).*(Jira|jira).*(任务|issue|bug|需求)'),
    re.compile(r'\b(update|edit|delete|close|resolve|assign|transition)\s+(issue|bug|task)\b', re.I),
    re.compile(r'(批量|导入|批量创建|导入草稿).*(Jira|jira)'),
    re.compile(r'(分配|指派|转交).*(Jira|jira)?.*(任务|issue|bug)'),
]

_ISSUE_KEY_IN_TEXT = re.compile(r'(?<![A-Za-z0-9])([A-Z][A-Z0-9]*-\d+)(?![A-Za-z0-9])')

# 工程写操作 —— 修改代码/文件，需要确认
ENGINEERING_WRITE_PATTERNS = [
    re.compile(r'(修改|改一下|更改|实现|新增|添加|接入|重构|修复|补齐|优化|删除|移除).*(代码|文件|接口|路由|服务|客户端|服务端|UI|样式|测试|配置|逻辑|功能|模块|组件)'),
    re.compile(r'(帮我|请).*(改|修|实现|新增|添加|删除|移除|重构)'),
    re.compile(r'\b(fix|implement|refactor|rewrite|optimize)\b', re.I),
]

# 工程只读查询 —— 放行
ENGINEERING_READONLY_PATTERNS = [
    re.compile(r'(看一下|看看|检查|分析|解释|定位|排查|查一下|阅读|梳理).*(代码|项目|工程|接口|路由|服务|文件|测试|UI|客户端|服务端|报错|bug|问题)'),
    re.compile(r'(怎么实现|在哪里|哪个文件|调用链|架构|结构|逻辑).*(代码|项目|工程|接口|路由|服务|客户端|服务端)?'),
    re.compile(r'\b(stack trace|error|bug|api|route|server|client|electron|express|vitest)\b', re.I),
]

# Jira 只读查询 —— 放行（这些走正常L1检索流程）
JIRA_QUERY_PATTERNS = [
    re.compile(r'(查|搜索|找|统计|汇总).*(Jira|jira)?.*(任务|issue|bug|story|需求)'),
    re.compile(r'\b(query|search|find|list|get)\s+(issues|bugs|tasks|stories)\b', re.I),
    re.compile(r'(我|某人|谁).*(任务|issue|bug|有多少|哪些)'),
    re.compile(r'(日报|周报|月报|总结|汇总|统计)'),
    re.compile(r'(项目|迭代|版本|sprint).*(进度|状态|情况)'),
    re.compile(r'[A-Z][A-Z0-9]*-\d+'),  # Issue Key 引用 (CT-12345 等)
    re.compile(r'(查|查看|看看|看|打开|显示|详情).*(详情|内容|描述|状态|备注|附件|评论)'),
]

# 模糊工程请求
AMBIGUOUS_PATTERNS = [
    re.compile(r'(处理|弄一下|搞一下|优化一下).*(问题|代码|项目|工程|接口|客户端|服务端)?'),
    re.compile(r'(有问题|不好用|不对劲)$'),
]

# 测试/构建请求
TEST_PATTERNS = [
    re.compile(r'(运行|执行|跑).*(测试|test|构建|打包|build|pack|dist)', re.I),
    re.compile(r'\b(npm\s+test|npm\s+run\s+(build|pack|dist|desktop))\b', re.I),
]


def matches_any(text: str, patterns: list) -> bool:
    """检查文本是否匹配任一正则模式"""
    return any(p.search(text) for p in patterns)


def classify_intent(text: str) -> dict:
    """
    对用户消息进行意图分类。

    返回结构:
    {
        "route": str,          # 路由类型
        "reason": str,         # 分类原因
        "requires_confirmation": bool,  # 是否需要确认
        "matched_pattern": str | None, # 匹配到的模式
    }
    """
    if not text or not isinstance(text, str):
        return {
            "route": "ordinary_chat",
            "reason": "empty_text",
            "requires_confirmation": False,
            "matched_pattern": None,
        }

    normalized = text.strip()

    # 1. 危险操作 —— 最高优先级
    for p in DANGEROUS_PATTERNS:
        if p.search(normalized):
            logger.warning(f"[Intent] DANGEROUS blocked: {normalized[:80]}")
            return {
                "route": "dangerous",
                "reason": "dangerous_operation",
                "requires_confirmation": False,  # 直接拦截，不是确认
                "matched_pattern": p.pattern,
            }

    # 2. 测试/构建请求
    for p in TEST_PATTERNS:
        if p.search(normalized):
            return {
                "route": "engineering_test",
                "reason": "test_or_build_request",
                "requires_confirmation": True,
                "matched_pattern": p.pattern,
            }

    # 3. Jira 状态流转 / 写操作（须在泛化 engineering_write 之前）
    for p in JIRA_ISSUE_STATUS_PATTERNS:
        if p.search(normalized):
            return {
                "route": "jira_write",
                "reason": "jira_status_transition",
                "requires_confirmation": True,
                "matched_pattern": p.pattern,
            }

    for p in JIRA_WRITE_PATTERNS:
        if p.search(normalized):
            return {
                "route": "jira_write",
                "reason": "jira_write_request",
                "requires_confirmation": True,
                "matched_pattern": p.pattern,
            }

    # 4. 工程写操作（含 Jira Issue Key 时改走 jira_write，避免误分类）
    for p in ENGINEERING_WRITE_PATTERNS:
        if p.search(normalized):
            if _ISSUE_KEY_IN_TEXT.search(normalized) and re.search(
                r'jira|issue|任务|工单', normalized, re.I
            ):
                return {
                    "route": "jira_write",
                    "reason": "jira_write_from_engineering_pattern",
                    "requires_confirmation": True,
                    "matched_pattern": p.pattern,
                }
            return {
                "route": "engineering_write",
                "reason": "write_request",
                "requires_confirmation": True,
                "matched_pattern": p.pattern,
            }

    # 5. "怎么实现/在哪里/哪个文件" → 只读优先
    if re.search(r'(怎么实现|在哪里|哪个文件|调用链|架构|结构|逻辑)', normalized):
        return {
            "route": "engineering_readonly",
            "reason": "readonly_engineering_question",
            "requires_confirmation": False,
            "matched_pattern": None,
        }

    # 6. Jira 只读查询
    for p in JIRA_QUERY_PATTERNS:
        if p.search(normalized):
            return {
                "route": "jira_query",
                "reason": "jira_read_query",
                "requires_confirmation": False,
                "matched_pattern": p.pattern,
            }

    # 7. 工程只读
    for p in ENGINEERING_READONLY_PATTERNS:
        if p.search(normalized):
            return {
                "route": "engineering_readonly",
                "reason": "readonly_engineering_request",
                "requires_confirmation": False,
                "matched_pattern": p.pattern,
            }

    # 8. 模糊请求
    for p in AMBIGUOUS_PATTERNS:
        if p.search(normalized):
            return {
                "route": "ambiguous",
                "reason": "ambiguous_engineering_request",
                "requires_confirmation": False,
                "matched_pattern": p.pattern,
            }

    # 9. 默认：普通聊天
    return {
        "route": "ordinary_chat",
        "reason": "ordinary_chat",
        "requires_confirmation": False,
        "matched_pattern": None,
    }


# ── 便捷函数 ──────────────────────────────────────────────────

def should_intercept(intent: dict) -> bool:
    """是否需要直接拦截（不交给 LLM）"""
    return intent["route"] in ("dangerous",)


def needs_confirmation(intent: dict) -> bool:
    """是否需要用户确认"""
    return intent["requires_confirmation"]


def is_jira_operation(intent: dict) -> bool:
    """是否是 Jira 操作（需要确认卡）"""
    return intent["route"] == "jira_write"


# ── 自测函数 ──────────────────────────────────────────────────

_TEST_CASES = [
    # (输入, 预期路由, 预期确认)
    ("帮我创建Jira任务：修复登录bug", "jira_write", True),
    ("查看我今天的任务", "jira_query", False),
    ("修改 ai_bridge.py 的缓存逻辑", "engineering_write", True),
    ("看一下这个报错是怎么回事", "engineering_readonly", False),
    ("rm -rf /tmp/test", "dangerous", False),
    ("删除所有代码", "dangerous", False),
    ("帮我跑一下测试", "engineering_test", True),
    ("今天天气怎么样", "ordinary_chat", False),
    ("帮我建一个 Jira bug", "jira_write", True),
    ("统计本周所有人的任务数量", "jira_query", False),
    ("查一下 CT-12345 的详情", "jira_query", False),
    ("批量导入Jira需求", "jira_write", True),
    ("请帮我把 Jira 任务 CT-10888 的状态直接改成完成", "jira_write", True),
    ("这个功能怎么实现", "engineering_readonly", False),
    ("delete from users where id=1", "dangerous", False),
    ("帮我分析一下代码结构", "engineering_readonly", False),
    ("新增一个API接口", "engineering_write", True),
    ("force push 到远程", "dangerous", False),
    ("今天的日报", "jira_query", False),
    ("有问题", "ambiguous", False),
    ("看看.env文件", "dangerous", False),
]


def run_self_test():
    """运行自测，返回 (通过数, 总数, 失败列表)"""
    passed = 0
    failures = []
    for text, expected_route, expected_confirm in _TEST_CASES:
        result = classify_intent(text)
        ok = (result["route"] == expected_route and
              result["requires_confirmation"] == expected_confirm)
        if ok:
            passed += 1
        else:
            failures.append({
                "input": text,
                "expected": {"route": expected_route, "confirmation": expected_confirm},
                "got": {"route": result["route"], "confirmation": result["requires_confirmation"]},
            })
    return passed, len(_TEST_CASES), failures


if __name__ == "__main__":
    # 直接运行：执行自测
    p, t, f = run_self_test()
    print(f"\n{'='*50}")
    print(f"  IntentClassifier 自测结果")
    print(f"{'='*50}")
    print(f"  通过: {p}/{t} ({p*100//t}%)")
    if f:
        print(f"  失败: {len(f)}")
        for item in f:
            print(f"    ✗ '{item['input']}'")
            print(f"      预期: route={item['expected']['route']}, confirm={item['expected']['confirmation']}")
            print(f"      实际: route={item['got']['route']}, confirm={item['got']['confirmation']}")
    else:
        print(f"  ✅ 全部通过!")
    print(f"{'='*50}\n")
