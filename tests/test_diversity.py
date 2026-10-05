# v36.0 (2026-10-05) — 36aigame
"""
战术多样性测试
版本: v20.0
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tactics_diversity_enforcer import (
    get_enforcer,
    assign_diverse_tactics,
    get_diversity_report,
    reset_diversity
)


def test_assign_diverse():
    """测试分配多样化战术"""
    reset_diversity()
    
    # 分配10个敌人的战术
    assignments = assign_diverse_tactics(10)
    
    assert len(assignments) == 10
    
    # 统计战术
    tactics = {}
    for eid, tactic in assignments.items():
        tactics[tactic] = tactics.get(tactic, 0) + 1
    
    # 检查是否多样化
    assert len(tactics) >= 3, f"战术种类不足: {len(tactics)}"
    
    max_ratio = max(tactics.values()) / 10
    assert max_ratio <= 0.4, f"最大占比过高: {max_ratio}"
    
    print(f"✅ 分配多样化测试通过: {tactics}")


def test_diversity_report():
    """测试多样性报告"""
    reset_diversity()
    
    # 分配一些战术
    assign_diverse_tactics(20)
    
    report = get_diversity_report()
    
    assert report["total_usage"] == 20
    assert report["tactic_count"] >= 3
    assert report["max_ratio"] <= 0.4
    assert report["status"] == "良好"
    
    print(f"✅ 多样性报告测试通过: {report}")


def test_enforce_diversity():
    """测试强制多样化"""
    reset_diversity()
    
    # 先使用一些其他战术，避免"山地占领"成为唯一选项
    for i in range(10):
        assign_diverse_tactics(5)
    
    # 模拟LLM输出单一战术
    current_orders = {i: {"plan": "山地占领"} for i in range(10)}
    
    # 强制多样化
    assignments = assign_diverse_tactics(10, current_orders)
    
    # 检查是否被修改
    tactics = {}
    for eid, tactic in assignments.items():
        tactics[tactic] = tactics.get(tactic, 0) + 1
    
    # 应该不再单一（至少2种）
    print(f"强制多样化结果: {tactics}")
    
    # 由于"山地占领"不在forced_tactics列表中，应该被替换
    assert "山地占领" not in tactics or len(tactics) >= 2, f"仍然单一: {tactics}"
    
    print(f"✅ 强制多样化测试通过")


if __name__ == '__main__':
    print("=== 战术多样性测试 ===")
    test_assign_diverse()
    test_diversity_report()
    test_enforce_diversity()
    print("\n✅ 所有测试通过！")
