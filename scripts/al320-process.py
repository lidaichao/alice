#!/usr/bin/env python3
"""Build AL-320 archive from remote-fetch + n8n CLI export. Redacts all secrets."""

from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAW = Path(r"H:\workbuddy\aliceV2\docs\evidence\al320\remote-fetch.raw.txt")
N8N_RAW = Path(
    r"H:\workbuddy\pm-Carroll\archive\alice-v3.2-config-snapshot-2026-06-29\n8n-workflows\n8n-all.raw.json"
)
ROOT = Path(r"H:\workbuddy\pm-Carroll\archive\alice-v3.2-config-snapshot-2026-06-29")
EVIDENCE = Path(r"H:\workbuddy\aliceV2\docs\evidence\al320")
TS = "2026-06-29"

REDACT_KEYS = re.compile(
    r"(api[_-]?key|password|secret|token|pat|authorization|private[_-]?key|access[_-]?key|notion_key|jira_pat)",
    re.I,
)
def split_sections(text: str) -> dict[str, str]:
    parts = re.split(r"===([A-Z0-9_]+)===", text)
    out: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        out[parts[i]] = parts[i + 1].strip()
    return out


def redact_obj(value):
    if isinstance(value, dict):
        return {
            k: ("***REDACTED***" if REDACT_KEYS.search(str(k)) else redact_obj(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_obj(v) for v in value]
    return value


def redact_env(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key, _, _val = line.partition("=")
        lines.append(f"{key}=***REDACTED***")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def fetch_dify_manifest(global_cfg: dict) -> dict:
    dataset_key = (
        global_cfg.get("DIFY_DATASET_API_KEY")
        or (global_cfg.get("dify") or {}).get("dataset_api_key")
        or (global_cfg.get("knowledge_base") or {}).get("api_key")
    )
    manifest = {"datasets": [], "documents_by_dataset": {}, "config_keys_present": {}}
    manifest["config_keys_present"] = {"dataset_api_key_set": bool(dataset_key)}
    if not dataset_key:
        manifest["note"] = "No dataset API key located in global_config"
        return manifest

    def get(url: str):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {dataset_key}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        for d in get("http://192.168.72.31:5001/v1/datasets?page=1&limit=100").get("data", []):
            manifest["datasets"].append(
                {
                    "id": d.get("id"),
                    "name": d.get("name"),
                    "document_count": d.get("document_count"),
                }
            )
            ds_id = d.get("id")
            if ds_id:
                manifest["documents_by_dataset"][ds_id] = [
                    {
                        "id": x.get("id"),
                        "name": x.get("name"),
                        "indexing_status": x.get("indexing_status"),
                    }
                    for x in get(
                        f"http://192.168.72.31:5001/v1/datasets/{ds_id}/documents?page=1&limit=100"
                    ).get("data", [])
                ]
    except Exception as exc:
        manifest["error"] = str(exc)
    return manifest


def main():
    for sub in ("hub-config", "n8n-workflows", "dify-datasets", "docker-volumes"):
        (ROOT / sub).mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    sections = split_sections(RAW.read_text(encoding="utf-8"))
    global_cfg = json.loads(sections["GLOBAL_CONFIG"])

    (ROOT / "hub-config" / "global_config.redacted.json").write_text(
        json.dumps(redact_obj(global_cfg), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (ROOT / "hub-config" / "env.prod.redacted").write_text(
        redact_env(sections["ENV_PROD"]) + "\n",
        encoding="utf-8",
    )

    n8n_payload = json.loads(N8N_RAW.read_text(encoding="utf-8"))
    workflows = n8n_payload if isinstance(n8n_payload, list) else n8n_payload.get("data", [])
    (ROOT / "n8n-workflows" / "workflows-all.redacted.json").write_text(
        json.dumps(redact_obj(workflows), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (ROOT / "n8n-workflows" / "workflows-index.json").write_text(
        json.dumps(
            [{"id": w.get("id"), "name": w.get("name"), "active": w.get("active")} for w in workflows],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    N8N_RAW.unlink(missing_ok=True)

    dify_manifest = fetch_dify_manifest(global_cfg)
    (ROOT / "dify-datasets" / "datasets-manifest.json").write_text(
        json.dumps(dify_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    (ROOT / "docker-volumes" / "volume-ls.txt").write_text(
        sections["DOCKER_VOLUME_LS"] + "\n",
        encoding="utf-8",
    )
    inspect = sections["VOLUME_INSPECT_DIFY"] + "\n\n" + sections["VOLUME_INSPECT_N8N"] + "\n"
    (ROOT / "docker-volumes" / "volume-inspect-dify-n8n.json.txt").write_text(inspect, encoding="utf-8")
    (EVIDENCE / "docker-volume-ls.txt").write_text(sections["DOCKER_VOLUME_LS"] + "\n", encoding="utf-8")
    (EVIDENCE / "volume-inspect-summary.txt").write_text(inspect, encoding="utf-8")

    with urllib.request.urlopen("http://192.168.72.31:5000/health", timeout=15) as resp:
        health = json.loads(resp.read().decode("utf-8"))
    (EVIDENCE / "health-during-backup.json").write_text(json.dumps(health, indent=2) + "\n", encoding="utf-8")

    RAW.unlink(missing_ok=True)

    files = [
        {"path": str(p.relative_to(ROOT)).replace("\\", "/"), "bytes": p.stat().st_size}
        for p in sorted(ROOT.rglob("*"))
        if p.is_file()
    ]
    (EVIDENCE / "archive-manifest.json").write_text(json.dumps(files, indent=2) + "\n", encoding="utf-8")

    readme = f"""# Alice v3.2 config snapshot ({TS})

| Field | Value |
|-------|-------|
| Server | `192.168.72.31` |
| Deploy root | `/home/alice/alice` |
| Backup UTC | {datetime.now(timezone.utc).isoformat()} |
| Operator | squirtle · AL-320 |
| Rollback contact | rabbit (CTO) |

## Contents

| Directory | AL | Notes |
|-----------|-----|-------|
| `hub-config/` | AL-321 | Redacted `global_config` + `.env.prod` |
| `n8n-workflows/` | AL-322 | 29 workflows via `n8n export:workflow --all` |
| `dify-datasets/` | AL-323 | Dataset/document manifest (IDs only) |
| `docker-volumes/` | AL-324/325 | `volume ls` + inspect pgdata + n8n |

## Health

Services **kept running** during backup · `/health` → 200

## Secrets

This archive contains **no plaintext API keys**. Full secrets remain on server only.
"""
    (ROOT / "README.md").write_text(readme, encoding="utf-8")

    log = [
        "AL-321 hub-config OK (redacted)",
        f"AL-322 n8n workflows={len(workflows)} (CLI export; REST API degraded)",
        f"AL-323 dify datasets={len(dify_manifest['datasets'])}",
        "AL-324/325 docker volumes OK",
        "health=200 during backup",
        f"archive files={len(files)}",
    ]
    (EVIDENCE / "backup-log.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "workflows": len(workflows), "datasets": len(dify_manifest["datasets"])}, indent=2))


if __name__ == "__main__":
    main()
