# Alice 发版自动化门禁（复制为 release_YYYY-MM-DD.md）

> **无人工签字**。勾选仅记录命令是否已跑通。

- [ ] `py -3 backend/intent_classifier.py` 全绿
- [ ] `py -3 scripts/validate_kb_matrix_yaml.py` → OK
- [ ] `py -3 scripts/ci_gate.py` → `CI_GATE_OK`
- [ ] （Hub 在线）`set ALICE_RUN_INTEGRATION=1` 后 ci_gate 含 smoke + e2e
- [ ] （可选）`py -3 backend/run_eval.py coordinator_m1` 不低于 `coordinator_baseline_M1.md`
