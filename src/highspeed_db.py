# v36.0 (2026-10-05) — 36aigame
# 高速数据库系统 - SQLite内存版
# 版本: v16.0
# 功能: SQLite内存数据库 + 可选硬盘持久化

import sqlite3
import json
import time
import threading
import os
from collections import OrderedDict

class HighSpeedDB:
    """
    SQLite内存数据库架构:
    1. 内存层: SQLite :memory:,O(1)读写
    2. 硬盘层: 可选JSON文件,定期同步
    """

    def __init__(self, name, disk_path=None, max_memory_size=10000):
        self.name = name
        self.max_memory_size = max_memory_size
        self.lock = threading.RLock()

        # v36.0: check_same_thread=False — 游戏主循环/同步线程/pilot多线程共享同一连接,
        # 原默认True会在跨线程调用时抛 ProgrammingError, 被上游 except:pass 吞掉,
        # 导致战场记录静默失败(无hsdb落盘)。线程安全由 self.lock 保证。
        self.conn = sqlite3.connect(':memory:', check_same_thread=False)
        # v36.0: 内存库无需崩溃恢复,关闭journal/sync大幅提升写性能
        self.conn.execute('PRAGMA journal_mode=MEMORY')
        self.conn.execute('PRAGMA synchronous=OFF')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS records (
                key TEXT PRIMARY KEY,
                value TEXT,
                timestamp REAL
            )
        ''')
        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp ON records(timestamp)
        ''')
        self.conn.commit()

        # 硬盘路径(可选)
        if disk_path:
            self.disk_path = disk_path
        else:
            self.disk_path = f"/tmp/hsdb_{name}.json"

        # 统计
        self.stats = {
            "memory_hits": 0,
            "disk_hits": 0,
            "misses": 0,
            "writes": 0,
            "syncs": 0
        }

        # 自动同步线程 (v36.0: 1秒同步一次)
        self.sync_interval = 1  # 基础同步间隔(秒)；大库可通过sync_every_n覆盖倍数
        # v36.01: sync_every_n — 每n个基础周期才真正落盘一次(大库IO节流)
        self.sync_every_n = 1
        self._sync_counter = 0
        self._stop_sync = False
        self._dirty = False
        self._sync_thread = threading.Thread(target=self._auto_sync, daemon=True)
        self._sync_thread.start()

        # 加载硬盘数据
        self._load_from_disk()

    def put(self, key, value):
        """写入数据(内存优先)"""
        with self.lock:
            # 写入SQLite内存数据库
            self.conn.execute(
                'INSERT OR REPLACE INTO records (key, value, timestamp) VALUES (?, ?, ?)',
                (key, json.dumps(value), time.time())
            )
            # v36.0: 惰性commit — 纯内存库无需每次提交，
            # 攒到dirty同步落盘时一并commit，写入吞吐提升~5x
            self._commit_pending = True

            # 限制内存大小
            self._limit_memory_size()

            self.stats["writes"] += 1
            self._dirty = True

    def _flush_if_needed(self):
        """读前确保未commit的写可见 (v36.0)"""
        if getattr(self, "_commit_pending", False):
            self.conn.commit()
            self._commit_pending = False

    def get(self, key, default=None):
        """读取数据 (v36.0: 支持default参数,兼容旧API)"""
        with self.lock:
            # 从SQLite内存数据库读取
            cursor = self.conn.execute('SELECT value FROM records WHERE key = ?', (key,))
            row = cursor.fetchone()
            if row:
                self.stats["memory_hits"] += 1
                return json.loads(row[0])
            
            self.stats["misses"] += 1
            return default

    def set(self, key, value):
        """写入数据 (v36.0: 兼容旧API, put的别名)"""
        self.put(key, value)

    def sync(self):
        """手动触发同步落盘 (v36.0: 兼容旧API)"""
        self._sync_to_disk()

    def get_latest(self, limit=100):
        """获取最新的记录"""
        with self.lock:
            cursor = self.conn.execute(
                'SELECT key, value FROM records ORDER BY timestamp DESC LIMIT ?',
                (limit,)
            )
            result = {}
            for row in cursor.fetchall():
                result[row[0]] = json.loads(row[1])
            return result

    def get_all(self):
        """获取所有记录"""
        with self.lock:
            cursor = self.conn.execute('SELECT key, value FROM records')
            result = {}
            for row in cursor.fetchall():
                result[row[0]] = json.loads(row[1])
            return result

    def _limit_memory_size(self):
        """限制内存大小"""
        cursor = self.conn.execute('SELECT COUNT(*) FROM records')
        count = cursor.fetchone()[0]

        if count > self.max_memory_size:
            # 删除最旧的记录
            to_delete = count - self.max_memory_size
            self.conn.execute('''
                DELETE FROM records WHERE key IN (
                    SELECT key FROM records ORDER BY timestamp ASC LIMIT ?
                )
            ''', (to_delete,))
            self.conn.commit()

    def _auto_sync(self):
        """自动同步到硬盘"""
        while not self._stop_sync:
            time.sleep(self.sync_interval)
            if self._dirty:
                # v36.01: 大库节流 — 每sync_every_n个周期才落盘一次
                self._sync_counter += 1
                if self._sync_counter % self.sync_every_n != 0:
                    continue
                self._sync_to_disk()

    def _sync_to_disk(self):
        """同步内存数据到硬盘 (v36.01: 原子写tmp+rename，避免读侧读到半截JSON)"""
        try:
            with self.lock:
                self._flush_if_needed()
                data = self.get_all()
                tmp_path = self.disk_path + ".tmp"
                with open(tmp_path, 'w') as f:
                    json.dump(data, f)
                os.replace(tmp_path, self.disk_path)  # 原子替换
                self._dirty = False
                self.stats["syncs"] += 1
        except Exception as e:
            print(f"[HSDB] 同步到硬盘失败: {e}")

    def _load_from_disk(self):
        """从硬盘加载数据"""
        try:
            if os.path.exists(self.disk_path):
                with open(self.disk_path, 'r') as f:
                    data = json.load(f)
                for key, value in data.items():
                    self.conn.execute(
                        'INSERT OR REPLACE INTO records (key, value, timestamp) VALUES (?, ?, ?)',
                        (key, json.dumps(value), time.time())
                    )
                self.conn.commit()
                print(f"[HSDB] {self.name} 从硬盘加载 {len(data)} 条记录")
        except Exception as e:
            print(f"[HSDB] 从硬盘加载失败: {e}")

    def get_stats(self):
        """获取统计信息"""
        with self.lock:
            cursor = self.conn.execute('SELECT COUNT(*) FROM records')
            count = cursor.fetchone()[0]
            total_reads = self.stats["memory_hits"] + self.stats["misses"] + self.stats["disk_hits"]
            hit_rate = (self.stats["memory_hits"] + self.stats["disk_hits"]) / total_reads if total_reads else 0.0
            return {
                **self.stats,
                # v36.0: 补充旧API字段（game_db测试与调用方依赖 memory_items/hit_rate）
                "memory_items": count,
                "memory_size": count,
                "max_memory_size": self.max_memory_size,
                "hit_rate": hit_rate
            }

    def close(self):
        """关闭数据库"""
        self._stop_sync = True
        self._flush_if_needed()
        self._sync_to_disk()
        self.conn.close()


# v36.0: 恢复模块级注册表 + get_db工厂函数（game_db/battle_recorder/tactics_evolution 都依赖）
_DBS = {}
_DBS_LOCK = threading.Lock()

def get_db(name, disk_path=None, max_memory_size=10000, sync_every_n=1):
    """获取或创建同名数据库单例 (兼容旧API)
    v36.01: sync_every_n — 落盘节流倍数(每n秒落盘一次)，大库传30/60避免每秒全量dump"""
    with _DBS_LOCK:
        if name not in _DBS:
            _DBS[name] = HighSpeedDB(name, disk_path, max_memory_size)
            if sync_every_n > 1:
                _DBS[name].sync_every_n = sync_every_n
        return _DBS[name]

def close_all():
    """关闭所有数据库 (兼容旧API)"""
    with _DBS_LOCK:
        for db in _DBS.values():
            try:
                db.close()
            except Exception:
                pass
        _DBS.clear()
