#!/usr/bin/env python3
"""
39aigame 遥测监控器 (v39.0)
实时监控游戏状态，异常时报警

用法:
    python3 telemetry_monitor.py              # 实时监控
    python3 telemetry_monitor.py --alert      # 异常时报警
    python3 telemetry_monitor.py --log        # 记录到文件
"""

import json
import time
import sys
import os
from datetime import datetime

# 遥测文件路径
FAST_FILE = "/tmp/tank_fast.json"
SLOW_FILE = "/tmp/tank_battle_status.json"

# 报警阈值
ALERT_THRESHOLDS = {
    'player_hp_low': 0.3,      # 主公HP < 30%
    'camp_hp_low': 0.3,        # 大营HP < 30%
    'fps_low': 20,             # FPS < 20
    'latency_high': 10,        # AI延迟 > 10s
    'enemies_high': 40,        # 敌军 > 40台
    'boundary_warning': 150,   # 距离边界 < 150px
}


class TelemetryMonitor:
    """遥测监控器"""
    
    def __init__(self, alert_mode=False, log_mode=False):
        self.alert_mode = alert_mode
        self.log_mode = log_mode
        self.alert_history = []
        self.last_data = None
        
        if log_mode:
            self.log_file = f"/tmp/telemetry_log_{datetime.now().strftime('%Y%m%d')}.txt"
    
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
    
    def check_alerts(self, data):
        """检查报警条件"""
        alerts = []
        
        if not data:
            return alerts
        
        # 检查主公HP
        player_hp = data.get('player_hp', 0)
        player_max = data.get('player_max_hp', 1)
        if player_max > 0 and player_hp / player_max < ALERT_THRESHOLDS['player_hp_low']:
            alerts.append(f"🔴 主公HP危急: {player_hp}/{player_max} ({player_hp/player_max*100:.0f}%)")
        
        # 检查大营HP
        player_camp = data.get('player_camp', {})
        if player_camp:
            camp_hp = player_camp.get('hp', 0)
            camp_max = 1000  # 假设最大1000
            if camp_hp / camp_max < ALERT_THRESHOLDS['camp_hp_low']:
                alerts.append(f"🔴 大营HP危急: {camp_hp}/{camp_max}")
        
        # 检查FPS
        fps = data.get('fps', 30)
        if fps < ALERT_THRESHOLDS['fps_low']:
            alerts.append(f"🟡 FPS过低: {fps}")
        
        # 检查AI延迟
        ai = data.get('ai', {})
        latency = ai.get('latency', 0)
        if latency > ALERT_THRESHOLDS['latency_high']:
            alerts.append(f"🟡 AI延迟过高: {latency}s")
        
        # 检查敌军数量
        enemies = data.get('enemies_onfield', 0)
        if enemies > ALERT_THRESHOLDS['enemies_high']:
            alerts.append(f"🟡 敌军过多: {enemies}台")
        
        # 检查边界
        px = data.get('player_x', 800)
        py = data.get('player_y', 500)
        if px < ALERT_THRESHOLDS['boundary_warning']:
            alerts.append(f"🟡 靠近左边界: x={px}")
        elif px > 1600 - ALERT_THRESHOLDS['boundary_warning']:
            alerts.append(f"🟡 靠近右边界: x={px}")
        if py < ALERT_THRESHOLDS['boundary_warning']:
            alerts.append(f"🟡 靠近上边界: y={py}")
        elif py > 1000 - ALERT_THRESHOLDS['boundary_warning']:
            alerts.append(f"🟡 靠近下边界: y={py}")
        
        return alerts
    
    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] {message}"
        
        print(log_line)
        
        if self.log_mode:
            with open(self.log_file, 'a') as f:
                f.write(log_line + '\n')
    
    def run(self):
        """运行监控"""
        self.log("🚀 遥测监控器启动")
        self.log(f"报警模式: {'开启' if self.alert_mode else '关闭'}")
        self.log(f"日志模式: {'开启' if self.log_mode else '关闭'}")
        
        try:
            while True:
                data = self.load_telemetry()
                
                if data != self.last_data:
                    self.last_data = data
                    
                    # 检查报警
                    alerts = self.check_alerts(data)
                    
                    if alerts:
                        for alert in alerts:
                            self.log(alert)
                        
                        # 报警模式：播放声音或发送通知
                        if self.alert_mode:
                            os.system('echo "\a"')  # 蜂鸣
                    
                    # 显示基本信息
                    if data:
                        wave = data.get('wave', 'N/A')
                        score = data.get('score', 'N/A')
                        hp = data.get('player_hp', 'N/A')
                        self.log(f"波次:{wave} 得分:{score} HP:{hp}")
                
                time.sleep(2)
                
        except KeyboardInterrupt:
            self.log("\n⏹️ 监控器停止")


def main():
    alert_mode = '--alert' in sys.argv
    log_mode = '--log' in sys.argv
    
    monitor = TelemetryMonitor(alert_mode=alert_mode, log_mode=log_mode)
    monitor.run()


if __name__ == "__main__":
    main()
