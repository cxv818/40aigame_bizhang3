# v36.0 (2026-10-05) — 36aigame
# 战术多样性强制执行器
# 版本: v12.0
# 功能: 在游戏逻辑层面强制战术多样化

import random
from collections import defaultdict

class TacticsDiversityEnforcer:
    """
    战术多样性强制执行器:
    - 监控战术使用比例
    - 强制分配不同战术
    - 惩罚过度使用同一战术
    """
    
    def __init__(self, max_ratio=0.4, min_tactics=3):
        self.max_ratio = max_ratio  # 最大占比40%
        self.min_tactics = min_tactics  # 最少3种战术
        self.tactic_usage = defaultdict(int)
        self.total_usage = 0
        self.forced_tactics = ["直攻", "集火", "方阵", "游击", "包抄"]
        
    def assign_tactics(self, enemy_count, current_orders=None):
        """
        强制分配战术，确保多样性
        
        Args:
            enemy_count: 敌人数量
            current_orders: 当前指令（如果有）
            
        Returns:
            dict: {enemy_id: tactic_name}
        """
        assignments = {}
        
        # 计算当前比例
        if self.total_usage > 0:
            current_ratios = {
                tactic: count / self.total_usage 
                for tactic, count in self.tactic_usage.items()
            }
        else:
            current_ratios = {}
        
        # 找出过度使用的战术
        overused = [
            tactic for tactic, ratio in current_ratios.items() 
            if ratio > self.max_ratio
        ]
        
        # 强制分配
        for i in range(enemy_count):
            # 如果当前指令存在且不过度使用，保留
            # v36.0: 修复 — 原逻辑只检查 overused 名单，名单外的单一战术
            # （如"山地占领"，不在 forced_tactics 里）会原样放行，多样化形同虚设。
            # 现在只有「不在overused 且 已在受控战术池」的指令才可保留。
            if current_orders and i in current_orders:
                current_tactic = current_orders[i].get("plan", "")
                in_pool = current_tactic in self.forced_tactics
                ratio = current_ratios.get(current_tactic, 0)
                # 全场单一战术(该战术占比==1.0)时也不得保留，必须打散
                is_monoculture = self.total_usage > 0 and ratio >= 1.0
                if (current_tactic and in_pool
                        and current_tactic not in overused
                        and not is_monoculture):
                    assignments[i] = current_tactic
                    continue
            
            # 选择使用比例最低的战术
            available_tactics = [
                t for t in self.forced_tactics 
                if t not in overused or self.tactic_usage[t] == 0
            ]
            
            if not available_tactics:
                available_tactics = self.forced_tactics
            
            # 优先选择使用少的战术
            tactic_counts = [
                (t, self.tactic_usage.get(t, 0)) 
                for t in available_tactics
            ]
            tactic_counts.sort(key=lambda x: x[1])
            
            # 前3个最少使用的战术中随机选择
            candidates = [t[0] for t in tactic_counts[:3]]
            chosen = random.choice(candidates)
            
            assignments[i] = chosen
            self.tactic_usage[chosen] += 1
            self.total_usage += 1
        
        return assignments
    
    def get_diversity_report(self):
        """获取多样性报告"""
        if self.total_usage == 0:
            return {"diversity": 0, "status": "无数据"}
        
        ratios = {
            tactic: count / self.total_usage 
            for tactic, count in self.tactic_usage.items()
        }
        
        max_ratio = max(ratios.values()) if ratios else 0
        max_tactic = max(ratios, key=ratios.get) if ratios else "无"
        
        return {
            "total_usage": self.total_usage,
            "tactic_count": len([t for t in self.tactic_usage.values() if t > 0]),
            "max_ratio": max_ratio,
            "max_tactic": max_tactic,
            "status": "良好" if max_ratio <= self.max_ratio else "需改进",
            "ratios": ratios
        }
    
    def reset(self):
        """重置统计"""
        self.tactic_usage.clear()
        self.total_usage = 0


# 全局实例
_enforcer = None

def get_enforcer():
    """获取强制执行器实例"""
    global _enforcer
    if _enforcer is None:
        _enforcer = TacticsDiversityEnforcer()
    return _enforcer


# 便捷函数
def assign_diverse_tactics(enemy_count, current_orders=None):
    """分配多样化战术"""
    enforcer = get_enforcer()
    return enforcer.assign_tactics(enemy_count, current_orders)

def get_diversity_report():
    """获取多样性报告"""
    enforcer = get_enforcer()
    return enforcer.get_diversity_report()

def reset_diversity():
    """重置多样性统计"""
    enforcer = get_enforcer()
    enforcer.reset()


# 测试
if __name__ == "__main__":
    enforcer = get_enforcer()
    
    # 模拟分配
    for round in range(5):
        print(f"\n=== 第{round+1}轮分配 ===")
        assignments = enforcer.assign_tactics(10)
        
        # 统计
        stats = {}
        for tactic in assignments.values():
            stats[tactic] = stats.get(tactic, 0) + 1
        
        print("分配结果:")
        for tactic, count in sorted(stats.items(), key=lambda x: -x[1]):
            print(f"  {tactic}: {count}个")
        
        # 报告
        report = enforcer.get_diversity_report()
        print(f"多样性: {report['status']}, 最大占比: {report['max_ratio']:.1%}")
