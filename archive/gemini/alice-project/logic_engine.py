"""
逻辑断言引擎 — 白泽风格领域规则判定
在 FC 调用前，用正则匹配判断用户意图，产出分类结果和推荐动作
"""
import os, re, yaml, logging

logger = logging.getLogger(__name__)

ASSERTIONS_DIR = os.path.join(os.path.dirname(__file__), 'logic', 'assertions')

class LogicEngine:
    def __init__(self):
        self.rules = []
        self._load_rules()
    
    def _load_rules(self):
        if not os.path.exists(ASSERTIONS_DIR):
            logger.warning(f"[Logic] Assertions dir not found: {ASSERTIONS_DIR}")
            return
        for fname in os.listdir(ASSERTIONS_DIR):
            if fname.endswith('.yaml'):
                try:
                    with open(os.path.join(ASSERTIONS_DIR, fname), 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                    for rule in config.get('rules', []):
                        rule['category'] = config.get('category', 'general')
                        rule['file'] = fname
                        self.rules.append(rule)
                except Exception as e:
                    logger.error(f"[Logic] Failed to load {fname}: {e}")
        logger.info(f"[Logic] Loaded {len(self.rules)} assertion rules from {len(os.listdir(ASSERTIONS_DIR))} files")
    
    def evaluate(self, text: str) -> dict:
        """评估用户输入，返回最佳匹配规则和推荐动作"""
        best_match = None
        best_score = 0
        
        for rule in self.rules:
            pattern = rule.get('pattern', '')
            if not pattern:
                continue
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    score = rule.get('score', 0.5)
                    if score > best_score:
                        best_score = score
                        best_match = {
                            'rule': rule['name'],
                            'category': rule['category'],
                            'score': score,
                            'action': rule.get('action', 'allow'),
                            'message': rule.get('message', ''),
                            'recommend_tool': rule.get('recommend_tool'),
                        }
            except re.error as e:
                logger.warning(f"[Logic] Invalid pattern '{pattern}': {e}")
        
        return best_match or {'rule': 'none', 'category': 'general', 'score': 0, 'action': 'allow'}

_engine = LogicEngine()

def evaluate_intent(text: str) -> dict:
    """快捷评估函数"""
    result = _engine.evaluate(text)
    logger.info(f"[Logic] Intent: {result['rule']} ({result['category']}) score={result['score']} action={result['action']}")
    return result

def reload_rules():
    """热重载断言规则"""
    _engine._load_rules()
    return {"ok": True, "rules_loaded": len(_engine.rules)}
