# v36.0 (2026-10-05) — 36aigame
# 战术效果数据库
# 版本: v36.0

import json
import os

# 数据库文件路径（v36.0: 修正硬编码 — 原路径写死到旧项目 23aigame，导致数据跨项目污染）
DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tactics_db.json")

# 默认战术数据
DEFAULT_TACTICS = {
    "右翼包抄": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
    "左翼包抄": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
    "佯退拉扯": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
    "方阵推进": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
    "集火攻击": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
    "直攻": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
    "压制": {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"},
}

def _load_db():
    """从文件加载数据库"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return DEFAULT_TACTICS.copy()
    return DEFAULT_TACTICS.copy()

def _save_db(data):
    """保存数据库到文件"""
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 加载数据库
TACTICS_DB = _load_db()

# v36.01: 写盘节流 — 内存实时累计，最多每30秒落盘一次(命中事件高频时原版每次写盘)
_SAVE_INTERVAL = 30.0
_last_save = [0.0]
_dirty = [False]

def _maybe_save(force=False):
    import time as _t
    now = _t.time()
    if force or (now - _last_save[0] >= _SAVE_INTERVAL):
        _save_db(TACTICS_DB)
        _last_save[0] = now
        _dirty[0] = False
    else:
        _dirty[0] = True

def flush():
    """v36.01: 强制立即落盘(游戏退出时调用)"""
    _maybe_save(force=True)

def record_tactic(tactic_name, hit=False, death=False):
    """记录战术效果并持久化
    
    参数:
        tactic_name: 战术名称
        hit: 是否命中玩家（True/False）- 只在玩家被击中时记录
        death: 是否阵亡（True/False）- 只在敌人死亡时记录
    """
    if tactic_name not in TACTICS_DB:
        # 动态添加新战术
        TACTICS_DB[tactic_name] = {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"}
    
    # 记录命中或阵亡（不增加used计数）
    # used计数应该在战术被分配时增加（在LLM生成指令时）
    if hit:
        TACTICS_DB[tactic_name]["hits"] += 1
    if death:
        TACTICS_DB[tactic_name]["deaths"] += 1
    
    # 计算效果
    used = TACTICS_DB[tactic_name]["used"]
    hits = TACTICS_DB[tactic_name]["hits"]
    deaths = TACTICS_DB[tactic_name]["deaths"]
    
    if used > 0:
        # 命中率 = 命中次数 / 使用次数（限制在0-1）
        hit_rate = min(1.0, hits / used)
        # 存活率 = 1 - (阵亡数 / 使用次数）（限制在0-1）
        survival_rate = max(0.0, min(1.0, 1.0 - (deaths / used)))
        # 综合效果 = 命中率 * 0.6 + 存活率 * 0.4（范围0-1）
        effectiveness = hit_rate * 0.6 + survival_rate * 0.4
        TACTICS_DB[tactic_name]["effectiveness"] = max(0.0, min(1.0, effectiveness))
        
        # 效果差就禁用（使用20次以上且效果<0.2）
        if TACTICS_DB[tactic_name]["effectiveness"] < 0.2 and used > 20:
            TACTICS_DB[tactic_name]["status"] = "disabled"
        # 效果好就激活（效果>0.5）
        elif TACTICS_DB[tactic_name]["effectiveness"] > 0.5 and used > 5:
            TACTICS_DB[tactic_name]["status"] = "active"
    
        # 持久化到文件（v36.01: 节流，不再每次写盘）
    _maybe_save()

def record_tactic_usage(tactic_name):
    """记录战术被使用（在LLM分配战术时调用）"""
    if tactic_name not in TACTICS_DB:
        TACTICS_DB[tactic_name] = {"used": 0, "hits": 0, "deaths": 0, "effectiveness": 0.0, "status": "active"}
    
    TACTICS_DB[tactic_name]["used"] += 1
    _maybe_save()

def get_valid_tactics():
    """获取有效的战术列表"""
    return [name for name, data in TACTICS_DB.items() if data["status"] == "active"]

def get_tactics_report():
    """生成战术效果报告"""
    report = []
    for name, data in TACTICS_DB.items():
        report.append(f"{name}: 使用{data['used']}次, 效果{data['effectiveness']:.2f}, 状态{data['status']}")
    return "\n".join(report)
