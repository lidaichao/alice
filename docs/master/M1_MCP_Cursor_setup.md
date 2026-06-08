# M1 — Hub MCP（Cursor 接入）

## HTTP（集成测试 / 脚本）

```bash
curl http://127.0.0.1:9099/mcp/v1/tools
curl -X POST http://127.0.0.1:9099/mcp/v1/tools/query_jira_metadata \
  -H "Content-Type: application/json" \
  -d '{"arguments":{"issue_key":"CT-11152"}}'
```

```powershell
$env:ALICE_RUN_INTEGRATION='1'; $env:ALICE_RUN_MCP='1'
py -3 scripts/ci_gate.py
```

## stdio（Cursor MCP）

```json
{
  "mcpServers": {
    "alice-hub": {
      "command": "py",
      "args": ["-3", "H:/workbuddy/alice/backend/hub_mcp_server.py"]
    }
  }
}
```

写操作工具 **不** 暴露于 MCP；Jira 写须经 `operation_id` + HITL 确认卡。
