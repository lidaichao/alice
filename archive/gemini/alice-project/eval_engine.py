"""
Agent 评估引擎 — Benchmark + Dataset + Eval
类似 LobeHub 的 agentEval 系统：运行测试用例，自动评分，产出报告
"""
import os, re, json, time, yaml, logging, requests

logger = logging.getLogger(__name__)

EVAL_DIR = os.path.join(os.path.dirname(__file__), 'eval')
DATASETS_DIR = os.path.join(EVAL_DIR, 'datasets')

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
        }
        
        self.results_store[run_id] = report
        return report
    
    def _evaluate_case(self, tc, rubric, user_config):
        """评估单个测试用例"""
        question = tc.get("input", "")
        expected = tc.get("expected_keywords", [])
        min_score = tc.get("min_score", 50)
        category = tc.get("category", "general")
        
        # 发送到 Agent 获取回答
        start = time.time()
        try:
            r = requests.post(f"{self.base_url}/v1/chat/completions", json={
                "messages": [{"role": "user", "content": question}],
                "user_config": user_config or {}
            }, stream=True, timeout=30)
            answer = ""
            for line in r.iter_lines():
                if line and b'data:' in line[:10]:
                    try:
                        j = json.loads(line[6:].decode('utf-8','ignore'))
                        c = j.get('choices',[{}])[0].get('delta',{}).get('content','')
                        if c and '[DONE]' not in str(c):
                            answer += c
                    except: pass
                if line == b'data: [DONE]':
                    break
            latency = round((time.time() - start) * 1000)
        except Exception as e:
            return {"id": tc["id"], "passed": False, "score": 0, "answer": "", 
                    "error": str(e), "latency_ms": 0, "category": category}
        
        # 评分：关键词匹配
        match_count = sum(1 for kw in expected if kw.lower() in answer.lower())
        keyword_score = int(match_count / max(len(expected), 1) * 100)
        
        # 长度加分
        length_bonus = min(len(answer.split()) / 20 * 10, 10) if len(answer) > 10 else 0
        
        score = min(int(keyword_score + length_bonus), 100)
        passed = score >= min_score
        
        return {
            "id": tc["id"],
            "passed": passed,
            "score": score,
            "min_score": min_score,
            "answer": answer[:500],
            "answer_length": len(answer),
            "matched_keywords": [kw for kw in expected if kw.lower() in answer.lower()],
            "latency_ms": latency,
            "category": category,
        }

_engine = EvalEngine()

def run_evaluation(dataset_name, user_config=None):
    return _engine.run_benchmark(dataset_name, user_config)

def list_eval_datasets():
    return _engine.list_datasets()

def get_eval_result(run_id):
    return _engine.results_store.get(run_id)
