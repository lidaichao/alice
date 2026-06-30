/**
 * 认证端点限速中间件
 *
 * 纯 Node.js 内存计数器，不引入 Redis。
 * - register：同一 IP 3 次/60s
 * - login：同一 IP 5 次/10s
 *
 * 超限返回 HTTP 429 + { retryAfter, message }，告知而非惩罚。
 */

const COUNTERS = new Map();

/**
 * @param {'register'|'login'} endpoint
 */
function rateLimiter(endpoint) {
  const limits = {
    register: { max: 3, windowMs: 60 * 1000 },
    login:    { max: 5, windowMs: 10 * 1000 }
  };

  const config = limits[endpoint];
  if (!config) {
    throw new Error(`Unknown rate-limit endpoint: ${endpoint}`);
  }

  return (req, res, next) => {
    const ip = req.ip || req.connection.remoteAddress || 'unknown';
    const key = `${endpoint}:${ip}`;
    const now = Date.now();

    let entry = COUNTERS.get(key);
    if (!entry || now - entry.windowStart > config.windowMs) {
      entry = { windowStart: now, count: 0 };
      COUNTERS.set(key, entry);
    }

    entry.count++;

    if (entry.count > config.max) {
      const elapsed = now - entry.windowStart;
      const retryAfter = Math.ceil((config.windowMs - elapsed) / 1000);
      res.status(429).json({
        ok: false,
        error: {
          code: 'RATE_LIMITED',
          message: `操作太快，请 ${retryAfter} 秒后再试`,
          retryAfter
        }
      });
      return;
    }

    next();
  };
}

// 定时清理过期计数器（60s 一次）
setInterval(() => {
  const now = Date.now();
  // Max window across all endpoints
  const MAX_WINDOW = 60 * 1000;
  for (const [key, entry] of COUNTERS) {
    if (now - entry.windowStart > MAX_WINDOW) {
      COUNTERS.delete(key);
    }
  }
}, 60 * 1000).unref();

function resetCounters() {
  COUNTERS.clear();
}

module.exports = { rateLimiter, resetCounters };
