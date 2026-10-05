# v36.0 (2026-10-05) — 36aigame
"""
高速数据库测试
版本: v20.0
"""

import sys
import os
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from highspeed_db import HighSpeedDB


def test_basic_operations():
    """测试基本读写操作"""
    db = HighSpeedDB('test_basic', '/tmp/test_basic.json', max_memory_size=100)
    
    # 写入
    db.set('key1', {'data': 1})
    db.set('key2', {'data': 2})
    
    # 读取
    assert db.get('key1') == {'data': 1}
    assert db.get('key2') == {'data': 2}
    assert db.get('nonexistent') is None
    assert db.get('nonexistent', 'default') == 'default'
    
    db.close()
    print("✅ 基本读写测试通过")


def test_performance():
    """测试性能"""
    db = HighSpeedDB('test_perf', '/tmp/test_perf.json', max_memory_size=10000)
    
    # 写入测试
    start = time.time()
    for i in range(1000):
        db.set(f'key_{i}', {'data': i, 'time': time.time()})
    write_time = time.time() - start
    
    # 读取测试
    start = time.time()
    for i in range(1000):
        db.get(f'key_{i}')
    read_time = time.time() - start
    
    write_ops = 1000 / write_time
    read_ops = 1000 / read_time
    
    print(f"写入性能: {write_ops:.0f} ops/s")
    print(f"读取性能: {read_ops:.0f} ops/s")
    
    assert write_ops > 100000, f"写入性能不足: {write_ops}"
    assert read_ops > 100000, f"读取性能不足: {read_ops}"
    
    db.close()
    print("✅ 性能测试通过")


def test_persistence():
    """测试持久化"""
    db1 = HighSpeedDB('test_persist', '/tmp/test_persist.json', max_memory_size=100)
    db1.set('persist_key', {'value': 'test'})
    db1.sync()
    db1.close()
    
    # 重新打开
    db2 = HighSpeedDB('test_persist', '/tmp/test_persist.json', max_memory_size=100)
    assert db2.get('persist_key') == {'value': 'test'}
    db2.close()
    
    print("✅ 持久化测试通过")


def test_stats():
    """测试统计信息"""
    db = HighSpeedDB('test_stats', '/tmp/test_stats.json', max_memory_size=100)
    
    db.set('a', 1)
    db.set('b', 2)
    db.get('a')
    db.get('a')
    db.get('nonexistent')
    
    stats = db.get_stats()
    assert stats['memory_items'] == 2
    assert stats['writes'] == 2
    assert stats['memory_hits'] >= 2
    
    db.close()
    print("✅ 统计测试通过")


if __name__ == '__main__':
    print("=== 高速数据库测试 ===")
    test_basic_operations()
    test_performance()
    test_persistence()
    test_stats()
    print("\n✅ 所有测试通过！")
