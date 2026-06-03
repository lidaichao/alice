"""
eval/generate_chaos_testset.py — 混沌工程师出题引擎
读取 omni_corpus.json → DeepSeek 生成跨域复合查询题
"""
import os, sys, json, random, time, requests
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DEEPSEEK_KEY

CORPUS = os.path.join(os.path.dirname(__file__), "data", "omni_corpus.json")
OUT = os.path.join(os.path.dirname(__file__), "data", "testset_chaos_v2.csv")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

SAMPLE_SIZE = 10  # 可通过命令行参数覆盖

CHAOS_PROMPT = """你是一个极其刁钻的系统测试专家（混沌工程师）。请从下方提供的全域混合数据集（包含 Jira、SVN、文档）中，提取关联信息，生成跨域复合查询题。

【绝对红线指令】：
你生成的测试题中，涉及的任何任务号（如 CT-xxxx）、人员姓名、文档名称、版本号，**必须且只能完全来自 omni_corpus.json 中的真实数据！**
绝对禁止捏造或推测任何不存在的 ID 或名称！如果数据集中只有 CT-10888、CT-11112、CT-11113，你就只能围绕这些真实编号出题！

要求：
1. 每道题必须跨越至少 2 个数据源（例如 Jira+SVN、SVN+Doc、Doc+Jira）
2. 题目要刁钻但答案必须能从数据中推导
3. 生成 JSON 数组：[
   {"question": "...", "ground_truth": "根据数据可推导的正确答案", "context_used": "来源数据源"}
]
4. 不要输出任何 Markdown 标记，只输出纯 JSON 数组。"""


def load_corpus():
    with open(CORPUS, "r", encoding="utf-8") as f:
        return json.load(f)


def build_dataset_text(corpus: list) -> str:
    """将异构数据拼接为纯文本 Prompt"""
    lines = ["=== 全域混合数据集 ===\n"]
    for c in corpus:
        tag = c["source_type"].upper()
        lines.append(f"[{tag}] {c.get('title','')}: {c.get('content','')[:200]}")
    return "\n".join(lines)


def generate_questions(sample_size: int) -> list:
    print(f"[Chaos] Generating {sample_size} cross-domain questions...")
    corpus = load_corpus()
    data_text = build_dataset_text(corpus)

    try:
        resp = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": CHAOS_PROMPT},
                    {"role": "user", "content": data_text[:6000]},
                ],
                "temperature": 0.8,
                "max_tokens": 2000,
            },
            timeout=60,
        )
        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if content.startswith("```"):
            content = content.split("```")[1].replace("json", "").strip()
        questions = json.loads(content)
        return questions[:sample_size]
    except Exception as e:
        print(f"  [ERR] {e}")
        return []


def main():
    global SAMPLE_SIZE
    if len(sys.argv) > 1:
        SAMPLE_SIZE = int(sys.argv[1])

    print("=" * 60)
    print(f"  Chaos Testset Generator (sample={SAMPLE_SIZE})")
    print("=" * 60)

    questions = generate_questions(SAMPLE_SIZE)
    if not questions:
        print("[FATAL] No questions generated — using fallback")
        questions = [
            {"question": "CT-10888 阵型养成任务对应的 r40632 提交者是谁？", "ground_truth": "张锡涛", "context_used": "Jira+SVN"},
            {"question": "战术系统文档中描述的进攻战术有多少种？哪个Jira任务负责实现？", "ground_truth": "8种进攻战术, CT-22160 魏诗豪", "context_used": "Doc+Jira"},
            {"question": "丁儒最近提交了哪些版本的代码？改了什么？", "ground_truth": "r40609(8文件Merge), r40589(19文件命名空间)", "context_used": "SVN"},
            {"question": "BattleRec回放系统属于哪个Jira任务？负责人是谁？", "ground_truth": "CT-22053, 袁伟伟", "context_used": "Doc+Jira"},
            {"question": "阵型养成相关的SVN提交在哪个日期段最密集？", "ground_truth": "2026-06-03 16:23~21:20, 张锡涛4次提交", "context_used": "SVN+Jira"},
        ]

    df = pd.DataFrame(questions)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n  Done! {len(df)} questions → {OUT}")
    for i, row in df.iterrows():
        q = row["question"][:80]
        a = str(row.get("ground_truth", ""))[:80]
        print(f"  {i+1}. Q: {q}")
        print(f"     A: {a}")


if __name__ == "__main__":
    main()
