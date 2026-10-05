# v36.0 (2026-10-05) — 36aigame
# ClusterPlanner(集群规划) / FormationManager(阵型) / BattleMemory(行为记忆) / AIDirector(三帅导演)
# 运行时上下文: main()/COMM 由调用方传入或 sys.modules 延迟读取, 不在此定义。
import json
import math
import os
import random
import re
import threading
import time
import urllib.request

import pygame

# 与主文件一致的环境端口
import os as _os
AI_PORT_1 = int(_os.environ.get("TANK_AI_PORT_1", 8080))
AI_PORT_2 = int(_os.environ.get("TANK_AI_PORT_2", 8081))
AI_PORT_3 = int(_os.environ.get("TANK_AI_PORT_3", 8082))
ADVISOR_PORT = int(_os.environ.get("TANK_ADVISOR_PORT", 8083))
EVO_DIR = _os.environ.get("TANK_EVO_DIR",
                          os.path.join(os.path.dirname(os.path.dirname(
                              os.path.abspath(__file__))), "config"))
RUNTIME_DIR = _os.environ.get("TANK_RUNTIME_DIR", "/tmp")
FAST_FILE = os.path.join(RUNTIME_DIR, "tank_fast.json")
SLOW_FILE = os.path.join(RUNTIME_DIR, "tank_battle_status.json")
WIDTH, HEIGHT = 1600, 1000

from channels import set_communicator  # noqa: F401 (AIDirector内引用)


def _get_COMM():
    """延迟读取主模块的 COMM(main() global赋值的 SquadComm 实例)。
    v36.0: 拆文件后类方法内不能直接读主模块全局, 用 sys.modules 延迟解析。"""
    import sys as _sys
    m = _sys.modules.get('tank_battle_deluxe')
    return getattr(m, 'COMM', None) if m else None


