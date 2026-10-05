# v36.0 (2026-10-05) — 36aigame
# 战场记录系统
# 版本: v15.1
# 功能: 每秒记录所有游戏元素，供LLM分析

import json
import time
import math
import threading
from game_db import get_db

# 战场记录数据库
# v36.01: battle库大幅节流落盘(30s) — 之前每秒全量dump~30MB JSON造成IO黑洞
battle_db = get_db("battle_records", "/tmp/hsdb_battle.json", max_memory_size=5000, sync_every_n=30)

# 异步缓存：避免主线程读取大文件导致卡顿
_cached_analysis = ""
_cache_lock = threading.Lock()
_cache_last_update = 0


def _update_analysis_cache():
    """后台线程更新缓存"""
    global _cached_analysis, _cache_last_update
    try:
        # 从高速数据库获取最新数据（内存读取，很快）
        latest = battle_db.get("latest_analysis")
        if latest:
            with _cache_lock:
                _cached_analysis = latest
                _cache_last_update = time.time()
    except Exception:
        pass


def get_cached_analysis():
    """获取缓存的战场分析（非阻塞）"""
    with _cache_lock:
        # 如果缓存超过60秒未更新，返回空字符串（避免 stale 数据）
        if time.time() - _cache_last_update < 60.0:
            return _cached_analysis
        return ""


def update_analysis_cache(analysis_text):
    """更新缓存（由记录线程调用）"""
    global _cached_analysis, _cache_last_update
    with _cache_lock:
        _cached_analysis = analysis_text
        _cache_last_update = time.time()

class BattleRecorder:
    """
    战场记录器:
    - 每秒记录一次完整战场状态
    - 包括: 玩家、敌人、子弹、大营、事件
    """
    
    def __init__(self):
        self.frame_count = 0
        self.last_record_time = 0
        self.record_interval = 1.0  # 每秒记录一次
        self.current_battle_id = f"battle_{int(time.time())}"
        
    def record(self, game_state):
        """记录一帧数据"""
        current_time = time.time()
        
        # 检查是否到了记录间隔（每2秒记录一次，减少IO）
        if current_time - self.last_record_time < 2.0:
            return
        
        self.last_record_time = current_time
        self.frame_count += 1
        
        # 构建记录数据
        record = {
            "battle_id": self.current_battle_id,
            "frame": self.frame_count,
            "timestamp": current_time,
            "game_time": game_state.get("game_time", 0),
            
            # 玩家信息
            "player": {
                "x": game_state.get("player_x", 0),
                "y": game_state.get("player_y", 0),
                "hp": game_state.get("player_hp", 0),
                "max_hp": game_state.get("player_max_hp", 500),
                "angle": game_state.get("player_angle", 0),  # 炮台角度
                "kills": game_state.get("killed", 0),
                "wave": game_state.get("wave", 1),
            },
            
            # 敌人信息
            "enemies": [],
            
            # 子弹信息
            "bullets": [],
            
            # 大营信息
            "camps": {},
            
            # 事件
            "events": []
        }
        
        # 记录敌人
        for enemy in game_state.get("enemies", []):
            record["enemies"].append({
                "id": enemy.get("id", 0),
                "x": enemy.get("x", 0),
                "y": enemy.get("y", 0),
                "hp": enemy.get("hp", 0),
                "max_hp": enemy.get("max_hp", 0),
                "angle": enemy.get("angle", 0),  # 炮台角度
                "type": enemy.get("type", "grunt"),
                "plan": enemy.get("plan", ""),
                "alive": enemy.get("alive", True)
            })
        
        # 记录子弹
        for bullet in game_state.get("player_bullets", []):
            record["bullets"].append({
                "owner": "player",
                "x": bullet.get("x", 0),
                "y": bullet.get("y", 0),
                "vx": bullet.get("vx", 0),
                "vy": bullet.get("vy", 0),
                "angle": math.atan2(bullet.get("vy", 0), bullet.get("vx", 0))
            })
        
        for bullet in game_state.get("enemy_bullets", []):
            record["bullets"].append({
                "owner": "enemy",
                "x": bullet.get("x", 0),
                "y": bullet.get("y", 0),
                "vx": bullet.get("vx", 0),
                "vy": bullet.get("vy", 0),
                "angle": math.atan2(bullet.get("vy", 0), bullet.get("vx", 0))
            })
        
        # 记录大营
        if game_state.get("enemy_camp"):
            ec = game_state["enemy_camp"]
            record["camps"]["enemy"] = {
                "x": ec.get("x", 0),
                "y": ec.get("y", 0),
                "hp": ec.get("hp", 0),
                "max_hp": ec.get("max_hp", 888),
                "alive": ec.get("alive", True)
            }
        
        if game_state.get("player_camp"):
            pc = game_state["player_camp"]
            record["camps"]["player"] = {
                "x": pc.get("x", 0),
                "y": pc.get("y", 0),
                "hp": pc.get("hp", 0),
                "max_hp": pc.get("max_hp", 888),
                "alive": pc.get("alive", True)
            }
        
        # 保存到数据库
        key = f"{self.current_battle_id}_frame_{self.frame_count}"
        battle_db.set(key, record)
        
        # 同时保存最新状态
        battle_db.set(f"{self.current_battle_id}_latest", record)
        
        # 更新异步缓存（供LLM快速读取）
        try:
            enemy_count = len(record.get('enemies', []))
            bullet_count = len(record.get('bullets', []))
            player_hp = record.get('player', {}).get('hp', 0)
            player_max_hp = record.get('player', {}).get('max_hp', 500)
            wave = record.get('player', {}).get('wave', 1)
            
            # 统计战术
            tactics = {}
            for e in record.get('enemies', []):
                plan = e.get('plan', '')
                if plan:
                    tactics[plan] = tactics.get(plan, 0) + 1
            
            # 计算玩家威胁度
            threat_level = "低"
            if player_hp < player_max_hp * 0.3:
                threat_level = "极高"
            elif player_hp < player_max_hp * 0.5:
                threat_level = "高"
            elif player_hp < player_max_hp * 0.8:
                threat_level = "中"
            
            # 计算敌人密度（每100x100区域）
            density = enemy_count / 9  # 900x600战场约9个区域
            
            analysis = f"\n📊最近战场数据 (波次{wave}):\n"
            analysis += f"- 敌人:{enemy_count}个, 子弹:{bullet_count}发, 密度:{density:.1f}/区\n"
            analysis += f"- 玩家HP:{player_hp}/{player_max_hp} (威胁度:{threat_level})\n"
            analysis += f"- 战术分布:{tactics}\n"
            
            # 添加战术建议（基于实时数据）
            if threat_level == "极高":
                analysis += "- 🔴建议:玩家残血，全力集火收割！\n"
            elif threat_level == "高":
                analysis += "- 🟠建议:玩家血量中等，保持压制，准备集火。\n"
            elif density > 5:
                analysis += "- 🟡建议:兵力充足，可尝试方阵推进压缩空间。\n"
            elif enemy_count < 5:
                analysis += "- 🟢建议:兵力不足，转为游击骚扰，等待援军。\n"
            
            # 添加战术效果提示
            if '集火' in tactics and tactics['集火'] > 10:
                analysis += "- 💡提示:集火单位充足，可触发合火弹！\n"
            if '方阵' in tactics and tactics['方阵'] > 5:
                analysis += "- 💡提示:方阵已成，注意保护阵外单位。\n"
            
            update_analysis_cache(analysis)
        except Exception:
            pass
        
        return record
    
    def add_event(self, event_type, data):
        """添加事件"""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": time.time()
        }
        # v36.0: 内存时间线(供三帅复盘提示词), 保留最近200条
        global _timeline
        _timeline.append({"t": time.time(), "type": event_type, "data": data})
        if len(_timeline) > 200:
            del _timeline[:len(_timeline) - 200]
        # 保存到当前帧的事件列表
        latest = battle_db.get(f"{self.current_battle_id}_latest")
        if latest:
            latest["events"].append(event)
            battle_db.set(f"{self.current_battle_id}_latest", latest)


