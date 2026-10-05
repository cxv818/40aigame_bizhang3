# v36.0 (2026-10-05) — 36aigame
# 版本: v20.0 (2025-10-03)
#!/usr/bin/env bash
# ============ 11aigame 一键启动 ============
# 版本: v20.0 (2025-10-03)
# 更新: 高级集群作战调度系统
# 顺序敏感: 三帅 LLM -> 军师 -> Laya -> 游戏 -> pilot -> 监控
# 用法: ./scripts/start_all.sh [--no-pilot] [--no-monitor] [--no-advisor] [--no-laya]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../config/env.sh
source "$ROOT/config/env.sh"

NO_PILOT=0; NO_MON=0; NO_ADVISOR=0; NO_LAYA=0
for a in "$@"; do
  case "$a" in
    --no-pilot) NO_PILOT=1 ;;
    --no-monitor) NO_MON=1 ;;
    --no-advisor) NO_ADVISOR=1 ;;
    --no-laya) NO_LAYA=1 ;;
  esac
done

# X 授权 (Wayland/mutter 环境后台启动 pygame 必需)
if [ -z "${DISPLAY:-}" ]; then export DISPLAY=:0; fi
XAUTH="$(ls /run/user/$(id -u)/.mutter-Xwaylandauth.* 2>/dev/null | head -1 || true)"
[ -n "$XAUTH" ] && export XAUTHORITY="$XAUTH"

echo "==> [1/6] 魏军三帅 35B (端口 $TANK_AI_PORT_1/$TANK_AI_PORT_2/$TANK_AI_PORT_3)"
i=0
for P in "$TANK_AI_PORT_1" "$TANK_AI_PORT_2" "$TANK_AI_PORT_3"; do
  i=$((i+1))
  if curl -s -m 2 "http://127.0.0.1:$P/health" 2>/dev/null | grep -q '"status":"ok"'; then
    echo "    port $P 已在跑,跳过"; continue
  fi
  GPU_VAR="TANK_GPU_$i"; GPU="${!GPU_VAR:-$((i-1))}"
  HIP_VISIBLE_DEVICES="$GPU" setsid nohup "$LLAMA_SERVER_BIN" \
    -m "$TANK_MODEL" --host 127.0.0.1 --port "$P" \
    -ngl "$TANK_NGL" -c "$TANK_CTX" --parallel 1 \
    >> "$TANK_RUNTIME_DIR/llama_$P.log" 2>&1 < /dev/null &
  echo "    port $P launching (GPU $GPU)"
done

echo "==> [2/6] 吕布 35B 军师 (端口 $TANK_ADVISOR_PORT, exps=CPU 共卡方案)"
if [ "$NO_ADVISOR" = "0" ]; then
  if curl -s -m 2 "http://127.0.0.1:$TANK_ADVISOR_PORT/health" 2>/dev/null | grep -q '"status":"ok"'; then
    echo "    port $TANK_ADVISOR_PORT 已在跑,跳过"
  else
    HIP_VISIBLE_DEVICES="$TANK_ADVISOR_GPU" setsid nohup "$LLAMA_SERVER_BIN" \
      -m "$TANK_MODEL" --host 127.0.0.1 --port "$TANK_ADVISOR_PORT" \
      -ngl "$TANK_NGL" -c "$TANK_ADVISOR_CTX" --parallel 1 $TANK_ADVISOR_EXTRA_ARGS \
      >> "$TANK_RUNTIME_DIR/llama_$TANK_ADVISOR_PORT.log" 2>&1 < /dev/null &
  fi
else
  echo "    跳过(--no-advisor)"
fi

echo "==> [3/6] Laya 哨兵 (端口 $LAYA_PORT)"
if [ "$NO_LAYA" = "0" ] && [ -x "${LAYA_BIN:-}" ]; then
  if curl -s -m 2 "http://127.0.0.1:$LAYA_PORT/health" 2>/dev/null | grep -q ok; then
    echo "    port $LAYA_PORT 已在跑,跳过"
  else
    setsid nohup "$LAYA_BIN" serve "$LAYA_MODEL" --port "$LAYA_PORT" --device auto \
      > "$TANK_RUNTIME_DIR/laya_serve.log" 2>&1 < /dev/null &
  fi
else
  echo "    跳过(--no-laya 或无 laya 二进制)"
fi

echo "    等待 LLM 全部就绪..."
ALLPORTS=("$TANK_AI_PORT_1" "$TANK_AI_PORT_2" "$TANK_AI_PORT_3")
[ "$NO_ADVISOR" = "0" ] && ALLPORTS+=("$TANK_ADVISOR_PORT")
for P in "${ALLPORTS[@]}"; do
  for _ in $(seq 1 60); do
    curl -s -m 2 "http://127.0.0.1:$P/health" 2>/dev/null | grep -q '"status":"ok"' && break
    sleep 3
  done
  echo "    port $P: $(curl -s -m 2 http://127.0.0.1:$P/health)"
done

echo "==> [4/6] 游戏本体"
if pgrep -f "python3.*[t]ank_battle_deluxe" > /dev/null; then
  echo "    游戏已在跑,跳过 (如需重启先 ./scripts/stop_all.sh)"
else
  cd "$ROOT/src"
  setsid nohup python3 tank_battle_deluxe.py \
    >> "$TANK_RUNTIME_DIR/tank_game.log" 2>&1 < /dev/null &
  sleep 3   # 旧 socket 释放延迟(踩坑#1)
fi

echo "==> [5/6] 吕布 pilot (三层大脑)"
if [ "$NO_PILOT" = "0" ]; then
  setsid nohup env LAYA_URL="$LAYA_URL" TANK_ADVISOR_URL="$TANK_ADVISOR_URL" \
    python3 "$ROOT/src/oc_pilot.py" \
    >> "$TANK_RUNTIME_DIR/oc_pilot.log" 2>&1 < /dev/null &
else
  echo "    跳过(--no-pilot)"
fi

echo "==> [6/6] 集火监控 (可选)"
if [ "$NO_MON" = "0" ]; then
  setsid nohup python3 "$ROOT/src/jihuo_monitor.py" \
    >> "$TANK_RUNTIME_DIR/jihuo.log" 2>&1 < /dev/null &
fi

echo "完成。共 4 个 LLM + 1 个 Laya + 游戏 + pilot。"
echo "遥测: $TANK_RUNTIME_DIR/tank_battle_status.json (2s) / tank_fast.json (0.2s)"
