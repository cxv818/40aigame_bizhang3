# v36.0 (2026-10-05) — 36aigame
"""
战术进化系统测试
版本: v20.0
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tactics_evolution import (
    get_evolution,
    record_tactic,
    record_effect,
    get_recommendations,
    get_diversity_info
)


def test_record_tactic():
    """测试记录战术使用"""
    evo = get_evolution()
    evo.reset()
    
    record_tactic("直攻", enemy_id=1)
    record_tactic("集火", enemy_id=2)
    record_tactic("直攻", enemy_id=3)
    
    assert evo.tactic_stats["直攻"]["used"] == 2
    assert evo.tactic_stats["集火"]["used"] == 1
    
    print("✅ 记录战术测试通过")


def test_record_effect():
    """测试记录战术效果"""
    evo = get_evolution()
    evo.reset()
    
    # 记录使用
    record_tactic("直攻", enemy_id=1)
    record_tactic("直攻", enemy_id=2)
    record_tactic("直攻", enemy_id=3)
    
    # 记录效果
    record_effect("直攻", hit=True, death=False)
    record_effect("直攻", hit=True, death=False)
    record_effect("直攻", hit=False, death=True)
    
    stats = evo.tactic_stats["直攻"]
    assert stats["hits"] == 2
    assert stats["deaths"] == 1
    assert stats["effectiveness"] != 0
    
    print("✅ 记录效果测试通过")


def test_recommendations():
    """测试战术推荐"""
    evo = get_evolution()
    evo.reset()
    
    # 模拟数据
    for i in range(10):
        record_tactic("直攻", enemy_id=i)
        record_effect("直攻", hit=(i % 2 == 0))
    
    for i in range(5):
        record_tactic("集火", enemy_id=i+10)
        record_effect("集火", hit=True)
    
    recs = get_recommendations()
    assert len(recs) > 0
    assert recs[0]["tactic"] in ["直攻", "集火"]
    
    print("✅ 推荐测试通过")


def test_diversity():
    """测试多样性计算"""
    evo = get_evolution()
    evo.reset()
    
    # 单一战术
    for i in range(10):
        record_tactic("直攻", enemy_id=i)
    
    div1 = get_diversity_info()
    assert div1["tactic_count"] == 1
    assert div1["dominant_tactic"] == "直攻"
    
    # 多种战术
    evo.reset()
    tactics = ["直攻", "集火", "方阵", "游击"]
    for i in range(20):
        record_tactic(tactics[i % 4], enemy_id=i)
    
    div2 = get_diversity_info()
    assert div2["tactic_count"] == 4
    assert div2["dominant_ratio"] < 0.5
    
    print("✅ 多样性测试通过")


if __name__ == '__main__':
    print("=== 战术进化系统测试 ===")
    test_record_tactic()
    test_record_effect()
    test_recommendations()
    test_diversity()
    print("\n✅ 所有测试通过！")
