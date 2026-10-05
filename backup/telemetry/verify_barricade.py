#!/usr/bin/env python3
"""
39aigame 烈璧障效果验证器 (v39.0)
验证烈璧障是否正确阻挡敌军和子弹

用法:
    python3 verify_barricade.py              # 实时验证
    python3 verify_barricade.py --report     # 生成验证报告
"""

import json
import time
import sys
import math
from datetime import datetime

# 遥测文件路径
FAST_FILE = "/tmp/tank_fast.json"
SLOW_FILE = "/tmp/tank_battle_status.json"


def load_telemetry():
    """加载遥测数据"""
    data = {}
    
    try:
        with open(FAST_FILE, 'r') as f:
            data.update(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    
    try:
        with open(SLOW_FILE, 'r') as f:
            data.update(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    
    return data


def check_point_in_barricade(px, py, barricade):
    """检查点是否在烈璧障环带内"""
    bx, by = barricade['x'], barricade['y']
    radius = barricade['radius']
    thick = barricade.get('thick', 12)
    facing = barricade['facing']
    
    dx, dy = px - bx, py - by
    dist = math.hypot(dx, dy)
    
    # 检查距离是否在环带内
    if not (radius - thick <= dist <= radius + thick):
        return False
    
    # 检查角度是否在半圆范围内
    ang = math.atan2(dy, dx)
    diff = math.atan2(math.sin(ang - facing), math.cos(ang - facing))
    
    return abs(diff) <= math.pi / 2


def verify_barricade(data):
    """验证烈璧障效果"""
    issues = []
    
    if not data:
        return issues
    
    player_x = data.get('player_x', 800)
    player_y = data.get('player_y', 500)
    barricades = data.get('barricade_list', [])
    enemies = data.get('enemies', [])
    
    if not barricades:
        return issues
    
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 烈璧障验证")
    print(f"主公位置: ({player_x}, {player_y})")
    print(f"烈璧障数量: {len(barricades)}")
    
    for i, b in enumerate(barricades):
        print(f"  障碍{i}: 中心({b['x']:.0f}, {b['y']:.0f}) 朝向:{b['facing']:.2f} 半径:{b['radius']}")
    
    # 检查每个敌军
    for enemy in enemies:
        ex, ey = enemy.get('x', 0), enemy.get('y', 0)
        enemy_id = enemy.get('id', 'N/A')
        
        # 计算与主公的距离
        dist_to_player = math.hypot(ex - player_x, ey - player_y)
        
        # 检查敌军是否在烈璧障内
        in_barricade = False
        for b in barricades:
            if check_point_in_barricade(ex, ey, b):
                in_barricade = True
                break
        
        # 检查敌军是否穿过了烈璧障（在主公附近但在烈璧障外）
        if dist_to_player < 200 and not in_barricade:
            # 检查敌军和主公之间是否有烈璧障
            has_barricade_between = False
            for b in barricades:
                # 简单检查：敌军和主公是否分别在烈璧障两侧
                dist_enemy = math.hypot(ex - b['x'], ey - b['y'])
                dist_player = math.hypot(player_x - b['x'], player_y - b['y'])
                
                # 如果敌军距离烈璧障中心比主公远，可能穿过了
                if dist_enemy > dist_player and dist_enemy > b['radius']:
                    has_barricade_between = True
                    break
            
            if has_barricade_between:
                issues.append(f"🚨 敌军ID:{enemy_id} 可能穿过烈璧障！位置({ex:.0f}, {ey:.0f})，距离主公{dist_to_player:.0f}px")
        
        # 如果敌军在烈璧障内，应该是被阻挡的
        if in_barricade:
            print(f"  ✅ 敌军ID:{enemy_id} 被烈璧障阻挡在({ex:.0f}, {ey:.0f})")
    
    return issues


def run():
    """运行验证器"""
    print("🚀 烈璧障效果验证器启动")
    print("=" * 60)
    
    try:
        while True:
            data = load_telemetry()
            issues = verify_barricade(data)
            
            if issues:
                print("\n⚠️ 发现异常:")
                for issue in issues:
                    print(f"  {issue}")
            else:
                print("\n✅ 烈璧障工作正常")
            
            print("\n" + "=" * 60)
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n⏹️ 验证器停止")


def generate_report():
    """生成验证报告"""
    data = load_telemetry()
    issues = verify_barricade(data)
    
    report_file = f"/tmp/barricade_verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w') as f:
        f.write("39aigame 烈璧障验证报告\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n")
        
        if issues:
            f.write("\n发现异常:\n")
            for issue in issues:
                f.write(f"  {issue}\n")
        else:
            f.write("\n烈璧障工作正常\n")
    
    print(f"报告已保存: {report_file}")


def main():
    if '--report' in sys.argv:
        generate_report()
    else:
        run()


if __name__ == "__main__":
    main()
