# Alice KB Regression Report

> Generated: 2026-06-05 00:34:33
> Backend: http://127.0.0.1:9099
> Dataset: testset_kb_matrix.csv (9 rows, 9 live)

## Summary

| Tier | Result |
|------|--------|
| Tier1 offline | 0/0 |
| Tier2 live lane | 9/9 |
| Tier3 LLM judge | 0/0 |
| **Overall live PASS** | **9/9** |

## Tier1 details


## Tier2 all

| id | pass | plugins | failures |
|----|:----:|---------|----------|
| coord-001 | Y | get_issue_commits |  |
| coord-002 | Y | get_issue_commits |  |
| coord-003 | Y | jira_structured_search |  |
| coord-004 | Y | query_jira_metadata |  |
| coord-005 | Y | read_specific_doc,search_docs_catalog |  |
| coord-006 | Y | read_specific_doc,search_docs_catalog |  |
| coord-007 | Y | read_specific_doc,search_docs_catalog |  |
| coord-008 | Y | get_issue_commits |  |
| coord-009 | Y | get_issue_commits |  |