# Alice KB Regression Report

> Generated: 2026-06-05 01:59:45
> Backend: http://127.0.0.1:9099
> Dataset: testset_kb_matrix.csv (9 rows, 9 live)

## Summary

| Tier | Result |
|------|--------|
| Tier1 offline | 0/0 |
| Tier2 live lane | 8/9 |
| Tier3 LLM judge | 0/0 |
| **Overall live PASS** | **8/9** |

## Failed cases

### coord-004
- **Q:** 请把 CT-10859 状态改成处理中
- **Mode:** oracle_struct
- **Failures:** stream error: HTTPConnectionPool(host='127.0.0.1', port=9099): Read timed out. (read timeout=180)

## Tier1 details


## Tier2 all

| id | pass | plugins | failures |
|----|:----:|---------|----------|
| coord-001 | Y | get_issue_commits |  |
| coord-002 | Y | get_issue_commits,get_single_commit_diff |  |
| coord-003 | Y | search_jira_issues |  |
| coord-004 | N |  | stream error: HTTPConnectionPool(host='127.0.0.1', port=9099): Read timed out. ( |
| coord-005 | Y | read_specific_doc,search_docs_catalog |  |
| coord-006 | Y | read_specific_doc,search_docs_catalog |  |
| coord-007 | Y | search_docs_catalog |  |
| coord-008 | Y | get_issue_commits,search_docs_catalog |  |
| coord-009 | Y | get_issue_commits |  |