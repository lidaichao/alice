"""
多项目 Jira 运行时配置 — 替代单项目硬编码。
合并顺序: 请求 config > global_config.json > 环境变量 > jira.schema.yaml 默认值
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

logger = logging.getLogger("jira-runtime-config")

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "config", "jira.schema.yaml")


@dataclass
class ProjectJiraConfig:
    project_key: str
    owner_fields: list = field(default_factory=list)
    deadline_field: str = ""


@dataclass
class JiraRuntimeConfig:
    default_project_keys: list = field(default_factory=lambda: ["CT"])
    default_issue_type: str = "Task"
    max_search_results: int = 50
    done_status_keywords: list = field(default_factory=list)
    owner_field_candidates: list = field(default_factory=list)
    projects: dict = field(default_factory=dict)  # str -> ProjectJiraConfig
    field_mappings: dict = field(default_factory=dict)

    def get_project(self, project_key: str) -> ProjectJiraConfig:
        pk = (project_key or "").strip().upper()
        if pk in self.projects:
            return self.projects[pk]
        return ProjectJiraConfig(
            project_key=pk or (self.default_project_keys[0] if self.default_project_keys else "CT"),
            owner_fields=list(self.owner_field_candidates),
        )


def _load_schema_defaults() -> dict:
    try:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"[JiraConfig] schema load failed: {e}")
        return {}


def load_jira_runtime_config(
    frontend_cfg: Optional[dict] = None,
    global_cfg: Optional[dict] = None,
) -> JiraRuntimeConfig:
    frontend_cfg = frontend_cfg or {}
    global_cfg = global_cfg or {}
    schema = _load_schema_defaults()
    defaults = schema.get("defaults") or {}

    proj_env = os.getenv("JIRA_PROJECTS", "")
    proj_keys = []
    raw_projects = frontend_cfg.get("jira_projects") or global_cfg.get("JIRA_PROJECTS") or proj_env
    if raw_projects:
        if isinstance(raw_projects, list):
            proj_keys = [str(p).strip().upper() for p in raw_projects if str(p).strip()]
        else:
            proj_keys = [k.strip().upper() for k in str(raw_projects).replace("，", ",").split(",") if k.strip()]
    if not proj_keys:
        proj_keys = [str(p).upper() for p in (defaults.get("projectKeys") or ["CT"])]

    owner_candidates = list(schema.get("ownerFieldCandidates") or ["任务负责人"])
    fm = global_cfg.get("JIRA_FIELD_MAPPINGS") or global_cfg.get("fieldMappings") or {}
    if isinstance(fm, dict):
        if fm.get("taskOwner"):
            owner_candidates.insert(0, fm["taskOwner"])
        if fm.get("owner"):
            owner_candidates.insert(0, fm["owner"])

    projects: dict = {}
    schema_projects = schema.get("projects") or {}
    cfg_by_proj = global_cfg.get("JIRA_PROJECT_CONFIG") or {}
    if isinstance(cfg_by_proj, dict):
        schema_projects = {**schema_projects, **cfg_by_proj}

    for pk, pdata in schema_projects.items():
        if not isinstance(pdata, dict):
            continue
        projects[str(pk).upper()] = ProjectJiraConfig(
            project_key=str(pk).upper(),
            owner_fields=list(pdata.get("ownerFields") or owner_candidates),
            deadline_field=str(pdata.get("deadlineField") or ""),
        )

    return JiraRuntimeConfig(
        default_project_keys=proj_keys,
        default_issue_type=str(defaults.get("defaultIssueType") or "Task"),
        max_search_results=int(defaults.get("maxSearchResults") or 50),
        done_status_keywords=list(defaults.get("doneStatusKeywords") or []),
        owner_field_candidates=owner_candidates,
        projects=projects,
        field_mappings=fm if isinstance(fm, dict) else {},
    )
