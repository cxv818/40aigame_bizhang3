#!/usr/bin/env python3
"""
39aigame 烈璧障路径分析器 (v39.0)
分析敌军是否只能从烈璧障开口方向绕过

用法:
    python3 analyze_barricade_path.py              # 实时分析
    python3 analyze_barricade_path.py --report     # 生成分析报告
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


def check_barricade_blocking(barricade, player_x, player_y, enemy_x, enemy_y):
    """
    检查烈璧障是否正确阻挡敌军
    
    返回:
        'blocked' - 敌军被阻挡
        'opening' - 敌军从开口方向接近
        'far' - 敌军距离太远
    """
    bx, by = barricade['x'], barricade['y']
    radius = barricade['radius']
    facing = barricade['facing']
    
    # 计算开口方向（与朝向相反）
    opening = facing + math.pi
    
    # 计算敌军相对于障碍的角度
    dx_enemy = enemy_x - bx
    dy_enemy = enemy_y - by
    angle_to_enemy = math.atan2(dy_enemy, dx_enemy)
    
    # 计算主公相对于障碍的角度
    dx_player = player_x - bx
    dy_player = player_y - by
    angle_to_player = math.atan2(dy_player, dx_player)
    
    # 计算敌军距离
    dist_enemy = math.hypot(dx_enemy, dy_enemy)
    
    # 如果敌军在环带内，被阻挡
    diff_to_facing = abs(math.atan2(math.sin(angle_to_enemy - facing), math.cos(angle_to_enemy - facing)))
    if (radius - 15 <= dist_enemy <= radius + 15) and diff_to_facing <= math.pi/2:
        return 'blocked'
    
    # 如果敌军在开口方向，可以接近
    diff_to_opening = abs(math.atan2(math.sin(angle_to_enemy - opening), math.cos(angle_to_enemy - opening)))
    if diff_to_opening <= math.pi/3:  # 开口方向±60度
        return 'opening'
    
    return 'far'


def analyze_paths(data):
    """分析敌军路径"""
    results = {
        'blocked': [],
        'opening': [],
        'far': [],
        'violation': []  # 违规穿过
    }
    
    if not data:
        return results
    
    player_x = data.get('player_x', 800)
    player_y = data.get('player_y', 500)
    barricades = data.get('barricade_list', [])
    enemies = data.get('enemies', [])
    
    if not barricades:
        return results
    
    for enemy in enemies:
        ex, ey = enemy.get('x', 0), enemy.get('y', 0)
        eid = enemy.get('id', 'N/A')
        
        # 计算与主公的距离
        dist_to_player = math.hypot(ex - player_x, ey - player_y)
        
        # 检查每个烈璧障
        enemy_status = 'far'
        for b in barricades:
            status = check_barricade_blocking(b, player_x, player_y, ex, ey)
            if status == 'blocked':
                enemy_status = 'blocked'
                break
            elif status == 'opening':
                enemy_status = 'opening'
        
        # 如果敌军已经突破到主公附近，但没有被阻挡，也没有从开口方向，则是违规
        if dist_to_player < 200 and enemy_status == 'far':
            enemy_status = 'violation'
        
        results[enemy_status].append({
            'id': eid,
            'x': ex,
            'y': ey,
            'dist': dist_to_player
        })
    
    return results


def print_analysis(results):
    """打印分析结果"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 烈璧障路径分析")
    print("=" * 60)
    
    total = sum(len(v) for v in results.values())
    print(f"总敌军: {total}")
    
    if results['blocked']:
        print(f"\n🛑 被阻挡 ({len(results['blocked'])}台):")
        for e in results['blocked']:
            print(f"  ID:{e['id']} ({e['x']:.0f}, {e['y']:.0f}) 距主公{e['dist']:.0f}px")
    
    if results['opening']:
        print(f"\n⚠️  从开口方向接近 ({len(results['opening'])}台):")
        for e in results['opening']:
            print(f"  ID:{e['id']} ({e['x']:.0f}, {e['y']:.0f}) 距主公{e['dist']:.0f}px")
    
    if results['far']:
        print(f"\n✅ 距离较远 ({len(results['far'])}台):")
        for e in results['far'][:5]:  # 只显示前5台
            print(f"  ID:{e['id']} ({e['x']:.0f}, {e['y']:.0f}) 距主公{e['dist']:.0f}px")
        if len(results['far']) > 5:
            print(f"  ... 还有{len(results['far']) - 5}台")
    
    if results['violation']:
        print(f"\n🚨 违规穿过 ({len(results['violation'])}台):")
        for e in results['violation']:
            print(f"  ID:{e['id']} ({e['x']:.0f}, {e['y']:.0f}) 距主公{e['dist']:.0f}px")
    
    # 统计
    blocked_rate = len(results['blocked']) / total * 100 if total > 0 else 0
    opening_rate = len(results['opening']) / total * 100 if total > 0 else 0
    violation_rate = len(results['violation']) / total * 100 if total > 0 else 0
    
    print(f"\n📊 统计:")
    print(f"  阻挡率: {blocked_rate:.1f}%")
    print(f"  开口接近率: {opening_rate:.1f}%")
    print(f"  违规穿过率: {violation_rate:.1f}%")
    
    if violation_rate > 10:
        print(f"\n🔴 警告: 违规穿过率过高！")
    elif violation_rate > 0:
        print(f"\n🟡 注意: 有敌军违规穿过")
    else:
        print(f"\n🟢 烈璧障工作正常")
    
    print("=" * 60)


def run():
    """运行分析器"""
    print("🚀 烈璧障路径分析器启动")
    print("验证敌军是否只能从开口方向绕过烈璧障")
    print("=" * 60)
    
    try:
        while True:
            data = load_telemetry()
            results = analyze_paths(data)
            print_analysis(results)
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n⏹️ 分析器停止")


def generate_report():
    """生成分析报告"""
    data = load_telemetry()
    results = analyze_paths(data)
    
    report_file = f"/tmp/barricade_path_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w') as f:
        f.write("39aigame 烈璧障路径分析报告\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n")
        
        total = sum(len(v) for v in results.values())
        f.write(f"总敌军: {total}\n")
        
        f.write(f"被阻挡: {len(results['blocked'])}台\n")
        f.write(f"从开口接近: {len(results['opening'])}台\n")
        f.write(f"距离较远: {len(results['far'])}台\n")
        f.write(f"违规穿过: {len(results['violation'])}台\n")
        
        blocked_rate = len(results['blocked']) / total * 100 if total > 0 else 0
        opening_rate = len(results['opening']) / total * 100 if total > 0 else 0
        violation_rate = len(results['violation']) / total * 100 if total > 0 else 0
        
        f.write(f"\n阻挡率: {blocked_rate:.1f}%\n")
        f.write(f"开口接近率: {opening_rate:.1f}%\n")
        f.write(f"违规穿过率: {violation_rate:.1f}%\n")
        
        if violation_rate > 10:
            f.write("\n警告: 违规穿过率过高！\n")
        elif violation_rate > 0:
            f.write("\n注意: 有敌军违规穿过\n")
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
