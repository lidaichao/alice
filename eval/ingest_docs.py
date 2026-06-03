"""
eval/ingest_docs.py — 真实文档提取器 (T1.2)
1. 通过 Notion API 搜索核心文档
2. 拉取 Page Blocks 并转为 Markdown
3. 使用 LangChain RecursiveCharacterTextSplitter 智能分块
4. 输出到 eval/data/corpus.json
"""
import os, sys, json, time
import requests
from pathlib import Path

# 添加 eval 到 sys.path 以便导入 config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import NOTION_KEY, NOTION_DATABASE_ID

# ═══════════════════════════════════════════════════════
#  配置
# ═══════════════════════════════════════════════════════
NOTION_API = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data", "corpus.json")

# ═══════════════════════════════════════════════════════
#  工具函数: Blocks → Markdown
# ═══════════════════════════════════════════════════════
def blocks_to_markdown(blocks: list) -> str:
    """将 Notion Block 列表转为 Markdown 纯文本"""
    lines = []
    for block in blocks:
        btype = block.get("type", "")
        content = block.get(btype, {})

        if btype == "heading_1":
            text = rich_text_plain(content.get("rich_text", []))
            lines.append(f"# {text}")
        elif btype == "heading_2":
            text = rich_text_plain(content.get("rich_text", []))
            lines.append(f"## {text}")
        elif btype == "heading_3":
            text = rich_text_plain(content.get("rich_text", []))
            lines.append(f"### {text}")
        elif btype == "paragraph":
            text = rich_text_plain(content.get("rich_text", []))
            if text.strip():
                lines.append(text)
        elif btype == "bulleted_list_item":
            text = rich_text_plain(content.get("rich_text", []))
            lines.append(f"- {text}")
        elif btype == "numbered_list_item":
            text = rich_text_plain(content.get("rich_text", []))
            lines.append(f"1. {text}")
        elif btype == "code":
            text = rich_text_plain(content.get("rich_text", []))
            lang = content.get("language", "")
            lines.append(f"```{lang}\n{text}\n```")
        elif btype == "quote":
            text = rich_text_plain(content.get("rich_text", []))
            lines.append(f"> {text}")
        elif btype == "divider":
            lines.append("---")
        elif btype == "callout":
            text = rich_text_plain(content.get("rich_text", []))
            lines.append(f"> **{text}**")
        elif btype == "image":
            url = content.get("file", {}).get("url") or content.get("external", {}).get("url", "")
            cap = rich_text_plain(content.get("caption", []))
            lines.append(f"![{cap}]({url})" if url else f"[图片: {cap}]")
        elif btype == "table":
            lines.append("[表格 — 已省略]")
        elif btype.startswith("toggle"):
            text = rich_text_plain(content.get("rich_text", []))
            lines.append(f"<details><summary>{text}</summary>\n(折叠内容)\n</details>")
        else:
            # 未知类型尝试提取 rich_text
            if "rich_text" in content:
                text = rich_text_plain(content.get("rich_text", []))
                if text.strip():
                    lines.append(text)

        # 递归处理子 blocks
        if content.get("children"):
            lines.append(blocks_to_markdown(content["children"]))

    return "\n\n".join(lines)


def rich_text_plain(rich_text: list) -> str:
    """将 Notion rich_text 数组转为纯文本"""
    if not rich_text:
        return ""
    return "".join(
        item.get("plain_text", "") for item in rich_text
    )


# ═══════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════
def fetch_page_blocks(page_id: str) -> list:
    """拉取 Page 的全部 Blocks (递归获取分页)"""
    blocks = []
    cursor = None
    while True:
        url = f"{NOTION_API}/blocks/{page_id}/children"
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  [WARN] Blocks fetch failed for {page_id}: {resp.status_code}")
            break
        data = resp.json()
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        time.sleep(0.3)
    return blocks


def main():
    print("=" * 60)
    print("  Alice Eval Engine — 文档提取器 (T1.2)")
    print("=" * 60)

    if not NOTION_KEY:
        print("[FATAL] NOTION_KEY 未配置! 请检查 eval/config.py")
        return

    # ── Step 1: 搜索核心文档 ──────────────────────
    print("\n[Step 1] 搜索 Notion 核心文档...")
    search_queries = ["策划文档", "战术系统", "技术栈", "战斗", "阵型"]
    all_pages = []

    for query in search_queries:
        print(f"  搜索: '{query}'...")
        try:
            resp = requests.post(
                f"{NOTION_API}/search",
                headers=HEADERS,
                json={"query": query, "page_size": 5},
                timeout=15,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                for r in results:
                    pid = r.get("id", "")
                    if pid not in [p["id"] for p in all_pages]:
                        title_obj = r.get("properties", {}).get("title", {}).get("title", [{}])
                        title = "".join(t.get("plain_text", "") for t in title_obj) if isinstance(title_obj, list) else str(r.get("url", pid))
                        all_pages.append({
                            "id": pid,
                            "title": title or r.get("url", pid),
                        })
            time.sleep(0.3)
        except Exception as e:
            print(f"  [WARN] Search '{query}' failed: {e}")

    all_pages = all_pages[:5]  # 取前5篇
    print(f"  找到 {len(all_pages)} 篇文档:")
    for p in all_pages:
        print(f"    - [{p['id'][:8]}...] {p['title'][:60]}")

    if not all_pages:
        print("[FATAL] 未找到任何文档!")
        return

    # ── Step 2: 拉取 Blocks → Markdown ────────────
    print(f"\n[Step 2] 拉取文档内容...")
    full_docs = []
    for i, page in enumerate(all_pages):
        print(f"  [{i+1}/{len(all_pages)}] {page['title'][:50]}...")
        blocks = fetch_page_blocks(page["id"])
        if not blocks:
            print(f"    [SKIP] 无内容")
            continue
        md_text = blocks_to_markdown(blocks)
        if len(md_text) < 20:
            print(f"    [SKIP] 内容过短 ({len(md_text)} chars)")
            continue
        full_docs.append({
            "doc_id": page["id"],
            "title": page["title"],
            "content": md_text,
        })
        print(f"    ✓ {len(md_text)} chars Markdown")
        time.sleep(0.5)

    if not full_docs:
        print("[FATAL] 所有文档均无有效内容!")
        return

    # ── Step 3: LangChain 智能分块 ─────────────────
    print(f"\n[Step 3] LangChain RecursiveCharacterTextSplitter 分块...")
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        try:
            from langchain.text_splitter import RecursiveCharacterTextSplitter
        except ImportError:
            print("[FATAL] langchain 未安装! 请运行: pip install -r eval/requirements.txt")
            return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", "。", ".", " ", ""],
    )

    corpus = []
    for doc in full_docs:
        chunks = splitter.split_text(doc["content"])
        for ci, chunk in enumerate(chunks):
            corpus.append({
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "chunk_id": ci,
                "content": chunk,
            })
        print(f"  {doc['title'][:40]}: {len(chunks)} chunks")

    # ── Step 4: 保存 corpus.json ───────────────────
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"  完成! {len(corpus)} chunks → {OUTPUT_PATH}")
    print(f"  总字符数: {sum(len(c['content']) for c in corpus):,}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
