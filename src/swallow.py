# v36.0 (2026-10-05) — 36aigame
# 用法: except Exception as e: swallow("tag", e)
import time

_last = {}

def swallow(tag, exc, rate=3600):
    now = time.time()
    if now - _last.get(tag, 0) < rate:
        return
    _last[tag] = now
    print(f"[SWALLOWED] {tag}: {type(exc).__name__}: {exc}", flush=True)
