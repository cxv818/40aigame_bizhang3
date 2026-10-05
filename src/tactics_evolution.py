# v36.0 (2026-10-05) — 36aigame
# 战术进化系统
# 版本: v12.0
# 功能: 实时战术效果评估 + 多样性奖励

import json
import time
import math
from collections import defaultdict
from game_db import get_db

# 战术数据库
tactics_db = get_db("tactics_evolution", "/tmp/hsdb_tactics_evolution.json", max_memory_size=1000)

class TacticsEvolution:
    """
    战术进化系统:
    1. 实时记录每种战术的效果
    2. 计算多样性奖励
    3. 推荐最优战术组合
    """
    
    def __init__(self):
        self.tactic_stats = defaultdict(lambda: {
            "used": 0,
            "hits": 0,
            "deaths": 0,
            "damage_dealt": 0,
            "damage_taken": 0,
            "last_used": 0,
            "effectiveness": 0.0,
            "diversity_score": 0.0
        })
        self.frame_count = 0
        self.last_diversity_check = 0
        
    def record_tactic_usage(self, tactic_name, enemy_id, context):
        """记录战术使用"""
        self.tactic_stats[tactic_name]["used"] += 1
        self.tactic_stats[tactic_name]["last_used"] = self.frame_count
        
        # 计算多样性奖励
        self._update_diversity_score(tactic_name)
        
    def record_tactic_effect(self, tactic_name, hit=False, death=False, 
                            damage_dealt=0, damage_taken=0):
        """记录战术效果"""
        if tactic_name not in self.tactic_stats:
            return
            
        stats = self.tactic_stats[tactic_name]
        if hit:
            stats["hits"] += 1
        if death:
            stats["deaths"] += 1
        stats["damage_dealt"] += damage_dealt
        stats["damage_taken"] += damage_taken
        
        # 计算综合效果
        self._calculate_effectiveness(tactic_name)
        
    def _update_diversity_score(self, tactic_name):
        """更新多样性评分"""
        # 计算当前帧使用的战术种类
        recent_tactics = set()
        for name, stats in self.tactic_stats.items():
            if stats["last_used"] >= self.frame_count - 10:  # 最近10帧
                recent_tactics.add(name)
        
        # 多样性奖励：使用的战术种类越多，奖励越高
        diversity_bonus = len(recent_tactics) * 0.1
        
        # 惩罚过度使用同一战术
        for name, stats in self.tactic_stats.items():
            if stats["used"] > 0:
                usage_ratio = stats["used"] / sum(s["used"] for s in self.tactic_stats.values())
                if usage_ratio > 0.5:  # 如果某个战术使用超过50%
                    diversity_bonus -= (usage_ratio - 0.5) * 0.5  # 惩罚
                
        self.tactic_stats[tactic_name]["diversity_score"] = diversity_bonus
        
    def _calculate_effectiveness(self, tactic_name):
        """计算战术综合效果"""
        stats = self.tactic_stats[tactic_name]
        if stats["used"] == 0:
            return
            
        # 基础效果 = 命中率 - 死亡率
        hit_rate = stats["hits"] / stats["used"]
        death_rate = stats["deaths"] / stats["used"]
        base_effectiveness = hit_rate - death_rate
        
        # 伤害效率 = 造成伤害 / 受到伤害
        damage_efficiency = 0
        if stats["damage_taken"] > 0:
            damage_efficiency = stats["damage_dealt"] / stats["damage_taken"]
        
        # 综合效果 = 基础效果 * 0.6 + 伤害效率 * 0.2 + 多样性奖励 * 0.2
        diversity_bonus = stats["diversity_score"]
        stats["effectiveness"] = (base_effectiveness * 0.6 + 
                                  min(damage_efficiency, 1.0) * 0.2 + 
                                  diversity_bonus * 0.2)
        
    def get_tactic_recommendation(self, current_tactics=None):
        """获取战术推荐"""
        if current_tactics is None:
            current_tactics = []
            
        recommendations = []
        
        for tactic_name, stats in self.tactic_stats.items():
            if stats["used"] < 5:  # 使用次数太少，不确定效果
                # 新战术探索奖励
                recommendations.append({
                    "tactic": tactic_name,
                    "score": 0.5,  # 中等分数，鼓励探索
                    "reason": "新战术，需要探索"
                })
            else:
                score = stats["effectiveness"]
                # 如果当前已经在用，降低推荐度（避免重复）
                if tactic_name in current_tactics:
                    score *= 0.8
                    
                recommendations.append({
                    "tactic": tactic_name,
                    "score": score,
                    "reason": f"效果{score:.2f},使用{stats['used']}次"
                })
        
        # 按分数排序
        recommendations.sort(key=lambda x: -x["score"])
        return recommendations[:5]  # 返回前5个推荐
        
    def get_diversity_penalty(self, tactic_name):
        """获取过度使用惩罚"""
        total_usage = sum(s["used"] for s in self.tactic_stats.values())
        if total_usage == 0:
            return 0
            
        usage_ratio = self.tactic_stats[tactic_name]["used"] / total_usage
        if usage_ratio > 0.5:
            return (usage_ratio - 0.5) * 0.3  # 最高0.15的惩罚
        return 0
        
    def save_state(self):
        """保存状态到数据库"""
        state = {
            "tactic_stats": dict(self.tactic_stats),
            "frame_count": self.frame_count,
            "timestamp": time.time()
        }
        tactics_db.set("evolution_state", state)
        
    def load_state(self):
        """从数据库加载状态"""
        state = tactics_db.get("evolution_state")
        if state:
            self.tactic_stats = defaultdict(lambda: {
                "used": 0, "hits": 0, "deaths": 0,
                "damage_dealt": 0, "damage_taken": 0,
                "last_used": 0, "effectiveness": 0.0,
                "diversity_score": 0.0
            })
            self.tactic_stats.update(state.get("tactic_stats", {}))
            self.frame_count = state.get("frame_count", 0)

    def reset(self):
        """重置全部统计 (v36.0: 测试依赖,原缺失)"""
        self.tactic_stats = defaultdict(lambda: {
            "used": 0, "hits": 0, "deaths": 0,
            "damage_dealt": 0, "damage_taken": 0,
            "last_used": 0, "effectiveness": 0.0,
            "diversity_score": 0.0
        })
        self.frame_count = 0


