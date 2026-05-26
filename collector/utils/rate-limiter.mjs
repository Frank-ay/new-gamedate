// 请求限速：固定延迟 + 随机抖动 + 指数退避重试
export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export async function throttledCall(fn, delayMs = 1500) {
  const jitter = (Math.random() - 0.5) * 1000; // ±500ms 抖动
  await sleep(Math.max(500, delayMs + jitter));
  return fn();
}

export async function withRetry(fn, maxRetries = 3, label = '') {
  let lastError;
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;
      if (attempt < maxRetries) {
        const backoff = Math.pow(2, attempt) * 1000; // 2s / 4s / 8s
        console.warn(`[retry ${attempt}/${maxRetries}] ${label}: ${err.message}, waiting ${backoff}ms`);
        await sleep(backoff);
      }
    }
  }
  throw lastError;
}
