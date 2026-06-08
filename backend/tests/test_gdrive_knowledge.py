#!/usr/bin/env python3
"""Unit tests for gdrive_knowledge (no network)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gdrive_knowledge import (
    extract_catalog_keywords,
    find_row_snippets,
    match_files_by_name,
    parse_gdrive_file_id,
    values_to_table_text,
)


class _Resp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_parse_gdrive_file_id():
    url = "https://docs.google.com/spreadsheets/d/abc123XYZ_abcdefghij/edit#gid=0"
    assert parse_gdrive_file_id(url) == "abc123XYZ_abcdefghij"


def test_match_files_by_name_and_rows():
    files = {
        "1": {"id": "1", "name": "球员配置表", "mimeType": "application/vnd.google-apps.spreadsheet"},
        "2": {"id": "2", "name": "无关文档", "mimeType": "application/vnd.google-apps.document"},
    }
    kws = extract_catalog_keywords("球员配置")
    matched = match_files_by_name(files, kws, "球员配置")
    assert len(matched) == 1
    assert matched[0]["id"] == "1"

    vals = [["姓名", "数值"], ["射门", "88"], ["传球", "70"]]
    snip = find_row_snippets(vals, ["射门"])
    assert "射门" in snip and "88" in snip

    text = values_to_table_text("测试表", vals)
    assert "射门" in text and "88" in text


def test_read_spreadsheet_via_sheets_api():
    from gdrive_knowledge import read_gdrive_file_content

    def fake_request(method, url, proxies=None, timeout=15):
        if "drive/v3/files/sheet1" in url and "fields=" in url:
            return _Resp(200, {"name": "表A", "mimeType": "application/vnd.google-apps.spreadsheet"})
        if "sheets.googleapis.com" in url:
            return _Resp(200, {"values": [["列1", "列2"], ["foo", "bar"]]})
        return _Resp(404)

    ok, content, err = read_gdrive_file_content("sheet1", "KEY", fake_request, None)
    assert ok, err
    assert "foo" in content and "bar" in content


if __name__ == "__main__":
    test_parse_gdrive_file_id()
    test_match_files_by_name_and_rows()
    test_read_spreadsheet_via_sheets_api()
    print("test_gdrive_knowledge OK")