class ClusterPlanner:
    """集群规划器: 基于战场态势生成高级战术规划"""
    
    def __init__(self, commander_name):
        self.name = commander_name
        self.plans = {
            "钳形合围": {"desc": "两翼包抄,中路牵制", "min_units": 8, "priority": 1},
            "声东击西": {"desc": "佯攻一侧,主力突破", "min_units": 6, "priority": 2},
            "火力压制": {"desc": "集中火力,压制走位", "min_units": 10, "priority": 1},
            "铁壁合围": {"desc": "方阵推进,逐步压缩", "min_units": 12, "priority": 3},
            "游击袭扰": {"desc": "分散骚扰,消耗血量", "min_units": 4, "priority": 4},
            "集火秒杀": {"desc": "十台齐射,合火必杀", "min_units": 10, "priority": 1},
            "山地占领": {"desc": "抢占高地,火力覆盖", "min_units": 6, "priority": 2},
            "诱敌深入": {"desc": "佯退聚敌,围而歼之", "min_units": 8, "priority": 3},
        }
        self.current_plan = None
        self.plan_progress = 0
        self.objectives = []  # 当前目标列表
        
    def analyze_battlefield(self, snapshot):
        """分析战场态势,生成战略建议"""
        enemies = snapshot.get("enemies", [])
        player = snapshot.get("player", {})
        barricades = snapshot.get("barricades", [])
        hills = snapshot.get("hills", {})
        
        analysis = {
            "enemy_count": len(enemies),
            "player_hp": player.get("hp", 500),
            "player_max_hp": player.get("max_hp", 500),
            "player_weak": player.get("hp", 500) < 150,
            "player_strong": player.get("hp", 500) > 350,
            "has_barricades": len(barricades) > 0,
            "has_hills": hills.get("count", 0) > 0,
            "wave": snapshot.get("wave", 1),
            "boss_active": snapshot.get("boss", False),
        }
        
        # 根据态势选择最佳方案
        if analysis["player_weak"] and analysis["enemy_count"] >= 10:
            return "集火秒杀", "玩家残血,全力集火收割"
        elif analysis["has_hills"] and analysis["enemy_count"] >= 6:
            return "山地占领", "抢占高地建立火力点"
        elif analysis["enemy_count"] >= 12:
            return "铁壁合围", "兵力充足,方阵推进"
        elif analysis["has_barricades"] and analysis["enemy_count"] >= 8:
            return "诱敌深入", "利用屏障诱敌,围而歼之"
        elif analysis["enemy_count"] >= 8:
            return "钳形合围", "两翼包抄,中路牵制"
        elif analysis["enemy_count"] >= 6:
            return "声东击西", "佯攻一侧,主力突破"
        else:
            return "游击袭扰", "兵力不足,分散骚扰"
    
    def generate_objectives(self, plan_name, enemies, player):
        """生成具体作战目标"""
        objectives = []
        px, py = player.get("x", WIDTH//2), player.get("y", HEIGHT//2)
        
        if plan_name == "钳形合围":
            # 左翼、右翼、中路三组目标
            left_flank = [e for e in enemies if e["x"] < px][:5]
            right_flank = [e for e in enemies if e["x"] >= px][:5]
            center = [e for e in enemies][:3]
            objectives = [
                {"type": "flank_left", "units": [e["id"] for e in left_flank], "target": (px-200, py)},
                {"type": "flank_right", "units": [e["id"] for e in right_flank], "target": (px+200, py)},
                {"type": "press_center", "units": [e["id"] for e in center], "target": (px, py-150)},
            ]
        elif plan_name == "集火秒杀":
            # 所有单位集火玩家
            all_ids = [e["id"] for e in enemies[:15]]  # 最多15台
            objectives = [
                {"type": "concentrate_fire", "units": all_ids, "target": (px, py)},
            ]
        elif plan_name == "山地占领":
            # 抢占山地
            hill_positions = [(200, 200), (700, 200), (450, 300)]  # 预设山地位置
            for i, hill_pos in enumerate(hill_positions):
                hill_units = [e["id"] for e in enemies[i*3:(i+1)*3]]
                if hill_units:
                    objectives.append({"type": "occupy_hill", "units": hill_units, "target": hill_pos})
        elif plan_name == "铁壁合围":
            # 方阵推进
            formation_ids = [e["id"] for e in enemies[:12]]
            objectives = [
                {"type": "phalanx_advance", "units": formation_ids, "target": (px, py)},
            ]
        
        return objectives



class FormationManager:
    """阵型管理器: 管理各种战斗阵型"""
    
    FORMATIONS = {
        "wedge": {  # 楔形阵: 前锋突破
            "positions": [(0, 0), (-1, -1), (1, -1), (-2, -2), (2, -2)],
            "spacing": 45,
        },
        "line": {  # 横队阵: 火力覆盖
            "positions": [(-2, 0), (-1, 0), (0, 0), (1, 0), (2, 0)],
            "spacing": 50,
        },
        "circle": {  # 圆阵: 防御包围
            "positions": [(0, -1), (0.7, -0.7), (1, 0), (0.7, 0.7), (0, 1), 
                         (-0.7, 0.7), (-1, 0), (-0.7, -0.7)],
            "spacing": 40,
        },
        "echelon": {  # 梯次阵: 斜向突击
            "positions": [(0, 0), (-1, 1), (-2, 2), (-3, 3)],
            "spacing": 50,
        },
        "phalanx": {  # 方阵: 密集防御
            "positions": [(-1, -1), (0, -1), (1, -1), (-1, 0), (0, 0), (1, 0)],
            "spacing": 35,
        },
    }
    
    def __init__(self):
        self.active_formations = {}  # formation_id -> {type, units, center, facing}
        
    def create_formation(self, formation_type, unit_ids, center_pos, facing=0):
        """创建新阵型"""
        if formation_type not in self.FORMATIONS:
            return None
        
        formation_id = f"{formation_type}_{pygame.time.get_ticks()}"
        self.active_formations[formation_id] = {
            "type": formation_type,
            "units": set(unit_ids),
            "center": center_pos,
            "facing": facing,
            "created": pygame.time.get_ticks(),
        }
        return formation_id
    
    def get_formation_positions(self, formation_id):
        """获取阵型中各单位的目标位置"""
        if formation_id not in self.active_formations:
            return {}
        
        formation = self.active_formations[formation_id]
        formation_cfg = self.FORMATIONS[formation["type"]]
        positions = formation_cfg["positions"]
        spacing = formation_cfg["spacing"]
        cx, cy = formation["center"]
        facing = formation["facing"]
        
        # 根据朝向旋转位置
        cos_f = math.cos(facing)
        sin_f = math.sin(facing)
        
        result = {}
        for i, unit_id in enumerate(formation["units"]):
            if i >= len(positions):
                break
            px, py = positions[i]
            # 旋转并缩放
            rx = px * spacing * cos_f - py * spacing * sin_f
            ry = px * spacing * sin_f + py * spacing * cos_f
            result[unit_id] = (cx + rx, cy + ry)
        
        return result
    
    def update_formation(self, formation_id, new_center=None, new_facing=None):
        """更新阵型位置和朝向"""
        if formation_id not in self.active_formations:
            return
        if new_center:
            self.active_formations[formation_id]["center"] = new_center
        if new_facing is not None:
            self.active_formations[formation_id]["facing"] = new_facing
    
    def disband_formation(self, formation_id):
        """解散阵型"""
        self.active_formations.pop(formation_id, None)
    
    def get_unit_formation(self, unit_id):
        """获取单位所属的阵型"""
        for fid, f in self.active_formations.items():
            if unit_id in f["units"]:
                return fid
        return None


# v36.0: 曹操36计选计器 — 便捷访问(导入失败不影响游戏)
try:
    from stratagem_llm import get_stratagem as _get_stratagem
    def _stratagem_block():
        try:
            return _get_stratagem().prompt_block()
        except Exception as _e:
            _swallow("strat_inject", _e)  # v33.03留痕
            return ""
except Exception:
    def _stratagem_block():
        return ""


# ---------- 军师频道 AdvisorChannel 已拆至 channels.py (v36.0, 旧定义已移除) ----------

class BattleMemory:
    """战场记忆库: 记录和学习玩家行为模式"""
    
    def __init__(self, max_history=100):
        self.player_positions = []  # 玩家位置历史
        self.player_actions = []    # 玩家行为历史
        self.engagement_results = []  # 交战结果
        self.max_history = max_history
        self.player_behavior_pattern = {
            "preferred_direction": None,  # 偏好移动方向
            "retreat_threshold": 0.3,     # 撤退血量阈值
            "aggression_level": 0.5,      # 侵略性
            "barricade_usage": 0,         # 屏障使用频率
            "hill_preference": 0,         # 山地偏好
        }
        
    def record_player_position(self, x, y, hp, timestamp):
        """记录玩家位置"""
        self.player_positions.append({
            "x": x, "y": y, "hp": hp, "t": timestamp
        })
        if len(self.player_positions) > self.max_history:
            self.player_positions.pop(0)
    
    def record_engagement(self, enemies_involved, hits_dealt, hits_taken, duration):
        """记录交战结果"""
        self.engagement_results.append({
            "enemies": enemies_involved,
            "hits_dealt": hits_dealt,
            "hits_taken": hits_taken,
            "duration": duration,
            "efficiency": hits_dealt / max(hits_taken, 1),
        })
        if len(self.engagement_results) > 50:
            self.engagement_results.pop(0)
    
    def analyze_player_behavior(self):
        """分析玩家行为模式"""
        if len(self.player_positions) < 10:
            return self.player_behavior_pattern
        
        # 分析移动偏好
        recent = self.player_positions[-20:]
        dx = sum(p["x"] - self.player_positions[-1]["x"] for p in recent) / len(recent)
        dy = sum(p["y"] - self.player_positions[-1]["y"] for p in recent) / len(recent)
        
        if abs(dx) > abs(dy):
            self.player_behavior_pattern["preferred_direction"] = "horizontal"
        else:
            self.player_behavior_pattern["preferred_direction"] = "vertical"
        
        # 分析侵略性
        hp_changes = [self.player_positions[i]["hp"] - self.player_positions[i-1]["hp"] 
                     for i in range(1, len(recent))]
        damage_taken = sum(-h for h in hp_changes if h < 0)
        self.player_behavior_pattern["aggression_level"] = min(1.0, damage_taken / 100)
        
        return self.player_behavior_pattern
    
    def predict_player_movement(self, current_pos, time_horizon=60):
        """预测玩家未来位置"""
        if len(self.player_positions) < 5:
            return current_pos
        
        # 基于最近移动趋势预测
        recent = self.player_positions[-10:]
        avg_dx = sum(recent[i]["x"] - recent[i-1]["x"] 
                    for i in range(1, len(recent))) / (len(recent) - 1)
        avg_dy = sum(recent[i]["y"] - recent[i-1]["y"] 
                    for i in range(1, len(recent))) / (len(recent) - 1)
        
        # 考虑边界反弹
        predicted_x = current_pos[0] + avg_dx * time_horizon
        predicted_y = current_pos[1] + avg_dy * time_horizon
        
        predicted_x = max(40, min(WIDTH - 40, predicted_x))
        predicted_y = max(40, min(HEIGHT - 40, predicted_y))
        
        return (predicted_x, predicted_y)


# ============ AI 指挥官 ============

def _timeline_text(since_seconds=120, limit=20):
    """本波关键时刻时间线文本(供复盘提示词)。取最近 since_seconds 秒内事件。"""
    try:
        import time as _t
        from battle_recorder import get_recent_events
        evs = get_recent_events(since_ts=_t.time() - since_seconds, limit=limit)
        if not evs:
            return ""
        lines = ["\n本波关键时刻时间线:"]
        t0 = evs[0]["t"]
        for e in evs:
            d = e.get("data") or {}
            brief = ",".join(f"{k}={v}" for k, v in list(d.items())[:3])
            lines.append(f"  {e['t']-t0:.0f}s {e['type']} {brief}")
        return "\n".join(lines) + "\n(据此分析战术成功/失败的因果)\n"
    except Exception:
        return ""


class AIDirector:
    """调用本地 LLM (llama-server) 为敌人生成战术指令；失败时回退规则 AI。"""

    def __init__(self, enabled=True, name="曹操", api_port=8080):
        self.enabled = enabled
        self.name = name
        self.api_port = api_port
        # RLock: worker 持锁期间会调 coord_brief()/status() 二次加锁(fd51503 死锁修复)
        self.lock = threading.RLock()
        self.orders = {}          # enemy_id -> dict(dir=角度, fire=bool, strafe=0/1)
        self.pending = False
        self.last_result = "待机"
        self.last_latency = 0.0
        self.last_request = 0.0
        # --- LLM 服务器自检:每5s轻量探测 /health(不占推理槽) ---
        self.health_ok = None      # None=未探测 True/False=结果
        self.health_msg = ""       # 附带原因(超时/拒绝/异常)
        self._health_stop = False
        self._health_thread = threading.Thread(
            target=self._health_loop, daemon=True)
        self._health_thread.start()
        # --- 自我进化:战果统计 + 教训代际传承 ---
        self.lessons = []         # 现役教训库(进化保留有效项)
        self.generation = 0       # 进化代数
        self.plan_stats = {}      # 方案名 -> {issued,hits,deaths} 跨波累积
        _evo_name = {"曹操": "evolution.json", "夏侯惇": "evolution_dun.json",
                     "夏侯渊": "evolution_yuan.json"}.get(self.name, "evolution.json")
        self._evo_path = os.path.join(EVO_DIR, _evo_name)  # 进化存档(跨局持久化,按武将分档)
        self.REVIEW_COOLDOWN = 120  # 进化冷却: 教训至少实战验证2分钟才允许下一代
        self._last_review = 0       # 上次进化时间戳(冷却起点)
        self._load_evolution()
        self.current_plan = None  # 当前执行的方案(归因用)
        self.stats = {"deaths": 0, "hits": 0, "orders": 0}  # 本波战损
        self.last_plans = []      # 本波先后下达的方案名
        self.phalanx_stats = {"formed": 0, "members": 0, "hits_during": 0}  # 方阵壁垒战果(注入复盘)
        # 联盟战术板: 三帅共享, key=帅名 value="主力方案x次数 第N代" (决策prompt互相可见)
        if not hasattr(AIDirector, "_alliance_board"):
            AIDirector._alliance_board = {}
        self.phalanx_feedback = ""  # 方阵指令回执(台数不足等,注入下轮决策prompt)
        self.review_pending = False
        self.commanded = set()    # 曾被指挥过的敌坦编号(用于待机判定)
        # --- 新增: 高级集群作战调度系统 ---
        self.cluster_planner = ClusterPlanner(self.name)  # 集群规划器
        self.formation_mgr = FormationManager()             # 阵型管理器
        self.battle_memory = BattleMemory()                 # 战场记忆库
        self.tactical_queue = []                            # 战术执行队列
        self.strategic_phase = "probe"                      # 战略阶段: probe/press/annihilate
        self.player_behavior_model = {}                     # 玩家行为模型
        # --- LLM 互相通讯 ---
        self.intercom = None  # 在主循环中统一设置

    def toggle(self):
        self.enabled = not self.enabled
        if not self.enabled:
            self.orders = {}
            self.last_result = "已关闭"

    # --- 新增: 高级集群作战调度 ---
    def execute_advanced_tactics(self, snapshot, valid_ids):
        """执行高级集群战术调度（20秒冷却，本地计算无阻塞）"""
        if not self.enabled or self.pending:
            return
        if time.time() - self.last_request < 60.0:
            return
        self.last_request = time.time()
        
        # 1. 分析战场态势（纯本地计算，无阻塞）
        plan_name, plan_reason = self.cluster_planner.analyze_battlefield(snapshot)
        
        # 2. 更新战场记忆
        player = snapshot.get("player", {})
        self.battle_memory.record_player_position(
            player.get("x", WIDTH//2), 
            player.get("y", HEIGHT//2),
            player.get("hp", 500),
            pygame.time.get_ticks()
        )
        
        # 3. 分析玩家行为
        behavior = self.battle_memory.analyze_player_behavior()
        
        # 4. 预测玩家位置
        predicted_pos = self.battle_memory.predict_player_movement(
            (player.get("x", WIDTH//2), player.get("y", HEIGHT//2))
        )
        
        # 5. 生成作战目标
        enemies = snapshot.get("enemies", [])
        objectives = self.cluster_planner.generate_objectives(plan_name, enemies, player)
        
        # 6. 构建增强型提示词
        enhanced_prompt = self._build_enhanced_prompt(
            snapshot, plan_name, plan_reason, objectives, 
            behavior, predicted_pos
        )
        
        # 7. 发送给 LLM（异步线程，不阻塞主循环）
        self._send_enhanced_request(enhanced_prompt, valid_ids, plan_name)
    
    def _build_enhanced_prompt(self, snapshot, plan_name, plan_reason, 
                               objectives, behavior, predicted_pos):
        """构建增强型战术提示词"""
        lines = []
        for e in snapshot.get("enemies", []):
            role = f",当前角色:{e.get('role', '')}" if e.get("role") else ""
            lines.append(
                f"敌{e['id']}({e['kind']}{role},HP{e['hp']}/{e['max_hp']},"
                f"距玩家{e['dist']:.0f},坐标{e['x']:.0f},{e['y']:.0f})"
            )
        
        p = snapshot.get("player", {})
        
        # 玩家行为分析
        behavior_text = (
            f"\n玩家行为分析:\n"
            f"- 移动偏好: {behavior.get('preferred_direction', '未知')}\n"
            f"- 侵略性: {behavior.get('aggression_level', 0.5):.2f}\n"
            f"- 预测位置(1秒后): ({predicted_pos[0]:.0f}, {predicted_pos[1]:.0f})\n"
        )
        
        # 作战目标
        obj_text = "\n作战目标:\n"
        for i, obj in enumerate(objectives[:3], 1):
            obj_text += f"{i}. {obj['type']}: 单位{obj['units'][:5]}... -> 目标{obj['target']}\n"
        
        # 战略阶段建议
        phase_guide = {
            "probe": "试探阶段: 分散侦察,摸清玩家习惯",
            "press": "压制阶段: 集中火力,压缩活动空间",
            "annihilate": "歼灭阶段: 全力集火,不给喘息",
        }
        # v36.0: 曹操已定之计 → 硬约束注入(高级调度路径同样联动)
        _sblock = _stratagem_block()
        
        # 阵型建议
        formation_guide = ""
        if plan_name in ["铁壁合围", "方阵推进"]:
            formation_guide = "建议阵型: 方阵(phalanx) - 密集防御,逐步推进\n"
        elif plan_name in ["钳形合围", "两翼包抄"]:
            formation_guide = "建议阵型: 楔形(wedge) - 前锋突破,两翼展开\n"
        elif plan_name == "集火秒杀":
            formation_guide = "建议阵型: 横队(line) - 一字排开,火力覆盖\n"
        
        prompt = (
            f"你是{self.name}，魏军主帅，统领全军。\n"
            f"\n【三将军事集团】\n"
            f"你和你的副将是一个整体，必须协同作战：\n"
            f"- 夏侯惇（左翼副将）：负责左翼包抄、防守、方阵推进\n"
            f"- 夏侯渊（右翼副将）：负责右翼突袭、快速穿插、游击袭扰\n"
            f"- 你自己（中军主帅）：负责全局指挥、中路突破、技能支援\n"
            f"\n【宏观调度要求 - 必须严格执行】\n"
            f"1. 统一指挥：所有敌人由你统一调度，分配任务给三将\n"
            f"2. 协同作战：\n"
            f"   - 左翼包抄 + 右翼牵制 + 中路突破 = 合围之势\n"
            f"   - 三将必须同时进攻，形成钳形攻势\n"
            f"   - 禁止各自为战，必须互相配合\n"
            f"3. 智能分配：\n"
            f"   - 左侧敌人 → 分配给夏侯惇（左翼）\n"
            f"   - 右侧敌人 → 分配给夏侯渊（右翼）\n"
            f"   - 中路敌人 → 由你亲自指挥（中军）\n"
            f"4. 阵型要求：\n"
            f"   - 钳形合围：左翼、右翼同时包抄，中路牵制\n"
            f"   - 方阵推进：密集防御，逐步压缩玩家空间\n"
            f"   - 集火秒杀：三将同时集火，触发合火必杀\n"
            f"5. 战略目标（优先级排序 - 必须严格执行）：\n"
            f"   - 【第一优先级】保护己方大营（绝对不能让大营被攻破！）\n"
            f"   - 【第二优先级】攻破吕布大营（波次>3时全力攻击）\n"
            f"   - 【第三优先级】保护自己和副将（不要送死，保存实力）\n"
            f"   - 【第四优先级】击杀吕布（玩家）\n"
            f"   - 【战术目标】三将协同，形成合围之势\n"
            f"\n当前执行战略: 『{plan_name}』({plan_reason})\n"
            f"战略阶段: {self.strategic_phase} - {phase_guide.get(self.strategic_phase, '')}\n"
            f"{_sblock}"
            f"{formation_guide}"
            f"{behavior_text}"
            f"{obj_text}"
            f"\n战场:\n" + "\n".join(lines) + "\n"
            f"玩家: 坐标({p.get('x', 0):.0f},{p.get('y', 0):.0f}) "
            f"HP{p.get('hp', 500):.0f}/{p.get('max_hp', 500)}\n"
            f"波次{snapshot.get('wave', 1)} "
            f"Boss{'在场' if snapshot.get('boss') else '不在场'}\n"
            f"\n高级调度要求（优先级排序）:\n"
            f"1. 【最高优先级】保护己方大营！如果大营受攻击，立即回防！\n"
            f"2. 【第二优先级】攻击敌方大营（波次>3时，target=\"pcamp\"）\n"
            f"3. 【第三优先级】保护将领！曹操、夏侯惇、夏侯渊血量低时必须撤退！\n"
            f"4. 按作战目标分配单位,每组至少3台\n"
            f"5. 考虑玩家预测位置,提前布防\n"
            f"6. 保留20%兵力作为预备队\n"
            f"7. 优先保护残血单位,让其退到后排\n"
            f"8. 狙击手优先占领高地或侧翼\n"
            f"9. 集火时确保≥10台同角度,触发合火必杀\n"
            f"10. target字段: \"pcamp\"=攻敌方大营;留空=打玩家(默认)\n"
            f"\n【输出格式 - 必须包含target字段】\n"
            f'[{{"ids":[敌编号],"plan":"{plan_name}",'
            f'"dir":角度偏移(-1到1),"fire":1或0,"strafe":1或0,"target":"pcamp或留空"}}]\n'
            f"\n【重要提醒】\n"
            f"- 每个指令必须包含target字段\n"
            f"- 波次>3时，60%的指令target必须是'pcamp'（攻大营）\n"
            f"- 40%的指令target可以留空（打玩家）\n"
            f"- 不指定target字段是错误的！\n"
            f"\n只输出JSON数组。"
        )
        return prompt
    
    def _send_enhanced_request(self, prompt, valid_ids, plan_name="高级调度"):
        """发送增强型请求到 LLM（异步线程，不阻塞主循环）"""
        if self.pending:
            return
        self.pending = True
        
        def worker():
            try:
                from llm_client import ask as _llm_ask  # v36.0: 统一出口
                text, latency = _llm_ask(self.api_port, prompt=prompt,
                                         max_tokens=1000, temperature=0.6, timeout=20)
                
                orders = self._parse_orders(text, valid_ids, comm=_get_COMM())
                
                # 强制战术多样化（与基础调度路径同规则，防止单一态势判定导致全队同战术）
                if orders:
                    self._enforce_tactic_diversity(orders)
                
                with self.lock:
                    if orders:
                        valid_now = {k: v for k, v in self.orders.items() if k in valid_ids}
                        self.orders = {**valid_now, **orders}
                        self.commanded.update(orders.keys())
                        self.last_result = f"AI高级调度 {len(orders)}条指令"
                        self.stats["orders"] += 1
                        # 记录战术统计（修复：高级调度路径缺少plan_stats记录）
                        for od in orders.values():
                            self.last_plans.append(od["plan"])
                            ps = self.plan_stats.setdefault(
                                od["plan"], {"issued": 0, "hits": 0, "deaths": 0})
                            ps["issued"] += 1
                        self.current_plan = plan_name
                    else:
                        self.last_result = "高级调度解析失败"
                    self.last_latency = latency
                    
            except Exception as exc:
                with self.lock:
                    self.last_result = f"高级调度离线({type(exc).__name__})"
            finally:
                self.pending = False
        
        threading.Thread(target=worker, daemon=True).start()
    
    def update_strategic_phase(self, player_hp, player_max, wave):
        """根据战况更新战略阶段"""
        hp_ratio = player_hp / player_max
        
        if wave <= 3:
            self.strategic_phase = "probe"
        elif hp_ratio < 0.3:
            self.strategic_phase = "annihilate"
        elif hp_ratio < 0.6 or wave > 10:
            self.strategic_phase = "press"
        else:
            self.strategic_phase = "probe"
    
    def create_formation(self, formation_type, unit_ids, center, facing=0):
        """创建战斗阵型"""
        return self.formation_mgr.create_formation(formation_type, unit_ids, center, facing)
    
    def get_formation_target(self, unit_id):
        """获取单位在阵型中的目标位置"""
        formation_id = self.formation_mgr.get_unit_formation(unit_id)
        if formation_id:
            positions = self.formation_mgr.get_formation_positions(formation_id)
            return positions.get(unit_id)
        return None

    # --- 提示词 ---
    def _build_prompt(self, snapshot):
        lines = []
        for e in snapshot["enemies"]:
            role = f",当前角色:{e["role"]}" if e.get("role") else ""
            lines.append(
                f"敌{e['id']}({e['kind']}{role},HP{e['hp']}/{e['max_hp']},"
                f"距玩家{e['dist']:.0f},坐标{e['x']:.0f},{e['y']:.0f})")
        p = snapshot["player"]
        # 吕布红墙情报: 坐标/半径/朝向/剩余寿命,给足绕行依据(此前是盲人摸墙)
        _barr_info = ""
        if snapshot.get("barricades"):
            _bl = ";".join(
                f"圆心({b['x']},{b['y']})R{b['r']}弧口朝{b['facing']}弧度"
                f"剩{b['life_left_s']}s"
                for b in snapshot["barricades"])
            _barr_info = ("⚠吕布烈璧障在场(红色半圆环,挡你的坦克移动,你的坦克撞墙会滑向弧口边缘):\n"
                          f"  {_bl}\n"
                          "  被墙挡住的单位务必改用 strafe=1 环绕走位+调整dir,沿墙弧面滑向弧口两侧包抄;\n"
                          "  或下令远离墙体重新集结,不要让部队顶在弧面上堆叠。硬顶无意义,墙剩余寿命有限。\n")
        hill_info = ""
        if snapshot.get("hills"):
            hs = snapshot["hills"]
            hill_info = (f"山地战场: {hs['count']}块迷彩山(绿/黄随机),"
                         f"中心点: " + ";".join(f"({h['x']},{h['y']})" for h in hs['blocks']) + "\n"
                         "地形规则: 敌坦在山上射速x2(火力压制力大增),"
                         "且总指挥每维持占山压制持续加分(击杀玩家+500)。"
                         "战术建议: 优先抢占山上建立火力点沿山绕行,"
                         "在山上集火充能效率更高。\n")
        _persona = ""
        if self.name == "夏侯惇":
            _persona = ("你是夏侯惇,魏军副将,治军稳健:擅长阵地压制/山地火力点/方阵壁垒,"
                        "打法偏稳,稳扎稳打,亲兵队约10台(编号除3余2)。\n")
        elif self.name == "夏侯渊":
            _persona = ("你是夏侯渊,魏军副将,用兵神速:擅长急袭/包抄/佯退拉扯,"
                        "打法偏机动,千里奔袭,亲兵队约10台(编号除3余1)。\n")
        _board = getattr(AIDirector, "_alliance_board", {})
        _others = "; ".join(v for k, v in _board.items() if k != self.name)
        _ally_info = (f"\n盟军协同情报(三帅战术板): {_others}\n"
                      "协同要求: 你的方案要与其他两镇互补,不要三镇全挤同一战术。\n"
                      if _others else "")
        # 大营情报
        _camp_info = ""
        if snapshot.get("player_camp"):
            pc = snapshot["player_camp"]
            _camp_info = f"\n⚠我军大营(必须保护): 坐标({pc['x']:.0f},{pc['y']:.0f}) HP{pc['hp']}/5000\n"
        if snapshot.get("enemy_camp"):
            ec = snapshot["enemy_camp"]
            _camp_info += f"⚠敌军大营(攻击目标): 坐标({ec['x']:.0f},{ec['y']:.0f}) HP{ec['hp']}/5000\n"
        # 三国杀: 三将在场情报(警告保护)
        _gen_alive = snapshot.get("generals_alive") or []
        if _gen_alive:
            _camp_info += f"⚠我方武将在场: {','.join(_gen_alive)} — 武将被吕布击杀则亲兵禁进化,务必保护!\n"
        
        # 读取战场数据库分析（异步缓存，避免阻塞主线程）
        battle_analysis = ""
        try:
            # 使用异步缓存的数据，避免直接读取大文件
            from battle_recorder import get_cached_analysis
            battle_analysis = get_cached_analysis()
            if not battle_analysis:
                battle_analysis = "\n📊战场数据: 暂无实时分析\n"
        except Exception:
            battle_analysis = "\n📊战场数据: 分析系统初始化中\n"
        
        # 导入战术数据库（使用缓存）
        tactics_stats = ""
        try:
            from tactics_db import TACTICS_DB, get_valid_tactics
            valid_tactics = get_valid_tactics()
            tactics_info = "有效战术:" + ",".join(valid_tactics) + "\n"
            # v36.0: 双口径合并视图([发令]/[命中记]各自自洽)替代单一口径裸数字
            from stats_view import get_merged_report
            tactics_stats = "\n" + get_merged_report(self.plan_stats) + "\n"
        except Exception as e:
            tactics_info = ""
            tactics_stats = "\n📈战术效果统计: 数据库加载中...\n"
        
        prompt = (
            "你是魏军" + self.name + "，负责指挥坦克作战。\n"
            "重要：你必须使用多种战术，否则会被判定为指挥失误！\n"
            "\n"
            + battle_analysis
            + tactics_stats
            # v36.0: 曹操已定之计 → 硬约束注入(计策与战术联动)
            + _stratagem_block()
            + "\n"
            "【强制规则 - 不遵守将战败】\n"
            "1. 必须分配至少3种不同战术！\n"
            "2. 每种战术最多只能给40%的坦克！\n"
            "3. 禁止所有坦克用同一战术！\n"
            "4. 必须包含『直攻』和『集火』两种战术！\n"
            "\n"
            "【推荐分配比例】\n"
            "- 直攻：30%坦克（正面冲锋）\n"
            "- 集火：30%坦克（远程齐射）\n"
            "- 方阵：20%坦克（组成壁垒）\n"
            "- 游击：20%坦克（侧翼骚扰）\n"
            "\n"
            "【检查清单 - 必须全部打勾】\n"
            "☑ 是否用了3种以上战术？\n"
            "☑ 是否有坦克用『直攻』？\n"
            "☑ 是否有坦克用『集火』？\n"
            "☑ 是否有坦克用『方阵』或『游击』？\n"
            "☑ 最大战术占比是否≤40%？\n"
            "\n"
            "【可用战术】\n"
            "- 直攻：直接朝玩家移动并开火\n"
            "- 集火：多台同方向齐射\n"
            "- 方阵：≥5台紧贴,免疫伤害(但无法开火)\n"
            "- 游击：灵活移动,骚扰玩家\n"
            "\n"
            "【禁用战术】\n"
            "- 右翼包抄：效果太差已禁用\n"
            "- 佯退拉扯：效果太差已禁用\n"
            "- 山地占领：效果太差已禁用\n"
            "\n"
            + _ally_info + "战场:\n"
            + _persona
            + _barr_info
            + "\n".join(lines)
            + f"\n玩家: 坐标({p['x']:.0f},{p['y']:.0f}) HP{p['hp']:.0f}/{p['max_hp']}"
            + (" ←玩家残血!全力收割!\n" if p['hp'] < 100 else
               " ←玩家血量高,攒集火\n" if p['hp'] > 300 else "")
            + _camp_info
            + f" 波次{snapshot['wave']}\n"
            + tactics_info
            + "⚠方阵: ≥5台紧贴(间距≤62px),免疫玩家子弹,但无法开火。方阵内fire=0\n"
            + "⚠集火: ≥10台同方向(±0.05弧度)齐射,合成万倍杀伤弹\n"
            + "⚠【必须】target字段: 留空=打吕布本人;\"pcamp\"=攻吕布大营(波次>3时必须用!)"
              f"(当前波次{'可攻!必须派≥60%兵力target=pcamp攻大营!' if snapshot.get('wave',1)>3 else '未激活,波次>3才能攻'})\n"
            + "\n"
            "【输出要求】\n"
            "1. 先检查是否满足强制规则\n"
            "2. 确保使用3种以上战术\n"
            "3. 确保包含『直攻』和『集火』\n"
            "4. 输出JSON数组\n"
            "\n"
            "输出JSON数组,同方案合并,压缩输出:\n"
            '[{"ids":[编号],"plan":"简称","dir":角度,"fire":0/1,"strafe":0/1,"target":"player或pcamp"}]\n'
            "只输出JSON。")
        return prompt

    def _query(self, snapshot):
        # v36.0: 统一出口(llm_client已内置reasoning_content兜底)
        # max_tokens=800: 400会截断多敌JSON(实测10+台必超),导致"无法解析"误报
        from llm_client import ask as _llm_ask
        return _llm_ask(self.api_port, prompt=self._build_prompt(snapshot),
                        max_tokens=800, temperature=0.7, timeout=25)

    def _load_evolution(self):
        """启动时读进化存档,继承代数/教训/方案谱系(没有则第0代)。"""
        try:
            with open(self._evo_path, encoding="utf-8") as f:
                evo = json.load(f)
            self.generation = int(evo.get("generation", 0))
            self.lessons = list(evo.get("lessons", []))[:8]
            self.plan_stats = evo.get("plan_stats", {})
            if _get_COMM():
                _get_COMM().say(self.name, f"继承存档: 第{self.generation}代 "
                         f"教训{len(self.lessons)}条")
        except FileNotFoundError:
            pass
        except Exception:
            pass  # 存档损坏则从零开始,不影响游戏

    def save_evolution(self):
        """进化后立即写盘(原子写,防半截文件)。"""
        import os as _os
        try:
            tmp = self._evo_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"generation": self.generation,
                           "lessons": self.lessons,
                           "plan_stats": self.plan_stats,
                           "total_kills": getattr(self, "_total_kills", 0),
                           "updated": time.strftime("%Y-%m-%d %H:%M:%S")},
                          f, ensure_ascii=False, indent=1)
            _os.replace(tmp, self._evo_path)
        except Exception:
            pass  # 存档失败不影响游戏

    def _parse_orders(self, text, valid_ids, comm=None):
        orders = {}
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            return orders
        try:
            arr = json.loads(m.group(0))
        except Exception:
            return orders
        if not isinstance(arr, list):
            return orders
        plan_name = None
        for item in arr:
            if not isinstance(item, dict):
                continue
            # 兼容两种格式: ids分组数组(压缩模式) 或 单个id(旧行为)
            raw_ids = item.get("ids", [item.get("id", -1)])
            if not isinstance(raw_ids, list):
                raw_ids = [raw_ids]
            eids = []
            for raw in raw_ids:
                try:
                    eid = int(raw)
                except (TypeError, ValueError):
                    continue
                if eid in valid_ids:
                    eids.append(eid)
            if not eids:
                continue
            pn = str(item.get("plan", "") or "")[:8]
            if pn and not plan_name:
                plan_name = pn
            try:
                d = float(item.get("dir", 0))
            except (TypeError, ValueError):
                d = 0.0
            d = max(-1.5, min(1.5, d))
            fire = 1 if item.get("fire") in (1, True, "1") else 0
            try:
                strafe = 1 if int(item.get("strafe", 0)) else 0
            except (TypeError, ValueError):
                strafe = 0
            for eid in eids:  # 同组敌坦共享同一道指令
                orders[eid] = {"dir": d, "fire": fire, "strafe": strafe,
                               "plan": pn or plan_name or "协同作战",
                               "target": str(item.get("target", ""))[:8]}
        # 总指挥方案广播到战术频道
        if comm is not None and orders:
            comm.say(self.name, f"全队执行『{plan_name or '协同作战'}』")
            for eid, od in orders.items():
                comm.say(self.name, f"{eid}号 → {od['plan']}")
        return orders

    def _health_loop(self):
        """每5秒探测一次 llama-server;只改自检状态,不碰推理结果。"""
        while not self._health_stop:
            ok, msg = False, ""
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.api_port}/health",
                    timeout=2) as r:
                    ok = r.status == 200
                    if not ok:
                        msg = f"HTTP{r.status}"
            except Exception as exc:
                msg = type(exc).__name__
            with self.lock:
                self.health_ok = ok
                self.health_msg = msg
            time.sleep(120)

    def request_async(self, snapshot, valid_ids):
        """非阻塞发起一次请求（有 lock 防重入）。"""
        if not self.enabled or self.pending:
            return
        if time.time() - self.last_request < 60.0:
            return
        self.last_request = time.time()
        self.pending = True

        def worker():
            try:
                text, lat = self._query(snapshot)
                orders = self._parse_orders(text, valid_ids,
                                            comm=_get_COMM() if _get_COMM() else None)
                with self.lock:
                    # 解析失败时保留旧订单,只更新有效id(新兵立刻归AI管)
                    if orders:
                        valid_now = {k: v for k, v in self.orders.items() if k in valid_ids}
                        self.orders = {**valid_now, **orders}
                        self.commanded.update(orders.keys())  # 标记已指挥
                        self.last_result = f"AI在线 {len(orders)}条指令"
                        self.stats["orders"] += 1
                        for od in orders.values():
                            self.last_plans.append(od["plan"])
                            ps = self.plan_stats.setdefault(
                                od["plan"], {"issued": 0, "hits": 0, "deaths": 0})
                            ps["issued"] += 1
                        # 强制战术多样化检查
                        if orders:
                            import sys
                            plans_before = set(od.get('plan', '') for od in orders.values())
                            print(f"[DEBUG] 强制多样化前: {plans_before}", flush=True)
                            self._enforce_tactic_diversity(orders)
                            plans_after = set(od.get('plan', '') for od in orders.values())
                            print(f"[DEBUG] 强制多样化后: {plans_after}", flush=True)
                            sys.stdout.flush()
                        
                        # 方阵指令回执: 台数不足时告知总指挥(下轮prompt),治35B数不清
                        _ph_ids = [i for i, od in orders.items()
                                   if "方阵" in od.get("plan", "")]
                        if 0 < len(_ph_ids) < 5:
                            self.phalanx_feedback = (
                                f"上轮方阵指令只有{len(_ph_ids)}台"
                                f"(ids:{_ph_ids}),未达5台门槛未成阵!必须凑≥5台")
                        self.current_plan = next(iter(orders.values()))["plan"]
                        # 方案谱系上限 10,防膨胀
                        if len(self.plan_stats) > 10:
                            for k in list(self.plan_stats)[:2]:
                                self.plan_stats.pop(k, None)
                        self.last_plans = self.last_plans[-6:]
                        # 更新联盟战术板(三帅互见)
                        try:
                            AIDirector._alliance_board[self.name] = self.coord_brief()
                        except Exception:
                            pass
                    else:
                        # 解析失败也保留旧订单(AI全权控制模式)
                        self.last_result = "AI返回无法解析"
                    self.last_latency = lat
            except Exception as exc:
                with self.lock:
                    # 请求失败不再清空订单:AI全权控制模式下沿用旧指令,防站桩
                    self.last_result = f"AI离线({type(exc).__name__}:{str(exc)[:50]})"
            finally:
                self.pending = False

        threading.Thread(target=worker, daemon=True).start()

    # --- 自我进化 ---
    def note_death(self, eid=None, plan=None):
        with self.lock:
            self.stats["deaths"] += 1
            self._total_kills = getattr(self, "_total_kills", 0) + 1  # 历史总击杀(进存档)
            if eid is not None:
                self.orders.pop(eid, None)  # 阵亡者的订单同步清除
            cp = plan or self.current_plan  # 阵亡者自己执行的方案,非全局首方案
            if cp and cp in self.plan_stats:
                self.plan_stats[cp]["deaths"] += 1

    def _enforce_tactic_diversity(self, orders):
        """强制战术多样化：如果LLM输出单一战术，强制修改为多种战术"""
        if not orders:
            return
            
        # 统计当前战术
        tactic_counts = {}
        for eid, od in orders.items():
            plan = od.get("plan", "")
            tactic_counts[plan] = tactic_counts.get(plan, 0) + 1
        
        total = len(orders)
        if total == 0:
            return
            
        # 检查是否需要强制多样化
        max_count = max(tactic_counts.values())
        max_ratio = max_count / total
        
        # 如果最大占比超过50%，强制修改
        if max_ratio > 0.5 or len(tactic_counts) < 3:
            # 强制分配战术
            forced_tactics = ["直攻", "集火", "方阵", "游击"]
            
            # 计算每种战术应该分配的数量
            eids = list(orders.keys())
            
            # 确保至少3种战术
            num_tactics = min(4, max(3, len(eids) // 3))
            tactics_to_use = forced_tactics[:num_tactics]
            
            # 分配战术
            for i, eid in enumerate(eids):
                tactic_idx = i % num_tactics
                new_tactic = tactics_to_use[tactic_idx]
                
                # 修改订单
                if eid in orders:
                    orders[eid]["plan"] = new_tactic
                    # 记录战术使用
                    try:
                        from tactics_db import record_tactic_usage
                        record_tactic_usage(new_tactic)
                    except:
                        pass
                    
            # 记录强制修改
            if _get_COMM():
                _get_COMM().say("战术频道", f"强制多样化：{len(tactic_counts)}种→{num_tactics}种战术")
    
    def note_hit(self, plan=None):
        with self.lock:
            self.stats["hits"] += 1
            # 优先用子弹自带方案(发射者当时的真实方案),缺失才退回全局 current_plan
            cp = plan or self.current_plan
            if cp and cp in self.plan_stats:
                self.plan_stats[cp]["hits"] += 1

    def request_review_async(self, wave, player_hp, player_max):
        """波次结束进化:保留有效教训,剔除无效战术,代际累积。
        冷却限速: 至少间隔 REVIEW_COOLDOWN 秒才允许一次进化——
        否则高频复盘导致教训还没验证就被覆盖,代数虚高而质量稀攇。"""
        if not self.enabled or self.review_pending:
            return
        # v37.0: 被斩杀后禁止进化(游戏侧 evo_disabled 标记,原版只喊话不生效)
        if getattr(self, "evo_disabled", False):
            return
        if time.time() - getattr(self, "_last_review", 0) < self.REVIEW_COOLDOWN:
            return  # 冷却中: 让当前教训至少跑满一个冷却周期再进化
        with self.lock:
            if self.stats["deaths"] == 0 and self.stats["hits"] == 0:
                return  # 没有交战,不进化
            st = dict(self.stats)
            plans = list(self.last_plans)
            lessons = list(self.lessons)
            gen = self.generation
            genealogy = {k: dict(v) for k, v in self.plan_stats.items()}
            self.stats = {"deaths": 0, "hits": 0, "orders": 0}
            self.last_plans = []
        self.review_pending = True

        def worker():
            try:
                old = "\n".join(f"{i+1}) {l}" for i, l in enumerate(lessons)) or "（无，初创代）"
                pl = " → ".join(plans) if plans else "（未发出指令）"
                gene = "\n".join(
                    f"- {name}: 发令{ps['issued']}次,玩家受击{ps['hits']},"
                    f"我方阵亡{ps['deaths']}"
                    for name, ps in genealogy.items()) or "（无）"
                # 方阵成阵统计注入复盘: 让总指挥知道方阵战术的实际战果
                ph = getattr(self, "phalanx_stats", None)
                ph_txt = ""
                if ph:
                    ph_txt = (f"\n方阵壁垒战果: 本波成阵{ph['formed']}次"
                              f"(共{ph['members']}台次免伤),"
                              f"方阵期间玩家受击{ph['hits_during']}次"
                              f"⚠方阵是好盾不是万能: 占指令超过一半会被玩家"
                              f"绕后逐个收割阵外单位,适度使用")
                    self.phalanx_stats = {"formed": 0, "members": 0, "hits_during": 0}
                prompt = (
                    f"你是敌方总指挥,正在进化你的战术体系(当前第{gen}代)。\n"
                    f"第{wave}波方案序列: {pl}\n"
                    f"本波: 我方阵亡{st['deaths']}台,玩家受击{st['hits']}次"
                    f"(玩家余HP{player_hp}/{player_max})\n"
                    f"方案谱系(跨波累积战果):\n{gene}\n"
                    + ("\n" + ph_txt if ph_txt else "")
                    # v36.0: 关键时刻时间线注入(事件因果链, LLM可直接消化)
                    + _timeline_text()
                    + f"\n现役教训(第{gen}代):\n{old}\n"
                    "进化规则: 被战果验证有效的教训保留(可精炼原文);"
                    "无效的改写或剔除;针对暴露的漏洞补充新教训。"
                    "最多5条。只输出JSON: {\"lessons\":[\"教训1\",...]}"
                )
                from llm_client import ask as _llm_ask  # v36.0: 统一出口
                text, _lat = _llm_ask(self.api_port, prompt=prompt, max_tokens=800,
                                      temperature=0.5, timeout=25)
                new_lessons = []
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if m:
                    try:
                        obj = json.loads(m.group(0))
                        for l in obj.get("lessons", []):
                            l = str(l).strip()[:40]
                            if l:
                                new_lessons.append(l)
                    except Exception:
                        pass
                # 评估战术效果，过滤无效战术
                try:
                    from tactics_db import TACTICS_DB
                    # 根据实际效果过滤教训
                    filtered_lessons = []
                    for l in new_lessons:
                        # 检查教训中提到的战术是否有效
                        tactic_valid = True
                        for tactic_name, data in TACTICS_DB.items():
                            if tactic_name in l and data["status"] == "disabled":
                                tactic_valid = False
                                break
                        if tactic_valid:
                            filtered_lessons.append(l)
                    new_lessons = filtered_lessons[:8]
                except:
                    new_lessons = new_lessons[:8]
                
                with self.lock:
                    if new_lessons:
                        kept = sum(1 for l in new_lessons if l in lessons)
                        self.lessons = new_lessons
                        self.generation += 1
                        self._last_review = time.time()  # 冷却起点
                        self.save_evolution()  # 进化立即存档,跨局继承
                        if _get_COMM():
                            _get_COMM().say(self.name,
                                     f"第{self.generation}代进化: "
                                     f"保留{kept}条+新增{len(new_lessons)-kept}条")
                            for l in new_lessons:
                                tag = "保留" if l in lessons else "新增"
                                _get_COMM().say(self.name, f"·[{tag}] {l}")
                    else:
                        if _get_COMM():
                            _get_COMM().say(self.name, "进化失败,维持现役教训")
            except Exception as exc:
                if _get_COMM():
                    _get_COMM().say(self.name, f"进化失败({type(exc).__name__})")
            finally:
                self.review_pending = False

        threading.Thread(target=worker, daemon=True).start()

    def get_order(self, eid):
        with self.lock:
            return self.orders.get(eid)

    def had_order(self, eid):
        """该敌坦是否曾被总指挥指挥过(兼容保留;AI全权模式下不再用于分支)。"""
        with self.lock:
            return eid in self.commanded

    def coord_brief(self):
        """帅间协同简报: 当前主力战术+兵力+代际,用于三帅通讯显示。"""
        with self.lock:
            if not self.plan_stats:
                return f"{self.name}: 待命(无战术记录)"
            top = max(self.plan_stats.items(),
                      key=lambda kv: kv[1]["issued"])
            return (f"{self.name}: 主力『{top[0]}』x{top[1]['issued']}"
                    f" 兵力{len(self.orders)} 第{self.generation}代")

    def status(self):
        with self.lock:
            base = f"{self.last_result} {self.last_latency:.1f}s" \
                if self.last_latency else self.last_result
            base = f"{self.name}·第{self.generation}代 | " + base
            if self.lessons:
                base += f" | 教训{len(self.lessons)}条"
            # 显示战略阶段和阵型信息
            base += f" | 阶段:{self.strategic_phase}"
            if hasattr(self, 'cluster_planner') and self.cluster_planner.current_plan:
                base += f" | 方案:{self.cluster_planner.current_plan}"
            # 附加自检状态:推理异常但服务器活着时,红/绿以自检为准
            if self.health_ok is True:
                base += " | 自检✓"
            elif self.health_ok is False:
                base += f" | 自检✗({self.health_msg})"
            return base
