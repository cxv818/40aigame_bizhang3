# v36.01 (2026-10-05) — 36aigame 遥测告警脚本
"""读取实时遥测，判断告警条件。
输出: 告警文本 或 NO_ALERT 或 GAME_OVER
阈值: 敌距<100px | HP<30% | 遥测停更>60s
"""
import json, os, time, sys

FAST = os.environ.get("TANK_RUNTIME_DIR", "/tmp") + "/tank_fast.json"
SLOW = os.environ.get("TANK_RUNTIME_DIR", "/tmp") + "/tank_battle_status.json"

def read(p):
    try:
        raw = open(p).read()
        if raw.startswith('#'):
            raw = raw[raw.find('\n')+1:]
        return json.loads(raw)
    except Exception:
        return None

def main():
    # 1) 文件不存在
    if not os.path.exists(FAST):
        print("GAME_OVER")
        return

    # 2) 停更检测(>60s未更新 = 游戏可能退出)
    age = time.time() - os.path.getmtime(FAST)
    if age > 60:
        print(f"GAME_OVER")
        return

    fast = read(FAST)
    slow = read(SLOW)
    if fast is None:
        print("GAME_OVER")
        return

    # 3) 非战斗状态
    state = (slow or {}).get("state", "play")
    if state == "gameover":
        score = (slow or {}).get("score", 0)
        wave = (slow or {}).get("wave", 0)
        killed = (slow or {}).get("killed", 0)
        print(f"GAME_OVER 最终得分{score} 第{wave}波 击杀{killed}")
        return
    if state != "play":
        print("NO_ALERT")
        return

    alerts = []

    # 4) HP告警 (<30%)
    hp = slow.get("player_hp", 500)
    mx = slow.get("player_max_hp", 500) or 500
    ratio = hp / mx
    if ratio < 0.30:
        alerts.append(f"🩸 吕布HP危急 {hp}/{mx}({ratio*100:.0f}%)")

    # 5) 敌军逼近 (<100px)
    px, py = fast.get("player_x"), fast.get("player_y")
    enemies = fast.get("enemies", [])
    if px is not None and enemies:
        near = min(enemies, key=lambda e: (e['x']-px)**2 + (e['y']-py)**2)
        d = ((near['x']-px)**2 + (near['y']-py)**2) ** 0.5
        if d < 100:
            alerts.append(f"⚠️ 敌#{near['id']}({near['kind']}) 逼近 {d:.0f}px HP{near['hp']}")

    # 6) 大本营危急 (<25%)
    pc = slow.get("player_camp") or {}
    if pc and pc.get("alive") and pc.get("hp", 999) < pc.get("max_hp", 888) * 0.25:
        alerts.append(f"🏰 我方大本营危急 {pc['hp']}/{pc.get('max_hp')}")

    if alerts:
        wave = slow.get("wave", "?")
        score = slow.get("score", 0)
        print(f"【第{wave}波 得分{score}】" + " | ".join(alerts))
    else:
        print("NO_ALERT")

if __name__ == "__main__":
    main()
