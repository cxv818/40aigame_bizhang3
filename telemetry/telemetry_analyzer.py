#!/usr/bin/env python3
"""
39aigame 遥测分析器 (v39.0)
分析游戏遥测数据，检测异常

用法:
    python3 telemetry_analyzer.py              # 实时分析
    python3 telemetry_analyzer.py --report     # 生成报告
"""

import json
import time
import sys
import os
from datetime import datetime

# 遥测文件路径
FAST_FILE = "/tmp/tank_fast.json"
SLOW_FILE = "/tmp/tank_battle_status.json"


class TelemetryAnalyzer:
    """遥测分析器"""
    
    def __init__(self):
        self.history = []
        self.max_history = 100
    
    def load_telemetry(self):
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
    
    def analyze_barricade(self, data):
        """分析烈璧障效果"""
        issues = []
        
        if not data:
            return issues
        
        # 获取烈璧障位置
        barricades = data.get('barricades', [])
        if not barricades:
            return issues
        
        # 获取敌军位置
        enemies = data.get('enemies', [])
        player_x = data.get('player_x', 800)
        player_y = data.get('player_y', 500)
        
        # 检查是否有敌军穿过烈璧障靠近主公
        for e in enemies:
            ex, ey = e.get('x', 0), e.get('y', 0)
            dist_to_player = ((ex - player_x)**2 + (ey - player_y)**2)**0.5
            
            # 如果敌军在主公附近（<200像素），检查是否穿过了烈璧障
            if dist_to_player < 200:
                # 这里应该检查敌军是否穿过了烈璧障
                # 但由于遥测数据不包含烈璧障具体位置，只能推测
                pass
        
        return issues
    
    def analyze_enemy_movement(self, data):
        """分析敌军移动"""
        issues = []
        
        if not data:
            return issues
        
        enemies = data.get('enemies', [])
        player_camp = data.get('player_camp', {})
        
        if not player_camp or not player_camp.get('alive'):
            return issues
        
        camp_x = player_camp.get('x', 800)
        camp_y = player_camp.get('y', 900)
        
        # 检查是否有敌军直接穿过大营
        for e in enemies:
            ex, ey = e.get('x', 0), e.get('y', 0)
            dist_to_camp = ((ex - camp_x)**2 + (ey - camp_y)**2)**0.5
            
            # 如果敌军在营地内部（<50像素），可能穿过了障碍
            if dist_to_camp < 50:
                issues.append(f"🚨 敌军ID:{e.get('id')} 在营地内部({ex},{ey})，可能穿过障碍！")
        
        return issues
    
    def analyze_bullet_pass(self, data):
        """分析子弹穿透"""
        issues = []
        
        # 这个需要更详细的遥测数据，当前版本暂不支持
        # 需要记录子弹位置和烈璧障位置
        
        return issues
    
    def analyze(self, data):
        """综合分析"""
        issues = []
        
        issues.extend(self.analyze_barricade(data))
        issues.extend(self.analyze_enemy_movement(data))
        issues.extend(self.analyze_bullet_pass(data))
        
        return issues
    
    def run(self):
        """运行分析器"""
        print("🚀 遥测分析器启动")
        print("=" * 60)
        
        try:
            while True:
                data = self.load_telemetry()
                
                if data:
                    # 保存历史
                    self.history.append(data)
                    if len(self.history) > self.max_history:
                        self.history.pop(0)
                    
                    # 分析
                    issues = self.analyze(data)
                    
                    if issues:
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 发现异常:")
                        for issue in issues:
                            print(f"  {issue}")
                    else:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] 状态正常", end='\r')
                
                time.sleep(2)
                
        except KeyboardInterrupt:
            print("\n\n⏹️ 分析器停止")
            self.generate_report()
    
    def generate_report(self):
        """生成报告"""
        if not self.history:
            print("无数据可报告")
            return
        
        print("\n" + "=" * 60)
        print("📊 遥测分析报告")
        print("=" * 60)
        
        # 统计信息
        waves = [d.get('wave', 0) for d in self.history]
        scores = [d.get('score', 0) for d in self.history]
        hps = [d.get('player_hp', 0) for d in self.history]
        
        print(f"\n数据点: {len(self.history)}")
        print(f"波次范围: {min(waves)} - {max(waves)}")
        print(f"得分范围: {min(scores)} - {max(scores)}")
        print(f"HP范围: {min(hps)} - {max(hps)}")
        
        # 保存报告
        report_file = f"/tmp/telemetry_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w') as f:
            f.write("39aigame 遥测分析报告\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"数据点: {len(self.history)}\n")
            f.write(f"波次范围: {min(waves)} - {max(waves)}\n")
            f.write(f"得分范围: {min(scores)} - {max(scores)}\n")
            f.write(f"HP范围: {min(hps)} - {max(hps)}\n")
        
        print(f"\n报告已保存: {report_file}")


def main():
    analyzer = TelemetryAnalyzer()
    
    if '--report' in sys.argv:
        analyzer.generate_report()
    else:
        analyzer.run()


if __name__ == "__main__":
    main()
