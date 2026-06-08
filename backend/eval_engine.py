"""
Agent 评估引擎 — Benchmark + Dataset + Eval
类似 LobeHub 的 agentEval 系统：运行测试用例，LLM-as-a-Judge 评分，产出报告
"""
import os, json, time, yaml, logging, requests, sys

logger = logging.getLogger(__name__)

EVAL_DIR = os.path.join(os.path.dirname(__file__), 'eval')
DATASETS_DIR = os.path.join(EVAL_DIR, 'datasets')
_REPO_EVAL = os.path.join(os.path.dirname(__file__), '..', 'eval')
if os.path.isdir(_REPO_EVAL) and _REPO_EVAL not in sys.path:
    sys.path.insert(0, os.path.normpath(_REPO_EVAL))

try:
    from lib.sse_collect import stream_chat as _sse_stream_chat
    from lib.oracle_assert import split_semicolon_list
    _HAS_SSE_LIB = True
except ImportError:
    _HAS_SSE_LIB = False

from eval_llm_judge import judge_eval_case


class EvalEngine:
    def __init__(self, base_url="http://127.0.0.1:9099"):
        self.base_url = base_url
        self.results_store = {}
    
    def list_datasets(self):
        files = [f for f in os.listdir(DATASETS_DIR) if f.endswith('.yaml')]
        datasets = []
        for f in files:
            with open(os.path.join(DATASETS_DIR, f), 'r', encoding='utf-8') as fp:
                d = yaml.safe_load(fp)
                datasets.append({"file": f, "name": d.get("name", f), "cases": len(d.get("test_cases", []))})
        return datasets
    
    def run_benchmark(self, dataset_name, user_config=None):
        """对指定数据集运行评估"""
        fname = dataset_name if dataset_name.endswith('.yaml') else f"{dataset_name}.yaml"
        path = os.path.join(DATASETS_DIR, fname)
        if not os.path.exists(path):
            return {"error": f"Dataset not found: {fname}"}
        
        with open(path, 'r', encoding='utf-8') as f:
            dataset = yaml.safe_load(f)
        
        test_cases = dataset.get("test_cases", [])
        rubric = dataset.get("rubric", {})
        run_id = f"eval-{int(time.time())}"
        
        results = []
        total_score = 0
        
        for tc in test_cases:
            case_result = self._evaluate_case(tc, rubric, user_config)
            results.append(case_result)
            total_score += case_result.get("score", 0)
        
        avg_score = total_score / len(test_cases) if test_cases else 0
        passed = sum(1 for r in results if r.get("passed"))
        
        report = {
            "run_id": run_id,
            "dataset": dataset_name,
            "total_cases": len(test_cases),
            "passed": passed,
            "failed": len(test_cases) - passed,
            "avg_score": round(avg_score, 1),
            "rubric": rubric,
            "results": results,
            "timestamp": time.time(),
            "judge_mode": "llm",
        }
        
        self.results_store[run_id] = report
        return report
    
    def _evaluate_case(self, tc, rubric, user_config):
        """评估单个测试用例 — LLM-as-a-Judge（插件约束仍为结构化 oracle）"""
        question = tc.get("input", "")
        expected = tc.get("expected_keywords", [])
        min_score = tc.get("min_score", 50)
        category = tc.get("category", "general")
        expected_plugins = tc.get("expected_plugins") or []
        forbidden_plugins = tc.get("forbidden_plugins") or []
        if isinstance(expected_plugins, str):
            expected_plugins = split_semicolon_list(expected_plugins) if _HAS_SSE_LIB else [expected_plugins]
        if isinstance(forbidden_plugins, str):
            forbidden_plugins = split_semicolon_list(forbidden_plugins) if _HAS_SSE_LIB else [forbidden_plugins]

        start = time.time()
        plugins_seen = []
        try:
            if _HAS_SSE_LIB:
                stream = _sse_stream_chat(
                    question,
                    base_url=self.base_url,
                    config=user_config or {},
                    timeout=120,
                )
                answer = stream.get("content") or ""
                plugins_seen = sorted(stream.get("plugins_seen") or [])
                latency = round((time.time() - start) * 1000)
                if stream.get("error"):
                    return {
                        "id": tc.get("id"),
                        "passed": False,
                        "score": 0,
                        "answer": "",
                        "error": stream["error"],
                        "latency_ms": latency,
                        "category": category,
                        "judge_reason": stream["error"],
                    }
            else:
                r = requests.post(f"{self.base_url}/v1/chat/completions", json={
                    "messages": [{"role": "user", "content": question}],
                    "user_config": user_config or {}
                }, stream=True, timeout=120)
                answer = ""
                for line in r.iter_lines():
                    if line and b'data:' in line[:10]:
                        try:
                            j = json.loads(line[6:].decode('utf-8', 'ignore'))
                            c = j.get('choices', [{}])[0].get('delta', {}).get('content', '')
                            if c and '[DONE]' not in str(c):
                                answer += c
                            if j.get("custom_type") == "plugin_state":
                                pname = (j.get("plugin") or {}).get("name")
                                if pname and pname not in plugins_seen:
                                    plugins_seen.append(pname)
                        except Exception:
                            pass
                    if line == b'data: [DONE]':
                        break
                latency = round((time.time() - start) * 1000)
        except Exception as e:
            return {
                "id": tc.get("id"),
                "passed": False,
                "score": 0,
                "answer": "",
                "error": str(e),
                "latency_ms": 0,
                "category": category,
                "judge_reason": str(e),
            }

        if tc.get("expect_confirm_card"):
            if stream.get("confirm_card") if _HAS_SSE_LIB else False:
                return {
                    "id": tc.get("id"),
                    "passed": True,
                    "score": 100,
                    "min_score": min_score,
                    "answer": (answer or "")[:500],
                    "answer_length": len(answer or ""),
                    "judge_reason": "HITL confirm_card emitted (no direct Jira write)",
                    "expected_keywords": expected,
                    "plugins_seen": plugins_seen,
                    "plugin_ok": True,
                    "plugin_note": "",
                    "latency_ms": latency,
                    "category": category,
                    "judge_mode": "oracle",
                }
            return {
                "id": tc.get("id"),
                "passed": False,
                "score": 0,
                "min_score": min_score,
                "answer": (answer or "")[:500],
                "judge_reason": "expect_confirm_card: no confirm_card in SSE",
                "plugins_seen": plugins_seen,
                "latency_ms": latency,
                "category": category,
                "judge_mode": "oracle",
            }

        plugin_ok = True
        plugin_note = ""
        if expected_plugins or forbidden_plugins:
            seen = set(plugins_seen)
            bad = [p for p in forbidden_plugins if p in seen]
            if bad:
                plugin_ok = False
                plugin_note = f"forbidden: {bad}"
            elif expected_plugins and not any(p in seen for p in expected_plugins):
                plugin_ok = False
                plugin_note = f"expected one of {expected_plugins}, got {plugins_seen}"

        verdict = judge_eval_case(
            question,
            expected if isinstance(expected, list) else [expected],
            answer,
            user_config=user_config,
            category=category,
        )
        score = int(verdict.get("score", 0))
        if not plugin_ok:
            score = min(score, 40)
        passed = score >= min_score and plugin_ok

        return {
            "id": tc.get("id"),
            "passed": passed,
            "score": score,
            "min_score": min_score,
            "answer": answer[:500],
            "answer_length": len(answer),
            "judge_reason": verdict.get("reason", ""),
            "expected_keywords": expected,
            "plugins_seen": plugins_seen,
            "plugin_ok": plugin_ok,
            "plugin_note": plugin_note,
            "latency_ms": latency,
            "category": category,
            "judge_mode": "llm",
        }

_engine = EvalEngine()

def run_evaluation(dataset_name, user_config=None):
    return _engine.run_benchmark(dataset_name, user_config)

def list_eval_datasets():
    return _engine.list_datasets()

def get_eval_result(run_id):
    return _engine.results_store.get(run_id)
