#!/usr/bin/env python3
"""
39aigame 遥测收集器 (v39.0)
收集游戏遥测数据并存储到历史数据库

用法:
    python3 telemetry_collector.py              # 启动收集
    python3 telemetry_collector.py --interval 5 # 每5秒收集一次
"""

import json
import time
import sys
import os
import sqlite3
from datetime import datetime
from pathlib import Path

# 遥测文件路径
FAST_FILE = "/tmp/tank_fast.json"
SLOW_FILE = "/tmp/tank_battle_status.json"

# 数据库路径
DB_DIR = Path("/home/ibm/桌面/39aigame/telemetry/data")
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "telemetry_history.db"


class TelemetryCollector:
    """遥测收集器"""
    
    def __init__(self, interval=5):
        self.interval = interval
        self.db_path = DB_PATH
        self.init_db()
    
    def init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建遥测数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                datetime TEXT,
                wave INTEGER,
                score INTEGER,
                player_hp INTEGER,
                player_max_hp INTEGER,
                player_x REAL,
                player_y REAL,
                enemies_onfield INTEGER,
                killed INTEGER,
                spawned INTEGER,
                player_camp_hp INTEGER,
                enemy_camp_hp INTEGER,
                fps REAL,
                ai_status TEXT,
                ai_latency REAL,
                ai_gen INTEGER,
                data_json TEXT
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON telemetry(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_wave ON telemetry(wave)')
        
        conn.commit()
        conn.close()
    
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
    
    def collect(self):
        """收集数据"""
        data = self.load_telemetry()
        
        if not data:
            return None
        
        # 提取关键字段
        record = {
            'timestamp': time.time(),
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'wave': data.get('wave', 0),
            'score': data.get('score', 0),
            'player_hp': data.get('player_hp', 0),
            'player_max_hp': data.get('player_max_hp', 0),
            'player_x': data.get('player_x', 0),
            'player_y': data.get('player_y', 0),
            'enemies_onfield': data.get('enemies_onfield', 0),
            'killed': data.get('killed', 0),
            'spawned': data.get('spawned', 0),
            'player_camp_hp': data.get('player_camp', {}).get('hp', 0) if data.get('player_camp') else 0,
            'enemy_camp_hp': data.get('enemy_camp', {}).get('hp', 0) if data.get('enemy_camp') else 0,
            'fps': data.get('fps', 0),
            'ai_status': data.get('ai', {}).get('status', '') if data.get('ai') else '',
            'ai_latency': data.get('ai', {}).get('latency', 0) if data.get('ai') else 0,
            'ai_gen': data.get('ai', {}).get('gen', 0) if data.get('ai') else 0,
            'data_json': json.dumps(data, ensure_ascii=False)
        }
        
        return record
    
    def save(self, record):
        """保存到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO telemetry 
            (timestamp, datetime, wave, score, player_hp, player_max_hp, 
             player_x, player_y, enemies_onfield, killed, spawned,
             player_camp_hp, enemy_camp_hp, fps, ai_status, ai_latency, ai_gen, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            record['timestamp'], record['datetime'], record['wave'], record['score'],
            record['player_hp'], record['player_max_hp'], record['player_x'], record['player_y'],
            record['enemies_onfield'], record['killed'], record['spawned'],
            record['player_camp_hp'], record['enemy_camp_hp'], record['fps'],
            record['ai_status'], record['ai_latency'], record['ai_gen'], record['data_json']
        ))
        
        conn.commit()
        conn.close()
    
    def run(self):
        """运行收集器"""
        print(f"🚀 遥测收集器启动 (间隔: {self.interval}秒)")
        print(f"📁 数据库: {self.db_path}")
        
        try:
            while True:
                record = self.collect()
                
                if record:
                    self.save(record)
                    print(f"[{record['datetime']}] 波次:{record['wave']} 得分:{record['score']} HP:{record['player_hp']}/{record['player_max_hp']}")
                else:
                    print("暂无遥测数据")
                
                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            print("\n⏹️ 收集器停止")
    
    def query(self, start_time=None, end_time=None, limit=100):
        """查询历史数据"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM telemetry"
        params = []
        
        if start_time or end_time:
            query += " WHERE"
            if start_time:
                query += " timestamp >= ?"
                params.append(start_time)
            if end_time:
                if start_time:
                    query += " AND"
                query += " timestamp <= ?"
                params.append(end_time)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        conn.close()
        
        return rows


def main():
    interval = 5
    
    if '--interval' in sys.argv:
        idx = sys.argv.index('--interval')
        if idx + 1 < len(sys.argv):
            interval = int(sys.argv[idx + 1])
    
    collector = TelemetryCollector(interval=interval)
    collector.run()


if __name__ == "__main__":
    main()
