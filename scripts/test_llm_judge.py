#!/usr/bin/env python3
"""
照妖镜 — LLM-as-a-Judge 全自动阅卷引擎
用 DeepSeek 作为裁判，对比 Alice 回答 vs Jira 真实数据
"""
import sys, os, json, requests

BASE_URL = "http://127.0.0.1:9099"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

GREEN, RED, CYAN, YELLOW, RESET = '\033[92m', '\033[91m', '\033[96m', '\033[93m', '\033[0m'

class LLMJudge:
    def __init__(self):
        self.deepseek_key = os.getenv("DEEPSEEK_KEY", "")
        # 从 global_config 读取
        try:
            with open("backend/global_config.json") as f:
                cfg = json.load(f)
                self.deepseek_key = cfg.get("DEEPSEEK_KEY", self.deepseek_key)
                self.jira_url = cfg.get("JIRA_BASE_URL", "http://ctjira1.lmdgame.com:8080")
                self.jira_pat = cfg.get("JIRA_PAT", "")
        except:
            self.jira_url = "http://ctjira1.lmdgame.com:8080"
            self.jira_pat = ""

    def get_ground_truth(self, issue_key: str, assignee: str = "") -> dict:
        """直接通过 Jira API 获取真实数据 (不经过 LLM)"""
        try:
            auth = __import__('base64').b64encode(f"{self.jira_pat}:".encode()).decode()
            resp = requests.get(
                f"{self.jira_url.rstrip('/')}/rest/api/2/issue/{issue_key}",
                headers={"Authorization": f"Basic {auth}"},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                fields = data.get("fields", {})
                return {
                    "key": data.get("key"),
                    "summary": fields.get("summary"),
                    "status": fields.get("status", {}).get("name"),
                    "assignee": (fields.get("assignee") or {}).get("displayName", "未分配"),
                    "issuetype": fields.get("issuetype", {}).get("name"),
                }
            return {"error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def ask_alice(self, question: str, timeout: int = 180) -> str:
        """向后端发送问题，返回爱丽丝的完整回答"""
        try:
            resp = requests.post(
                f"{BASE_URL}/v1/chat/completions",
                json={"messages": [{"role": "user", "content": question}]},
                stream=True, timeout=timeout,
            )
            collected = []
            for line in resp.iter_lines():
                if line and b'data: ' in line and b'[DONE]' not in line:
                    try:
                        chunk = json.loads(line.decode().split('data: ', 1)[1])
                        d = chunk.get('choices', [{}])[0].get('delta', {}).get('content', '')
                        if d: collected.append(d)
                    except:
                        pass
            return ''.join(collected)
        except Exception as e:
            return f"[ERROR] {e}"

    def evaluate(self, truth: dict, answer: str, context: str = "") -> dict:
        """用 DeepSeek 作为裁判，对比真实数据 vs Alice 回答"""
        if not self.deepseek_key:
            return {"pass": None, "reason": "DEEPSEEK_KEY 未配置"}

        truth_str = json.dumps(truth, ensure_ascii=False, indent=2)
        prompt = (
            f"你是无情的自动化裁判。\n\n"
            f"【标准事实】(来自 Jira API 的真实数据)：\n{truth_str}\n\n"
            f"【当前测试场景】：{context}\n\n"
            f"【爱丽丝的回答】：\n{answer[:2000]}\n\n"
            f"请判断：\n"
            f"1. 爱丽丝的回答中是否包含标准事实里的关键数据（如任务编号、标题、状态、经办人）？\n"
            f"2. 爱丽丝是否捏造了不存在的版本号、人名或数据？\n"
            f"3. 对于代码类问题，爱丽丝的回答是否为有效内容（非空字符串、非纯数字）？\n\n"
            f"严格返回 JSON 格式（不要外层 Markdown 代码块）：\n"
            f'{{"pass": true/false, "confidence": 0.0-1.0, "reason": "简短的评判理由"}}'
        )

        try:
            resp = requests.post(
                DEEPSEEK_URL,
                headers={"Authorization": f"Bearer {self.deepseek_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 300,
                },
                timeout=30,
            )
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            # 尝试提取 JSON
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except json.JSONDecodeError:
            return {"pass": False, "confidence": 0, "reason": f"裁判 JSON 解析失败: {content[:200]}"}
        except Exception as e:
            return {"pass": False, "confidence": 0, "reason": f"裁判调用失败: {e}"}


def test_case_1(judge: LLMJudge):
    """用例1: 事实一致性 — 获取我的Jira任务真实数量"""
    print(f"\n{'─'*70}")
    print(f"[用例1] 事实一致性: 本周任务数")
    print(f"{'─'*70}")

    # 获取真实数据
    truth = judge.get_ground_truth("CT-10888")
    print(f"  真实数据: {json.dumps(truth, ensure_ascii=False)}")

    # 问 Alice
    answer = judge.ask_alice("CT-10888 当前的状态和负责人是什么？简单回复")
    print(f"  爱丽丝回答 ({len(answer)} chars): {answer[:300]}")

    if not answer or answer.startswith("[ERROR]"):
        print(f"  {RED}[FAIL] 爱丽丝无法回答{RESET}")
        return {"pass": False, "reason": "Alice returned empty/error"}

    verdict = judge.evaluate(truth, answer, "事实一致性：Alice是否正确回答了CT-10888的状态和负责人")
    print(f"  {CYAN}裁判: pass={verdict.get('pass')} conf={verdict.get('confidence',0):.2f}{RESET}")
    print(f"  理由: {verdict.get('reason','?')[:200]}")
    return verdict


def test_case_2(judge: LLMJudge):
    """用例2: DSML修复验证 — 查询 CT-10888 的代码提交"""
    print(f"\n{'─'*70}")
    print(f"[用例2] DSML修复验证: CT-10888 改了哪些文件")
    print(f"{'─'*70}")

    truth = {"key": "CT-10888", "summary": "【系统】新增-阵型养成", "expects_content": True}

    answer = judge.ask_alice("帮我查一下 CT-10888，最近 SVN 里提交了什么？改了哪些文件？")
    print(f"  爱丽丝回答 ({len(answer)} chars)")
    print(f"  前400字符: {answer[:400]}")

    # 关键检查: 回答不能是空字符串
    if not answer.strip():
        print(f"  {RED}[FAIL] DSML 过滤过度: 回答为空!{RESET}")
        return {"pass": False, "confidence": 0, "reason": "DSML过滤导致0 chars输出"}

    if len(answer) < 50:
        print(f"  {YELLOW}[WARN] 回答过短 ({len(answer)} chars){RESET}")

    verdict = judge.evaluate(
        truth, answer,
        "DSML修复验证：Alice是否输出了CT-10888的有效代码提交内容（非空、有实质信息）"
    )
    print(f"  {CYAN}裁判: pass={verdict.get('pass')} conf={verdict.get('confidence',0):.2f}{RESET}")
    print(f"  理由: {verdict.get('reason','?')[:200]}")
    return verdict


def main():
    print("=" * 70)
    print("  照妖镜 — LLM-as-a-Judge 全自动阅卷", flush=True)
    print("=" * 70, flush=True)

    # 健康检查
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"  Health: {GREEN}{r.json().get('status')}{RESET}", flush=True)
    except Exception as e:
        print(f"  {RED}后端未启动: {e}{RESET}", flush=True)
        return

    judge = LLMJudge()
    if not judge.deepseek_key:
        print(f"  {RED}DEEPSEEK_KEY 未配置 — 裁判无法工作{RESET}", flush=True)
        return
    print(f"  Judge ready (DeepSeek key: {judge.deepseek_key[:8]}...)", flush=True)

    r1 = test_case_1(judge)
    r2 = test_case_2(judge)

    print(f"\n{'='*70}")
    print(f"  阅卷结果汇总")
    print(f"{'='*70}")

    def emoji(v): return f"{GREEN}PASS" if v.get('pass') else f"{RED}FAIL"
    print(f"  用例1 (事实一致性): {emoji(r1)} | {r1.get('reason','?')[:100]}{RESET}")
    print(f"  用例2 (DSML修复验证): {emoji(r2)} | {r2.get('reason','?')[:100]}{RESET}")

    # 最终判决 JSON
    report = {
        "test_case_1_fact_check": {"pass": r1.get("pass"), "reason": r1.get("reason")},
        "test_case_2_dsml_fix": {"pass": r2.get("pass"), "reason": r2.get("reason")},
    }
    print(f"\n  最终裁判 JSON:")
    print(f"  {GREEN}{json.dumps(report, ensure_ascii=False, indent=2)}{RESET}", flush=True)


if __name__ == "__main__":
    main()
