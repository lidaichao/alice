"""
eval/generate_testset.py — 考官出题引擎 (T2.1 + T2.2)
1. 读取 corpus.json → 随机抽取 5 个高质量 chunk
2. 调用 DeepSeek API 为每个 chunk 生成 2 个测试题
3. 组装三元组 (question, context, ground_truth) → testset_v1.csv
"""
import os, sys, json, random, time, requests
import pandas as pd
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DEEPSEEK_KEY

CORPUS_PATH = os.path.join(os.path.dirname(__file__), "data", "corpus.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data", "testset_v1.csv")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

SYSTEM_PROMPT = """你是一个严厉的软件工程考试出题官。请阅读下方提供的【内部文档片段】，针对该内容生成 2 个测试题（1个简单的事实提取题，1个稍微复杂的逻辑综合题）。

必须以严格的 JSON 数组格式返回，格式如下：
[
  {"question": "生成的问题...", "ground_truth": "根据文档得出的标准答案..."}
]
不要输出任何其他废话或 Markdown 标记，只能输出纯 JSON 字符串。"""


def load_corpus() -> list:
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def sample_chunks(corpus: list, n: int = 5) -> list:
    """抽取高质量 chunk（内容 > 200 字符）"""
    good = [c for c in corpus if len(c["content"]) > 200]
    if len(good) <= n:
        return good
    return random.sample(good, n)


def ask_deepseek(chunk: dict) -> list:
    """调用 DeepSeek 生成 2 个测试题，返回 [{"question":..., "ground_truth":...}]"""
    user_msg = f"文档标题: {chunk['title']}\n\n文档内容:\n{chunk['content'][:1500]}"

    try:
        resp = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.7,
                "max_tokens": 800,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"  [ERR] DeepSeek returned {resp.status_code}: {resp.text[:200]}")
            return []

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        # 尝试多种 JSON 解析方式
        for attempt in [
            lambda: json.loads(content),
            lambda: json.loads(content.split("```json")[1].split("```")[0]) if "```json" in content else None,
            lambda: json.loads(content.split("```")[1].split("```")[0]) if "```" in content else None,
        ]:
            try:
                result = attempt()
                if isinstance(result, list) and len(result) > 0:
                    return result
            except (json.JSONDecodeError, IndexError, TypeError):
                continue

        print(f"  [WARN] JSON parse failed, content: {content[:200]}")
        return []

    except Exception as e:
        print(f"  [ERR] DeepSeek call failed: {e}")
        return []


def main():
    print("=" * 60)
    print("  Alice Eval Engine — 考官出题引擎 (T2.1+T2.2)")
    print("=" * 60)

    if not DEEPSEEK_KEY:
        print("[FATAL] DEEPSEEK_KEY not configured")
        return

    # Step 1: 加载 + 抽样
    corpus = load_corpus()
    print(f"\n[Step 1] Loaded {len(corpus)} chunks from corpus.json")
    samples = sample_chunks(corpus, 5)
    print(f"  Sampled {len(samples)} high-quality chunks")

    # Step 2: 逐 chunk 调用 DeepSeek 出题
    print(f"\n[Step 2] Generating questions via DeepSeek...")
    testset = []
    for i, chunk in enumerate(samples):
        title = chunk["title"][:50]
        print(f"  [{i+1}/{len(samples)}] {title}...")
        questions = ask_deepseek(chunk)
        for q in questions:
            testset.append({
                "question": q.get("question", ""),
                "context": chunk["content"],
                "ground_truth": q.get("ground_truth", ""),
                "doc_title": chunk["title"],
                "doc_id": chunk["doc_id"],
            })
        print(f"    → {len(questions)} questions generated")
        time.sleep(0.5)

    if not testset:
        print("[FATAL] No questions generated")
        return

    # Step 3: 导出 CSV
    print(f"\n[Step 3] Saving {len(testset)} questions to {OUTPUT_PATH}")
    df = pd.DataFrame(testset)
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"  Done! {len(df)} rows, columns: {list(df.columns)}")

    # Print preview
    print(f"\n{'='*60}")
    print(f"  考卷预览 (前 3 题)")
    print(f"{'='*60}")
    for i, row in df.head(3).iterrows():
        print(f"\n  Q{i+1}: {row['question'][:120]}")
        print(f"  A{i+1}: {row['ground_truth'][:120]}")
        print(f"  Doc: {row['doc_title'][:50]}")


if __name__ == "__main__":
    main()