# v36.0: 关键时刻时间线(内存, 复盘用)
_timeline = []


def get_recent_events(since_ts=None, limit=30):
    """返回最近关键时刻(时间线)。since_ts: 只取此时间戳之后; limit: 最多几条(取最新的)"""
    global _timeline
    evs = [e for e in _timeline if since_ts is None or e["t"] >= since_ts]
    return evs[-limit:]
    
    def get_battle_summary(self):
        """获取战斗摘要"""
        return {
            "battle_id": self.current_battle_id,
            "total_frames": self.frame_count,
            "duration": self.frame_count * self.record_interval,
            "start_time": self.current_battle_id.replace("battle_", "")
        }
    
    def get_frame_range(self, start_frame, end_frame):
        """获取指定帧范围的数据"""
        frames = []
        for i in range(start_frame, end_frame + 1):
            key = f"{self.current_battle_id}_frame_{i}"
            frame = battle_db.get(key)
            if frame:
                frames.append(frame)
        return frames


# 全局记录器实例
_recorder = None

def get_recorder():
    """获取记录器实例"""
    global _recorder
    if _recorder is None:
        _recorder = BattleRecorder()
    return _recorder


def record_frame(game_state):
    """记录一帧（便捷函数）"""
    recorder = get_recorder()
    return recorder.record(game_state)

def record_event(event_type, data):
    """记录事件（便捷函数）"""
    recorder = get_recorder()
    recorder.add_event(event_type, data)


# 测试
if __name__ == "__main__":
    # 模拟游戏状态
    test_state = {
        "player_x": 450,
        "player_y": 580,
        "player_hp": 500,
        "player_max_hp": 500,
        "player_angle": 1.5,
        "killed": 10,
        "wave": 3,
        "game_time": 30.5,
        "enemies": [
            {"id": 1, "x": 400, "y": 200, "hp": 80, "max_hp": 100, "angle": 3.14, "type": "grunt", "plan": "直攻", "alive": True},
            {"id": 2, "x": 500, "y": 300, "hp": 60, "max_hp": 100, "angle": 0, "type": "fast", "plan": "包抄", "alive": True}
        ],
        "player_bullets": [
            {"x": 450, "y": 550, "vx": 0, "vy": -10}
        ],
        "enemy_bullets": [
            {"x": 400, "y": 250, "vx": 2, "vy": 3}
        ],
        "enemy_camp": {"x": 450, "y": 100, "hp": 888, "max_hp": 888, "alive": True},
        "player_camp": {"x": 450, "y": 540, "hp": 888, "max_hp": 888, "alive": True}
    }
    
    # 记录几帧
    for i in range(3):
        record = record_frame(test_state)
        print(f"记录帧 #{record['frame']}: 敌人{len(record['enemies'])}个, 子弹{len(record['bullets'])}个")
        time.sleep(1.1)  # 超过记录间隔
    
    # 添加事件
    record_event("kill", {"enemy_id": 1, "player_hp": 500})
    
    # 获取摘要
    summary = get_recorder().get_battle_summary()
    print(f"\n战斗摘要: {json.dumps(summary, ensure_ascii=False)}")
