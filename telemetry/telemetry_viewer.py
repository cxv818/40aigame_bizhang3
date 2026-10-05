#!/usr/bin/env python3
"""
39aigame 遥测查看器 (v39.0)
实时显示游戏遥测数据

用法:
    python3 telemetry_viewer.py              # 实时查看
    python3 telemetry_viewer.py --history    # 查看历史
    python3 telemetry_viewer.py --export     # 导出CSV
"""

import json
import time
import sys
import os
from datetime import datetime

# 遥测文件路径
FAST_FILE = "/tmp/tank_fast.json"
SLOW_FILE = "/tmp/tank_battle_status.json"


def clear_screen():
    """清屏"""
    os.system('clear' if os.name != 'nt' else 'cls')


def load_telemetry():
    """加载遥测数据"""
    data = {}
    
    # 加载快遥测
    try:
        with open(FAST_FILE, 'r') as f:
            fast_data = json.load(f)
            data.update(fast_data)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    
    # 加载慢遥测
    try:
        with open(SLOW_FILE, 'r') as f:
            slow_data = json.load(f)
            data.update(slow_data)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    
    return data


def format_status(data):
    """格式化状态显示"""
    if not data:
        return "暂无遥测数据"
    
    lines = []
    lines.append("=" * 60)
    lines.append(f"🎮 39aigame 实时遥测 - {datetime.now().strftime('%H:%M:%S')}")
    lines.append("=" * 60)
    
    # 基本信息
    lines.append(f"\n📊 基本信息")
    lines.append(f"  时间: {data.get('ts', 'N/A')}")
    lines.append(f"  状态: {data.get('state', 'N/A')}")
    lines.append(f"  波次: {data.get('wave', 'N/A')}")
    lines.append(f"  得分: {data.get('score', 'N/A')}")
    lines.append(f"  FPS: {data.get('fps', 'N/A')}")
    
    # 主公状态
    lines.append(f"\n⚔️ 主公状态")
    player_hp = data.get('player_hp', 0)
    player_max = data.get('player_max_hp', 1)
    hp_ratio = player_hp / player_max if player_max > 0 else 0
    hp_bar = "█" * int(hp_ratio * 20) + "░" * (20 - int(hp_ratio * 20))
    lines.append(f"  HP: {player_hp}/{player_max} [{hp_bar}] {hp_ratio*100:.0f}%")
    lines.append(f"  位置: ({data.get('player_x', 'N/A')}, {data.get('player_y', 'N/A')})")
    
    # 边界警告
    px = data.get('player_x', 800)
    py = data.get('player_y', 500)
    warnings = []
    if px < 150: warnings.append("左边界")
    elif px > 1450: warnings.append("右边界")
    if py < 150: warnings.append("上边界")
    elif py > 850: warnings.append("下边界")
    if warnings:
        lines.append(f"  ⚠️ 警告: {'+'.join(warnings)}")
    
    # 大营状态
    lines.append(f"\n🏰 大营状态")
    player_camp = data.get('player_camp', {})
    enemy_camp = data.get('enemy_camp', {})
    if player_camp:
        camp_hp = player_camp.get('hp', 0)
        lines.append(f"  我军大营: HP {camp_hp} {'🟢' if camp_hp > 600 else '🟡' if camp_hp > 300 else '🔴'}")
    if enemy_camp:
        camp_hp = enemy_camp.get('hp', 0)
        lines.append(f"  敌军大营: HP {camp_hp}")
    
    # 敌军状态
    lines.append(f"\n👹 敌军状态")
    lines.append(f"  场上敌军: {data.get('enemies_onfield', 'N/A')}台")
    lines.append(f"  击杀/总出: {data.get('killed', 'N/A')}/{data.get('spawned', 'N/A')}")
    
    # 方阵
    phalanx = data.get('phalanx', [])
    if phalanx:
        lines.append(f"  方阵: {len(phalanx)}台 {phalanx[:5]}")
    
    # AI状态
    lines.append(f"\n🤖 AI状态")
    ai = data.get('ai', {})
    if ai:
        lines.append(f"  状态: {ai.get('status', 'N/A')}")
        lines.append(f"  延迟: {ai.get('latency', 'N/A')}s")
        lines.append(f"  进化: 第{ai.get('gen', 'N/A')}代")
        lines.append(f"  教训: {ai.get('lessons', 'N/A')}条")
    
    # 三帅状态
    generals = data.get('generals', [])
    if generals:
        lines.append(f"\n⚔️ 三帅状态")
        for g in generals:
            lines.append(f"  {g.get('name', 'N/A')}: HP {g.get('hp', 'N/A')}/{g.get('max_hp', 'N/A')} @ ({g.get('x', 'N/A')}, {g.get('y', 'N/A')})")
    
    # Pilot状态
    lines.append(f"\n🎮 Pilot状态")
    lines.append(f"  接管: {'✅' if data.get('pilot') else '❌'}")
    
    # 烈璧障
    lines.append(f"\n🛡️ 烈璧障")
    lines.append(f"  数量: {data.get('barricades', 'N/A')}")
    lines.append(f"  CD: {data.get('barricade_cd_s', 'N/A')}s")
    
    lines.append("\n" + "=" * 60)
    
    return "\n".join(lines)


def realtime_view():
    """实时查看模式"""
    try:
        while True:
            clear_screen()
            data = load_telemetry()
            print(format_status(data))
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n退出遥测查看器")


def export_csv():
    """导出CSV"""
    data = load_telemetry()
    if not data:
        print("暂无遥测数据")
        return
    
    filename = f"/tmp/telemetry_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(filename, 'w') as f:
        f.write("key,value\n")
        for key, value in data.items():
            f.write(f"{key},{value}\n")
    
    print(f"已导出到: {filename}")


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == '--history':
            # 查看历史
            print("历史功能待实现")
        elif sys.argv[1] == '--export':
            export_csv()
        else:
            print(f"未知参数: {sys.argv[1]}")
            print("用法: python3 telemetry_viewer.py [--history|--export]")
    else:
        realtime_view()


if __name__ == "__main__":
    main()
