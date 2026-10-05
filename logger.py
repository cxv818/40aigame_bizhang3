# v36.0 (2026-10-05) — 36aigame
"""游戏日志系统：记录所有重要事件，便于调试和分析。"""

import os
import json
import time
from datetime import datetime

class GameLogger:
    """游戏日志记录器"""
    
    def __init__(self, log_dir="/tmp/game_logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # 创建日志文件
        self.log_file = os.path.join(log_dir, f"game_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        self.event_file = os.path.join(log_dir, f"events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        
        # 事件列表
        self.events = []
        
        # 写入日志头
        self._write_header()
    
    def _write_header(self):
        """写入日志头"""
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write(f"# 游戏日志 - 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("# 格式: [时间] [级别] [模块] 消息\n")
            f.write("-" * 60 + "\n")
    
    def log(self, level, module, message):
        """记录日志
        
        Args:
            level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
            module: 模块名
            message: 日志消息
        """
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        log_line = f"[{timestamp}] [{level}] [{module}] {message}\n"
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_line)
    
    def debug(self, module, message):
        """记录调试日志"""
        self.log("DEBUG", module, message)
    
    def info(self, module, message):
        """记录信息日志"""
        self.log("INFO", module, message)
    
    def warning(self, module, message):
        """记录警告日志"""
        self.log("WARNING", module, message)
    
    def error(self, module, message):
        """记录错误日志"""
        self.log("ERROR", module, message)
    
    def event(self, event_type, data):
        """记录事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        event = {
            "timestamp": time.time(),
            "type": event_type,
            "data": data
        }
        self.events.append(event)
        
        # 每10个事件保存一次
        if len(self.events) % 10 == 0:
            self._save_events()
    
    def _save_events(self):
        """保存事件到JSON文件"""
        with open(self.event_file, 'w', encoding='utf-8') as f:
            json.dump(self.events, f, ensure_ascii=False, indent=2)
    
    def get_stats(self):
        """获取日志统计"""
        return {
            "log_file": self.log_file,
            "event_file": self.event_file,
            "event_count": len(self.events)
        }

# 全局日志实例
LOGGER = None

def init_logger(log_dir="/tmp/game_logs"):
    """初始化日志系统"""
    global LOGGER
    LOGGER = GameLogger(log_dir)
    return LOGGER

def get_logger():
    """获取日志实例"""
    global LOGGER
    if LOGGER is None:
        LOGGER = init_logger()
    return LOGGER