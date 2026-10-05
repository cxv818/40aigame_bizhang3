# v36.0 (2026-10-05) — 36aigame
# 五处调用点(AIDirector._query / _send_enhanced_request / 军师_ask_llm /
# 选计器_worker / 进化复盘worker)统一走这里, 便于监控与未来换模型。
import json
import threading
import time
import urllib.request

_stats = {}          # port -> {calls, fails, total_ms}
_lock = threading.Lock()


def _record(port, ms, ok):
    with _lock:
        s = _stats.setdefault(port, {"calls": 0, "fails": 0, "total_ms": 0.0})
        s["calls"] += 1
        s["total_ms"] += ms
        if not ok:
            s["fails"] += 1


def ask(port, prompt=None, max_tokens=800, temperature=0.7, timeout=25,
        retries=0, messages=None):
    """调用 llama-server OpenAI 兼容接口。返回 (text, latency_s)。

    - prompt: 单轮用户消息; 或传 messages=完整消息数组(二选一)
    - enable_thinking=false + reasoning_content 兜底(内置, 原逻辑等价)
    - 失败重试 retries 次; 全失败抛最后一个异常(调用方自行降级)
    """
    if messages is None:
        messages = [{"role": "user", "content": prompt}]
    body = json.dumps({
        "messages": messages,
        "max_tokens": max_tokens, "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode("utf-8")
    last_exc = None
    for _attempt in range(retries + 1):
        t0 = time.time()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            msg = data["choices"][0]["message"]
            text = msg.get("content", "") or msg.get("reasoning_content", "") or ""
            _record(port, (time.time() - t0) * 1000, ok=True)
            return text, time.time() - t0
        except Exception as e:
            last_exc = e
            _record(port, (time.time() - t0) * 1000, ok=False)
    raise last_exc


def health():
    """给 self_check 用: {port: {calls, fails, fail_rate, avg_ms}}"""
    with _lock:
        out = {}
        for p, s in _stats.items():
            calls = max(1, s["calls"])
            out[str(p)] = {"calls": s["calls"], "fails": s["fails"],
                           "fail_rate": round(s["fails"] / calls, 2),
                           "avg_ms": round(s["total_ms"] / calls)}
        return out
