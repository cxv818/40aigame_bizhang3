# v36.0 (2026-10-05) — 36aigame
# 游戏专用数据库
# 版本: v12.0

from highspeed_db import get_db
import time

# 创建游戏数据库实例
game_state_db = get_db("game_state", "/tmp/hsdb_game_state.json", max_memory_size=100)
tactics_db = get_db("tactics", "/tmp/hsdb_tactics.json", max_memory_size=1000)
evolution_db = get_db("evolution", "/tmp/hsdb_evolution.json", max_memory_size=100)

def save_game_state(state):
    """保存游戏状态"""
    game_state_db.set("current_state", {
        "data": state,
        "timestamp": time.time()
    })

def load_game_state():
    """加载游戏状态"""
    result = game_state_db.get("current_state")
    if result:
        return result["data"]
    return None

def record_tactic_effect(tactic_name, hit=False, death=False):
    """记录战术效果"""
    key = f"tactic_{tactic_name}"
    data = tactics_db.get(key, {
        "used": 0,
        "hits": 0,
        "deaths": 0,
        "effectiveness": 0.0
    })
    
    data["used"] += 1
    if hit:
        data["hits"] += 1
    if death:
        data["deaths"] += 1
    
    # 计算效果
    if data["used"] > 0:
        hit_rate = data["hits"] / data["used"]
        death_rate = data["deaths"] / data["used"]
        data["effectiveness"] = hit_rate - death_rate
    
    tactics_db.set(key, data)

def get_tactic_stats(tactic_name):
    """获取战术统计"""
    key = f"tactic_{tactic_name}"
    return tactics_db.get(key, {
        "used": 0,
        "hits": 0,
        "deaths": 0,
        "effectiveness": 0.0
    })

def save_evolution_data(ai_name, generation, lessons):
    """保存进化数据"""
    key = f"evo_{ai_name}"
    data = evolution_db.get(key, [])
    data.append({
        "generation": generation,
        "lessons": lessons,
        "timestamp": time.time()
    })
    # 只保留最近100条
    data = data[-100:]
    evolution_db.set(key, data)

def get_evolution_history(ai_name):
    """获取进化历史"""
    key = f"evo_{ai_name}"
    return evolution_db.get(key, [])

def get_db_stats():
    """获取所有数据库统计"""
    return {
        "game_state": game_state_db.get_stats(),
        "tactics": tactics_db.get_stats(),
        "evolution": evolution_db.get_stats()
    }

# 测试
if __name__ == "__main__":
    import json
    
    # 测试游戏状态
    test_state = {
        "player_x": 450,
        "player_y": 580,
        "hp": 500,
        "enemies": 16
    }
    save_game_state(test_state)
    loaded = load_game_state()
    print(f"游戏状态: {json.dumps(loaded, ensure_ascii=False)}")
    
    # 测试战术记录
    record_tactic_effect("直攻", hit=True)
    record_tactic_effect("直攻", hit=True)
    record_tactic_effect("直攻", death=True)
    
    stats = get_tactic_stats("直攻")
    print(f"战术统计: {json.dumps(stats, ensure_ascii=False)}")
    
    # 测试进化记录
    save_evolution_data("曹操", 25, ["集火有效", "方阵保命"])
    history = get_evolution_history("曹操")
    print(f"进化历史: {len(history)}条")
    
    # 统计
    print(f"\n数据库统计:")
    for name, stats in get_db_stats().items():
        print(f"  {name}: {stats['memory_items']}项, 命中率{stats['hit_rate']}")
