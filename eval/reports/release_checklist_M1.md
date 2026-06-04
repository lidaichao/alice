# Alice 发版勾选单 — M1

复制本模板到 `eval/reports/release_YYYY-MM-DD.md` 并逐项勾选。

- [ ] `py -3 backend/intent_classifier.py` 全绿
- [ ] `py -3 scripts/validate_kb_matrix_yaml.py` → OK
- [ ] `py -3 scripts/smoke_chat_only.py` → `SMOKE_CHAT_ONLY_OK`（Hub 9099）
- [ ] `py -3 scripts/e2e_short_draft_memory.py` → `E2E_SHORT_OK`
- [ ] `py -3 backend/run_eval.py coordinator_m1` 不低于 M1 基线（见 `coordinator_baseline_M1.md`）
- [ ] 灰盒 SOP 第四节场景人工点验
- [ ] Admin Jira「测试连接」502/401/超时文案已 spot-check

**签字**：________ **日期**：________
