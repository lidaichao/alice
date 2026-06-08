"""GDrive catalog + spreadsheet read helpers (E6 hotfix)."""
from __future__ import annotations

import os
import re
from typing import Callable, Optional

_GDRIVE_ID_RE = re.compile(
    r"(?:spreadsheets/d/|file/d/|open\?id=)([a-zA-Z0-9_-]{10,})"
)
_SPREADSHEET_MIME = "application/vnd.google-apps.spreadsheet"


def parse_gdrive_file_id(text: str) -> str:
    """Extract Drive file id from query or Google Docs/Sheets URL."""
    if not text:
        return ""
    m = _GDRIVE_ID_RE.search(text.strip())
    return m.group(1) if m else ""


def looks_like_gdrive_file_id(text: str) -> bool:
    t = (text or "").strip()
    if parse_gdrive_file_id(t):
        return True
    return bool(re.fullmatch(r"[a-zA-Z0-9_-]{20,}", t))


def extract_catalog_keywords(query: str) -> list[str]:
    q = (query or "").strip()
    kws = [kw for kw in re.split(r"[\s,，、]+", q) if len(kw) >= 2]
    extra: list[str] = []
    for kw in list(kws):
        if re.search(r"[\u4e00-\u9fff]", kw) and len(kw) >= 4:
            extra.extend([kw[i : i + 2] for i in range(len(kw) - 1)])
    return list(dict.fromkeys(kws + extra))


def is_spreadsheet_mime(mime: str) -> bool:
    return "spreadsheet" in (mime or "")


def sheet_range() -> str:
    return os.getenv("GDRIVE_SHEET_RANGE", "A1:Z200").strip() or "A1:Z200"


def values_to_table_text(name: str, values: list, max_chars: int = 8000) -> str:
    if not values:
        return f"# {name}\n\n(表格为空)"
    lines = []
    for row in values[:200]:
        if not isinstance(row, list):
            continue
        cells = [str(c).strip() for c in row if str(c).strip()]
        if cells:
            lines.append(" | ".join(cells))
    body = "\n".join(lines) if lines else "(无有效行)"
    return f"# {name}\n\n{body}"[:max_chars]


def find_row_snippets(values: list, keywords: list[str], max_rows: int = 3) -> str:
    if not values or not keywords:
        return ""
    hits: list[str] = []
    for row in values:
        if not isinstance(row, list):
            continue
        line = " | ".join(str(c) for c in row)
        low = line.lower()
        if any(k.lower() in low for k in keywords):
            hits.append(line[:240])
        if len(hits) >= max_rows:
            break
    return " ; ".join(hits)


def match_files_by_name(files: dict, keywords: list[str], query: str) -> list[dict]:
    if not files:
        return []
    q_low = (query or "").lower()
    if not keywords and not q_low:
        return list(files.values())
    matched = []
    for f in files.values():
        name = f.get("name", "") or ""
        name_low = name.lower()
        if keywords and any(k.lower() in name_low for k in keywords):
            matched.append(f)
            continue
        if len(q_low) >= 3 and q_low in name_low:
            matched.append(f)
            continue
        if len(name_low) >= 3 and name_low in q_low:
            matched.append(f)
    return matched


def fetch_sheet_values(
    file_id: str,
    api_key: str,
    request_fn: Callable,
    proxies: Optional[dict],
    range_a1: Optional[str] = None,
) -> list:
    rng = range_a1 or sheet_range()
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}"
        f"/values/{rng}?key={api_key}"
    )
    r = request_fn("GET", url, proxies=proxies, timeout=15)
    if r.status_code != 200:
        return []
    return r.json().get("values") or []


def enrich_spreadsheet_snippets(
    files: list[dict],
    keywords: list[str],
    api_key: str,
    request_fn: Callable,
    proxies: Optional[dict],
    max_scan: int = 5,
) -> dict[str, str]:
    """file_id -> snippet from row-level keyword hits."""
    out: dict[str, str] = {}
    scanned = 0
    for f in files:
        if not is_spreadsheet_mime(f.get("mimeType", "")):
            continue
        if scanned >= max_scan:
            break
        scanned += 1
        fid = f.get("id", "")
        if not fid:
            continue
        vals = fetch_sheet_values(fid, api_key, request_fn, proxies)
        snippet = find_row_snippets(vals, keywords)
        if snippet:
            out[fid] = snippet[:300]
    return out


def read_gdrive_file_content(
    doc_id: str,
    api_key: str,
    request_fn: Callable,
    proxies: Optional[dict],
) -> tuple[bool, str, str]:
    """
    Returns (ok, llm_text, error_message).
    Spreadsheets use Sheets API; other Google files use Drive export.
    """
    meta_url = (
        f"https://www.googleapis.com/drive/v3/files/{doc_id}"
        f"?key={api_key}&fields=name,mimeType"
    )
    meta_r = request_fn("GET", meta_url, proxies=proxies, timeout=15)
    if meta_r.status_code != 200:
        return False, "", f"文件 {doc_id} 不存在或无权访问"
    meta = meta_r.json()
    mime = meta.get("mimeType", "")
    name = meta.get("name", "未命名")

    if is_spreadsheet_mime(mime):
        vals = fetch_sheet_values(doc_id, api_key, request_fn, proxies)
        if vals:
            return True, values_to_table_text(name, vals), ""
        export_url = (
            f"https://www.googleapis.com/drive/v3/files/{doc_id}"
            f"/export?mimeType=text/csv&key={api_key}"
        )
        cr = request_fn("GET", export_url, proxies=proxies, timeout=20)
        if cr.status_code == 200 and cr.text.strip():
            raw = f"# {name}\n\n{cr.text}"
            return True, raw[:8000], ""
        return False, "", f"表格 {name} 读取失败 (Sheets/Export)"

    export_mime = "text/plain"
    if "document" in mime:
        export_mime = "text/plain"
    export_url = (
        f"https://www.googleapis.com/drive/v3/files/{doc_id}"
        f"/export?mimeType={export_mime}&key={api_key}"
    )
    cr = request_fn("GET", export_url, proxies=proxies, timeout=20)
    if cr.status_code != 200:
        return False, "", f"文件 {name} 导出失败 (HTTP {cr.status_code})"
    raw = f"# {name}\n\n{cr.text}"
    from doc_content_extractor import build_skeleton_from_markdown, should_use_skeleton

    if should_use_skeleton(raw):
        content = build_skeleton_from_markdown(raw, title=name)
    else:
        content = raw[:8000]
    return True, content, ""
