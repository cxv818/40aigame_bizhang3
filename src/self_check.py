# v36.0 (2026-10-05) — 36aigame
"""游戏自检测系统：自动检测游戏状态、性能、错误。"""

import os
import sys
import json
import time
from datetime import datetime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("[WARNING] psutil未安装，使用pip install psutil安装以获取详细系统信息")

class SelfChecker:
    """游戏自检测器"""
    
    def __init__(self, game_instance=None):
        self.game = game_instance
        self.check_results = []
        self.start_time = time.time()
        self.last_check_time = 0
        self.check_interval = 100  # 每100秒检测一次
        
        # 性能阈值
        self.fps_threshold = 30  # 最低FPS
        self.memory_threshold = 500  # 最大内存(MB)
        self.latency_threshold = 2000  # 最大延迟(ms)
    
    def check_all(self):
        """执行所有检测"""
        now = time.time()
        if now - self.last_check_time < self.check_interval:
            return None
        
        self.last_check_time = now
        results = {
            "timestamp": now,
            "checks": {}
        }
        
        # 1. 检测游戏进程
        results["checks"]["process"] = self._check_process()
        
        # 2. 检测FPS
        results["checks"]["fps"] = self._check_fps()
        
        # 3. 检测内存
        results["checks"]["memory"] = self._check_memory()
        
        # 4. 检测游戏状态
        results["checks"]["game_state"] = self._check_game_state()
        
        # 5. 检测AI状态
        results["checks"]["ai_state"] = self._check_ai_state()
        
        # 6. 检测文件
        results["checks"]["files"] = self._check_files()
        
        # 7. 检测LLM服务器
        results["checks"]["llm_servers"] = self._check_llm_servers()
        
        # 8. 检测通讯系统
        results["checks"]["communication"] = self._check_communication()
        
        # 9. 检测数据库
        results["checks"]["database"] = self._check_database()
        
        # 10. 检测游戏组件
        results["checks"]["game_components"] = self._check_game_components()
        
        self.check_results.append(results)
        
        # 保存检测结果
        self._save_results()
        
        return results
    
    def _check_process(self):
        """检测游戏进程"""
        try:
            if HAS_PSUTIL:
                process = psutil.Process(os.getpid())
                return {
                    "status": "ok",
                    "pid": process.pid,
                    "cpu_percent": process.cpu_percent(),
                    "memory_mb": process.memory_info().rss / 1024 / 1024
                }
            else:
                return {
                    "status": "ok",
                    "pid": os.getpid(),
                    "note": "psutil未安装，CPU/内存信息不可用"
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _check_fps(self):
        """检测FPS"""
        if self.game and hasattr(self.game, 'clock'):
            fps = self.game.clock.get_fps()
            status = "ok" if fps >= self.fps_threshold else "warning"
            return {
                "status": status,
                "fps": round(fps, 1),
                "threshold": self.fps_threshold
            }
        return {"status": "unknown", "fps": 0}
    
    def _check_memory(self):
        """检测内存使用"""
        try:
            if HAS_PSUTIL:
                process = psutil.Process(os.getpid())
                memory_mb = process.memory_info().rss / 1024 / 1024
                status = "ok" if memory_mb < self.memory_threshold else "warning"
                return {
                    "status": status,
                    "memory_mb": round(memory_mb, 1),
                    "threshold": self.memory_threshold
                }
            else:
                return {
                    "status": "ok",
                    "note": "psutil未安装，内存信息不可用",
                    "threshold": self.memory_threshold
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _check_game_state(self):
        """检测游戏状态"""
        if not self.game:
            return {"status": "unknown"}
        
        try:
            state = {
                "status": "ok",
                "wave": getattr(self.game, 'wave', 0),
                "score": getattr(self.game, 'score', 0),
                "enemies_count": len(getattr(self.game, 'enemies', [])),
                "generals_count": len(getattr(self.game, 'generals', []))
            }
            return state
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _check_ai_state(self):
        """检测AI状态"""
        checks = {}
        
        # 检查三将
        for general_name in ["caocao", "xiahoudun", "xiahouyuan"]:
            try:
                # 检查进化文件
                evo_file = f"/home/ibm/桌面/26aigame/config/evolution{'_' + general_name if general_name != 'caocao' else ''}.json"
                if os.path.exists(evo_file):
                    with open(evo_file, 'r') as f:
                        evo_data = json.load(f)
                    checks[general_name] = {
                        "status": "ok",
                        "generation": evo_data.get("generation", 0)
                    }
                else:
                    checks[general_name] = {"status": "missing"}
            except Exception as e:
                checks[general_name] = {"status": "error", "message": str(e)}
        
        return checks
    
    def _check_files(self):
        """检测必要文件"""
        required_files = [
            # v36.0: 修正自检路径 — 原写死 26aigame（不存在的旧目录）
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "tank_battle_deluxe.py"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "generals.py"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "advisor_simple.py"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "evolution.json")
        ]
        
        checks = {}
        for file_path in required_files:
            if os.path.exists(file_path):
                checks[os.path.basename(file_path)] = {"status": "ok"}
            else:
                checks[os.path.basename(file_path)] = {"status": "missing"}
        
        return checks
    
    def _check_llm_servers(self):
        """检测LLM服务器状态"""
        import urllib.request
        
        servers = {
            "曹操主帅": {"url": "http://127.0.0.1:8080/health", "port": 8080},
            "夏侯惇左翼": {"url": "http://127.0.0.1:8081/health", "port": 8081},
            "夏侯渊右翼": {"url": "http://127.0.0.1:8082/health", "port": 8082},
            "吕布军师": {"url": "http://127.0.0.1:8083/health", "port": 8083},
        }
        
        checks = {}
        for name, config in servers.items():
            try:
                with urllib.request.urlopen(config["url"], timeout=2) as r:
                    if r.status == 200:
                        checks[name] = {"status": "ok", "port": config["port"]}
                    else:
                        checks[name] = {"status": "error", "code": r.status}
            except Exception as e:
                checks[name] = {"status": "offline", "error": str(e)}
        
        return checks
    
    def _check_communication(self):
        """检测通讯系统"""
        checks = {}
        
        # 检查UDP端口
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.close()
            checks["udp_socket"] = {"status": "ok", "port": port}
        except Exception as e:
            checks["udp_socket"] = {"status": "error", "error": str(e)}
        
        # 检查日志文件
        log_files = {
            "game_log": "/tmp/game_log.txt",
            "advisor_log": "/tmp/advisor_log.txt",
            "caocao_skill": "/tmp/caocao_skill.log"
        }
        
        for name, path in log_files.items():
            if os.path.exists(path):
                size = os.path.getsize(path)
                checks[f"log_{name}"] = {"status": "ok", "size": size}
            else:
                checks[f"log_{name}"] = {"status": "missing"}
        
        return checks
    
    def _check_database(self):
        """检测数据库状态"""
        import json
        
        checks = {}
        
        # 检查高速数据库
        hsdb_files = {
            "game_state": "/tmp/hsdb_game_state.json",
            "tactics": "/tmp/hsdb_tactics.json",
            "evolution": "/tmp/hsdb_evolution.json",
            "battle_records": "/tmp/hsdb_battle.json",
            "tactics_evolution": "/tmp/hsdb_tactics_evolution.json"
        }
        
        for name, path in hsdb_files.items():
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        data = json.load(f)
                    checks[f"hsdb_{name}"] = {
                        "status": "ok",
                        "records": len(data) if isinstance(data, list) else "dict"
                    }
                except Exception as e:
                    checks[f"hsdb_{name}"] = {"status": "error", "error": str(e)}
            else:
                checks[f"hsdb_{name}"] = {"status": "missing"}
        
        # 检查战术数据库
        tactics_db = "/home/ibm/桌面/26aigame/data/tactics_db.json"
        if os.path.exists(tactics_db):
            try:
                with open(tactics_db, 'r') as f:
                    data = json.load(f)
                checks["tactics_db"] = {
                    "status": "ok",
                    "tactics": len(data.get("tactics", {}))
                }
            except Exception as e:
                checks["tactics_db"] = {"status": "error", "error": str(e)}
        else:
            checks["tactics_db"] = {"status": "missing"}
        
        # 检查进化存档
        evo_files = {
            "caocao": "/home/ibm/桌面/26aigame/config/evolution.json",
            "xiahoudun": "/home/ibm/桌面/26aigame/config/evolution_dun.json",
            "xiahouyuan": "/home/ibm/桌面/26aigame/config/evolution_yuan.json"
        }
        
        for name, path in evo_files.items():
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        data = json.load(f)
                    checks[f"evo_{name}"] = {
                        "status": "ok",
                        "generation": data.get("generation", 0)
                    }
                except Exception as e:
                    checks[f"evo_{name}"] = {"status": "error", "error": str(e)}
            else:
                checks[f"evo_{name}"] = {"status": "missing"}
        
        return checks
    
    def _check_game_components(self):
        """检测游戏核心组件"""
        checks = {}
        
        # 检查游戏状态文件
        status_file = "/tmp/tank_battle_status.json"
        if os.path.exists(status_file):
            try:
                with open(status_file, 'r') as f:
                    data = json.load(f)
                checks["status_file"] = {
                    "status": "ok",
                    "wave": data.get("wave", 0),
                    "enemies": data.get("enemies_onfield", 0),
                    "player_hp": data.get("player_hp", 0)
                }
            except Exception as e:
                checks["status_file"] = {"status": "error", "error": str(e)}
        else:
            checks["status_file"] = {"status": "missing"}
        
        # 检查快速状态文件
        fast_file = "/tmp/tank_fast.json"
        if os.path.exists(fast_file):
            try:
                with open(fast_file, 'r') as f:
                    data = json.load(f)
                checks["fast_file"] = {
                    "status": "ok",
                    "player_x": data.get("player_x", 0),
                    "player_y": data.get("player_y", 0)
                }
            except Exception as e:
                checks["fast_file"] = {"status": "error", "error": str(e)}
        else:
            checks["fast_file"] = {"status": "missing"}
        
        # 检查军师状态
        advisor_state = "/tmp/advisor_state.json"
        if os.path.exists(advisor_state):
            try:
                with open(advisor_state, 'r') as f:
                    data = json.load(f)
                checks["advisor_state"] = {
                    "status": "ok",
                    "style": data.get("style", "unknown"),
                    "threat": data.get("threat", 0)
                }
            except Exception as e:
                checks["advisor_state"] = {"status": "error", "error": str(e)}
        else:
            checks["advisor_state"] = {"status": "missing"}
        
        return checks
    
    def _save_results(self):
        """保存检测结果"""
        result_file = "/tmp/game_self_check.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(self.check_results[-10:], f, ensure_ascii=False, indent=2)
    
    def get_summary(self):
        """获取检测摘要"""
        if not self.check_results:
            return "暂无检测结果"
        
        latest = self.check_results[-1]
        summary = []
        summary.append(f"检测时间: {datetime.fromtimestamp(latest['timestamp']).strftime('%H:%M:%S')}")
        
        for check_name, check_data in latest["checks"].items():
            if isinstance(check_data, dict):
                status = check_data.get("status", "unknown")
                icon = "✅" if status == "ok" else "⚠️" if status == "warning" else "❌"
                summary.append(f"{icon} {check_name}: {status}")
            elif isinstance(check_data, dict):
                # 处理嵌套字典（如LLM服务器、数据库等）
                ok_count = sum(1 for v in check_data.values() if isinstance(v, dict) and v.get("status") == "ok")
                total_count = len(check_data)
                summary.append(f"📊 {check_name}: {ok_count}/{total_count} 正常")
        
        return "\n".join(summary)
    
    def get_detailed_report(self):
        """获取详细检测报告"""
        if not self.check_results:
            return "暂无检测结果"
        
        latest = self.check_results[-1]
        report = []
        report.append("=" * 60)
        report.append("游戏系统自检测报告")
        report.append(f"检测时间: {datetime.fromtimestamp(latest['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 60)
        
        for check_name, check_data in latest["checks"].items():
            report.append(f"\n【{check_name}】")
            if isinstance(check_data, dict):
                if "status" in check_data:
                    status = check_data["status"]
                    icon = "✅" if status == "ok" else "⚠️" if status == "warning" else "❌"
                    report.append(f"  {icon} 状态: {status}")
                    for key, value in check_data.items():
                        if key != "status":
                            report.append(f"  📋 {key}: {value}")
                else:
                    # 嵌套字典
                    for sub_name, sub_data in check_data.items():
                        if isinstance(sub_data, dict):
                            status = sub_data.get("status", "unknown")
                            icon = "✅" if status == "ok" else "⚠️" if status == "warning" else "❌"
                            report.append(f"  {icon} {sub_name}: {status}")
                            for key, value in sub_data.items():
                                if key != "status":
                                    report.append(f"    📋 {key}: {value}")
        
        report.append("\n" + "=" * 60)
        return "\n".join(report)

# 全局检测实例
CHECKER = None

def init_checker(game_instance=None):
    """初始化检测器"""
    global CHECKER
    CHECKER = SelfChecker(game_instance)
    return CHECKER

def get_checker():
    """获取检测器实例"""
    global CHECKER
    if CHECKER is None:
        CHECKER = init_checker()
    return CHECKER