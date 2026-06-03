"""
eval/run_tests.py — 自动化拷问 + 双维度裁判 + 报告生成 (T3.1+T3.2+T3.3)
"""
import os, sys, json, time, requests
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DEEPSEEK_KEY

ALICE_URL = "http://127.0.0.1:9099/v1/chat/completions"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
TEST_CSV = os.path.join(os.path.dirname(__file__), "data", "testset_v1.csv")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", "eval_report_latest.md")

GREEN, RED, CYAN, RESET = '\033[92m', '\033[91m', '\033[96m', '\033[0m'

JUDGE_PROMPT = """你是无情的 AI 评测法官。

【标准上下文】: {context}
【标准答案】: {ground_truth}
【用户的提问】: {question}
【Alice的回答】: {alice_answer}

请评估 Alice 的回答，输出严格的 JSON：
{{
  "faithfulness": <0或1>,
  "relevance": <0或1>,
  "reason": "<简短的一句话理由>"
}}"""


def ask_alice(question: str, timeout: int = 180) -> str:
    """向 Alice 后端发送请求，收集 SSE 流式回答"""
    try:
        resp = requests.post(
            ALICE_URL,
            json={"messages": [{"role": "user", "content": question}]},
            stream=True, timeout=timeout,
        )
        collected = []
        for line in resp.iter_lines():
            if not line:
                continue
            decoded = line.decode('utf-8', errors='replace')
            if 'data: [DONE]' in decoded:
                break
            if decoded.startswith('data: '):
                chunk = decoded[6:]
                try:
                    data = json.loads(chunk)
                    d = data.get('choices', [{}])[0].get('delta', {}).get('content', '')
                    if d:
                        collected.append(d)
                except json.JSONDecodeError:
                    continue
        return ''.join(collected)
    except Exception as e:
        return f"[ERROR] {e}"


def judge(question: str, context: str, ground_truth: str, alice_answer: str) -> dict:
    """用 DeepSeek 作为裁判，返回 {faithfulness, relevance, reason}"""
    prompt = JUDGE_PROMPT.format(
        context=context[:1500],
        ground_truth=ground_truth[:500],
        question=question,
        alice_answer=alice_answer[:1500] if alice_answer else "(Alice 未回答)",
    )
    try:
        resp = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 200,
            },
            timeout=30,
        )
        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if content.startswith("```"):
            content = content.split("```")[1].replace("json", "").strip()
        return json.loads(content)
    except:
        return {"faithfulness": 0, "relevance": 0, "reason": "裁判调用失败"}


def gen_report(results: list) -> str:
    """生成 Markdown 评测报告"""
    avg_f = sum(r["faithfulness"] for r in results) / len(results) if results else 0
    avg_r = sum(r["relevance"] for r in results) / len(results) if results else 0
    failed = [r for r in results if r["relevance"] == 0 or r["faithfulness"] == 0]

    lines = [
        f"# Alice AI Bridge — 自动化评测报告",
        f"",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 题库: testset_v1.csv ({len(results)} 题)",
        f"",
        f"## 总体得分",
        f"",
        f"| 指标 | 得分 |",
        f"|------|------|",
        f"| **平均忠实度 (Faithfulness)** | **{avg_f:.1%}** |",
        f"| **平均相关性 (Relevance)** | **{avg_r:.1%}** |",
        f"| 总题数 | {len(results)} |",
        f"| 通过题数 | {sum(1 for r in results if r['relevance'] == 1 and r['faithfulness'] == 1)} |",
        f"",
    ]
    if failed:
        lines += [
            f"## 失败案例 ({len(failed)} 题)",
            f"",
            f"| # | 题目 | Alice回答 | 评分 | 理由 |",
            f"|---|------|-----------|------|------|",
        ]
        for i, f in enumerate(failed[:10], 1):
            q = f["question"][:40]
            a = (f.get("alice_answer", "") or "")[:60]
            score = f"F={f['faithfulness']} R={f['relevance']}"
            reason = f.get("reason", "")[:60]
            lines.append(f"| {i} | {q} | {a} | {score} | {reason} |")

    lines += [
        f"",
        f"## 全部结果",
        f"",
        f"| # | 题目 | 忠实度 | 相关性 | 理由 |",
        f"|---|------|:--:|:--:|------|",
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"| {i} | {r['question'][:50]} | {r['faithfulness']} | {r['relevance']} | {r.get('reason','')[:50]} |")

    return "\n".join(lines)


def main():
    print("=" * 60)
    print("  Alice Eval Engine — 自动化拷问 + 双维度裁判 (T3)")
    print("=" * 60)

    if not DEEPSEEK_KEY:
        print("[FATAL] DEEPSEEK_KEY not configured")
        return

    # Step 1: 加载 + 健康检查
    df = pd.read_csv(TEST_CSV)
    print(f"\n[Step 1] Loaded {len(df)} questions from testset_v1.csv")

    try:
        h = requests.get("http://127.0.0.1:9099/health", timeout=5)
        print(f"  Backend: {h.json().get('status')}")
    except:
        print(f"  {RED}Backend offline — 请先启动 python backend/ai_bridge.py{RESET}")
        return

    # Step 2: 逐题拷问 + 裁判
    print(f"\n[Step 2] Running {len(df)} tests...")
    results = []
    for i, row in df.iterrows():
        q = row["question"]
        print(f"\n  [{i+1}/{len(df)}] {q[:80]}...", flush=True)

        alice_answer = ask_alice(q)
        alice_answer = (alice_answer or "").strip()
        print(f"    Alice: {len(alice_answer)} chars", flush=True)
        if alice_answer:
            print(f"    {CYAN}{alice_answer[:120]}{RESET}", flush=True)

        verdict = judge(q, row["context"], row["ground_truth"], alice_answer)
        print(f"    Judge: F={verdict.get('faithfulness')} R={verdict.get('relevance')} | {verdict.get('reason','?')[:80]}", flush=True)

        results.append({
            "question": q,
            "ground_truth": row["ground_truth"],
            "alice_answer": alice_answer,
            "faithfulness": verdict.get("faithfulness", 0),
            "relevance": verdict.get("relevance", 0),
            "reason": verdict.get("reason", ""),
        })
        time.sleep(1)

    # Step 3: 生成报告
    print(f"\n[Step 3] Generating report...")
    report = gen_report(results)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)

    avg_f = sum(r["faithfulness"] for r in results) / len(results)
    avg_r = sum(r["relevance"] for r in results) / len(results)
    passes = sum(1 for r in results if r["relevance"] == 1 and r["faithfulness"] == 1)
    print(f"\n{'='*60}")
    print(f"  评测完成! {passes}/{len(results)} 通过")
    print(f"  忠实度: {avg_f:.1%} | 相关性: {avg_r:.1%}")
    print(f"  报告: {REPORT_PATH}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
