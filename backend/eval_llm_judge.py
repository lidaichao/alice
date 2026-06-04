"""
LLM-as-a-Judge for EvalEngine — replaces keyword substring scoring.
"""
from __future__ import annotations

import json
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

JUDGE_SYSTEM = """你是 Alice 评测裁判。根据用户问题、期望要点与 Alice 的实际回答，给出客观分数。

评分规则：
- 0-40：答非所问、空答、明显编造、或未尝试解决
- 41-69：部分相关但遗漏关键期望要点
- 70-89：基本满足期望要点，有小瑕疵可接受
- 90-100：完整、忠实、结构清晰地满足期望

「期望要点」是验收参考，不要求逐字出现，但语义须覆盖。
若回答明确说明无法完成且理由合理，可给 50-70（视问题而定）。

只输出 JSON，不要 markdown 围栏：
{"score": <0-100 整数>, "reason": "<一句中文理由>"}"""


def _resolve_api_key(user_config: dict | None) -> str:
    cfg = user_config or {}
    key = (
        cfg.get("deepseek_key")
        or cfg.get("ai_api_key")
        or os.getenv("DEEPSEEK_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or ""
    )
    if key:
        return key.strip()
    try:
        path = os.path.join(os.path.dirname(__file__), "global_config.json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return (data.get("DEEPSEEK_KEY") or "").strip()
    except Exception:
        pass
    return ""


def _parse_judge_json(content: str) -> dict:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def judge_eval_case(
    question: str,
    expected_keywords: list,
    answer: str,
    *,
    user_config: dict | None = None,
    category: str = "",
) -> dict:
    """
    Call DeepSeek (temperature 0.0) → {"score": int, "reason": str}.
    """
    key = _resolve_api_key(user_config)
    if not key:
        return {"score": 0, "reason": "DEEPSEEK_KEY 未配置，无法启用 LLM 裁判"}

    expectations = [k for k in (expected_keywords or []) if k and str(k).strip()]
    exp_block = "\n".join(f"- {k}" for k in expectations) if expectations else "（无明确要点，按问题相关性评分）"

    user_prompt = (
        f"【类别】{category or 'general'}\n"
        f"【用户问题】\n{question[:2000]}\n\n"
        f"【期望要点】\n{exp_block}\n\n"
        f"【Alice 实际回答】\n{(answer or '(empty)')[:4000]}"
    )

    try:
        resp = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": (user_config or {}).get("deepseek_model") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat",
                "messages": [
                    {"role": "system", "content": JUDGE_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 300,
            },
            timeout=45,
        )
        resp.raise_for_status()
        content = (
            resp.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed = _parse_judge_json(content)
        score = int(parsed.get("score", 0))
        score = max(0, min(100, score))
        return {"score": score, "reason": str(parsed.get("reason", ""))[:500]}
    except Exception as e:
        logger.warning(f"[EvalJudge] LLM judge failed: {e}")
        return {"score": 0, "reason": f"LLM 裁判调用失败: {e}"}