# 全局实例
_evolution = None

def get_evolution():
    """获取战术进化实例"""
    global _evolution
    if _evolution is None:
        _evolution = TacticsEvolution()
        _evolution.load_state()
    return _evolution


# 便捷函数
def record_tactic(tactic_name, enemy_id=None, context=None):
    """记录战术使用"""
    evo = get_evolution()
    evo.record_tactic_usage(tactic_name, enemy_id, context)
    evo.frame_count += 1

def record_effect(tactic_name, hit=False, death=False, 
                 damage_dealt=0, damage_taken=0):
    """记录战术效果"""
    evo = get_evolution()
    evo.record_tactic_effect(tactic_name, hit, death, damage_dealt, damage_taken)

def get_recommendations(current_tactics=None):
    """获取战术推荐"""
    evo = get_evolution()
    return evo.get_tactic_recommendation(current_tactics)

def get_diversity_info():
    """获取多样性信息"""
    evo = get_evolution()
    total = sum(s["used"] for s in evo.tactic_stats.values())
    if total == 0:
        # v36.0: 补齐字段——原返回缺 dominant_ratio,调用方无条件下访问致KeyError(留痕抓到)
        return {"diversity": 0, "dominant_tactic": None, "dominant_ratio": 0.0, "tactic_count": 0}
        
    # 计算多样性指数（Shannon指数）
    diversity = 0
    dominant = None
    max_ratio = 0
    
    for name, stats in evo.tactic_stats.items():
        if stats["used"] > 0:
            ratio = stats["used"] / total
            if ratio > max_ratio:
                max_ratio = ratio
                dominant = name
            diversity -= ratio * math.log(ratio)
            
    return {
        "diversity": diversity,
        "dominant_tactic": dominant,
        "dominant_ratio": max_ratio,
        "tactic_count": len([s for s in evo.tactic_stats.values() if s["used"] > 0])
    }


# 测试
if __name__ == "__main__":
    evo = get_evolution()
    
    # 模拟数据
    tactics = ["直攻", "集火", "方阵", "包抄", "佯退"]
    
    for i in range(100):
        tactic = tactics[i % len(tactics)]
        record_tactic(tactic, i)
        
        # 模拟效果
        hit = (i % 3 == 0)
        death = (i % 10 == 0)
        record_effect(tactic, hit=hit, death=death, 
                     damage_dealt=10 if hit else 0, damage_taken=5 if death else 0)
    
    # 获取推荐
    print("=== 战术推荐 ===")
    recs = get_recommendations()
    for rec in recs:
        print(f"{rec['tactic']}: {rec['score']:.2f} ({rec['reason']})")
    
    # 获取多样性信息
    print("\n=== 多样性分析 ===")
    div = get_diversity_info()
    print(f"多样性指数: {div['diversity']:.2f}")
    print(f"主导战术: {div['dominant_tactic']} ({div['dominant_ratio']:.1%})")
    print(f"战术种类: {div['tactic_count']}")
