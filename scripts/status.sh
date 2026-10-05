# v36.0 (2026-10-05) — 36aigame
# 版本: v20.0 (2025-10-03)
#!/usr/bin/env bash
# ============ 11aigame 全脑健康速查 ============
# 版本: v20.0 (2025-10-03)
# 三帅+军师+Laya+游戏战况 一屏看完
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../config/env.sh
source "$ROOT/config/env.sh" 2>/dev/null || true
RT="${TANK_RUNTIME_DIR:-/tmp}"

echo "── LLM 大脑 ──"
for P in "$TANK_AI_PORT_1" "$TANK_AI_PORT_2" "$TANK_AI_PORT_3" "${TANK_ADVISOR_PORT:-8083}"; do
  case "$P" in
    "$TANK_AI_PORT_1") N="曹操  ";; "$TANK_AI_PORT_2") N="夏侯惇";;
    "$TANK_AI_PORT_3") N="夏侯渊";; *) N="军师  ";; esac
  printf "%s :%s  %s\n" "$N" "$P" "$(curl -s -m 2 http://127.0.0.1:$P/health 2>/dev/null || echo DOWN)"
done
H=$(curl -s -m 2 "http://127.0.0.1:${LAYA_PORT:-8091}/health" 2>/dev/null)
if [ -n "$H" ]; then
  echo "Laya  :${LAYA_PORT:-8091}  $(echo "$H" | head -c 100)"
else
  echo "Laya  :${LAYA_PORT:-8091}  DOWN (哨兵层关闭,pilot 自动降级)"
fi

if [ -f "$RT/tank_battle_status.json" ]; then
  python3 - "$RT/tank_battle_status.json" <<'EOF'
import json, sys
try:
    s = json.load(open(sys.argv[1]))
except Exception as e:
    print("\n遥测不可读:", e); raise SystemExit
ai = s.get("ai", {})
print(f"\n── 战况 ──\n{ s.get('ts') } | wave {s.get('wave')} | 杀 {s.get('killed')} | "
      f"HP {round(s.get('player_hp',0))}/{s.get('player_max_hp')} | fps {s.get('fps')} | "
      f"pilot {s.get('pilot')} | 烈璧障 {s.get('barricades')} (CD {s.get('barricade_cd_s')}s)")
print("曹操:", ai.get("status"))
for k, v in (ai.get("lieutenants") or {}).items():
    print(f"{k}:", v.get("status"))
EOF
else
  echo "\n(无遥测 $RT/tank_battle_status.json — 游戏未运行?)"
fi
