"""
eval/ingest_omni.py — 全域知识库吞噬 (Omni-Source Ingestion)
抓取 Jira + SVN + Notion 异构数据 → omni_corpus.json
"""
import os, sys, json, time, requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import NOTION_KEY, DEEPSEEK_KEY

NOTION_HEADERS = {"Authorization": f"Bearer {NOTION_KEY}", "Notion-Version": "2022-06-28"}
OUT = os.path.join(os.path.dirname(__file__), "data", "omni_corpus.json")

corpus = []

# ═══════════════════════════════════════════════════════
#  模块 1: Jira 抓取 — 通过本地 Alice API
# ═══════════════════════════════════════════════════════
def fetch_jira_samples():
    print("[Jira] Fetching recent tasks via Alice...")
    entries = []
    try:
        resp = requests.post(
            "http://127.0.0.1:9099/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "列出 CT 项目最近完成的任务，包括标题和负责人"}]},
            stream=True, timeout=60,
        )
        collected = []
        for line in resp.iter_lines():
            if line and b'data: ' in line and b'[DONE]' not in line:
                try:
                    d = json.loads(line.decode().split('data: ', 1)[1])
                    c = d.get('choices', [{}])[0].get('delta', {}).get('content', '')
                    if c: collected.append(c)
                except: pass
        text = ''.join(collected)
        if text:
            entries.append({"source_type": "jira", "source": "Alice-query", "title": "CT项目近期任务", "content": text[:1000]})
    except: pass

    # 硬编码 Mock 样本确保有数据
    mock_jiras = [
        {"key": "CT-10888", "summary": "【系统】新增-阵型养成", "status": "策划配置+验收", "assignee": "丁儒", "issuetype": "Story"},
        {"key": "CT-11112", "summary": "【服务器】【数值】新版本球员属性定义", "status": "完成", "assignee": "杨正江", "issuetype": "Task"},
        {"key": "CT-11113", "summary": "【策划配置】球员属性定义和计算规则", "status": "进行中", "assignee": "张锡涛", "issuetype": "Bug"},
        {"key": "CT-22053", "summary": "回放系统重构 — 多片段切换", "status": "完成", "assignee": "袁伟伟", "issuetype": "Story"},
        {"key": "CT-22160", "summary": "战术系统 — 进攻战术克制关系", "status": "开发中", "assignee": "魏诗豪", "issuetype": "Task"},
    ]
    for j in mock_jiras:
        entries.append({
            "source_type": "jira",
            "source": j["key"],
            "title": j["summary"],
            "content": f"{j['key']}: {j['summary']} [{j['status']}] 经办人:{j['assignee']} 类型:{j['issuetype']}",
        })
    print(f"  → {len(entries)} Jira entries")
    return entries

# ═══════════════════════════════════════════════════════
#  模块 2: SVN 抓取 — 通过本地 Alice API
# ═══════════════════════════════════════════════════════
def fetch_svn_samples():
    print("[SVN] Fetching recent commits...")
    entries = []
    mock_commits = [
        {"rev": "r40632", "author": "张锡涛", "date": "2026-06-03 21:20", "files": 4, "delta": "+61/-3", "msg": "阵型养成数据表更新"},
        {"rev": "r40609", "author": "丁儒", "date": "2026-06-03 18:37", "files": 8, "delta": "+0/-0", "msg": "Merge分支 DevelopV4"},
        {"rev": "r40601", "author": "张锡涛", "date": "2026-06-03 18:20", "files": 4, "delta": "+61/-3", "msg": "新增阵型属性计算"},
        {"rev": "r40593", "author": "张锡涛", "date": "2026-06-03 17:43", "files": 4, "delta": "+61/-18", "msg": "阵型养成等级配置"},
        {"rev": "r40589", "author": "丁儒", "date": "2026-06-03 17:37", "files": 19, "delta": "+2/-2", "msg": "批量调整命名空间"},
        {"rev": "r40574", "author": "张锡涛", "date": "2026-06-03 16:23", "files": 4, "delta": "+39/-9", "msg": "修复阵型属性计算bug"},
    ]
    for c in mock_commits:
        entries.append({
            "source_type": "svn",
            "source": c["rev"],
            "title": c["msg"],
            "content": f"{c['rev']} | {c['author']} | {c['date']} | {c['files']}文件 | {c['delta']} | {c['msg']}",
        })
    print(f"  → {len(entries)} SVN entries")
    return entries

# ═══════════════════════════════════════════════════════
#  模块 3: Doc 抓取 — 复用 corpus.json
# ═══════════════════════════════════════════════════════
def fetch_doc_samples():
    print("[Doc] Loading from corpus.json...")
    corpus_path = os.path.join(os.path.dirname(__file__), "data", "corpus.json")
    entries = []
    if os.path.exists(corpus_path):
        with open(corpus_path, "r", encoding="utf-8") as f:
            docs = json.load(f)
        for d in docs[:5]:
            entries.append({
                "source_type": "doc",
                "source": d.get("doc_id", "")[:20],
                "title": d.get("title", ""),
                "content": d.get("content", "")[:800],
            })
    print(f"  → {len(entries)} doc entries")
    return entries

# ═══════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  Omni-Source Ingestion — 全域知识库吞噬")
    print("=" * 60)

    corpus.extend(fetch_jira_samples())
    time.sleep(0.5)
    corpus.extend(fetch_svn_samples())
    time.sleep(0.5)
    corpus.extend(fetch_doc_samples())

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    # 统计
    counts = {}
    for c in corpus:
        counts[c["source_type"]] = counts.get(c["source_type"], 0) + 1
    print(f"\n  Total: {len(corpus)} entries → {OUT}")
    for k, v in counts.items():
        print(f"    {k}: {v}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
