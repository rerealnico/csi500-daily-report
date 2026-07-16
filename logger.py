"""
日志系统 - 控制台 INFO + 文件 DEBUG
不替换现有 print，提供补充式文件日志
"""
import logging
import sys
from pathlib import Path
from datetime import datetime
from config import PROJECT_ROOT


_LOG_DIR = PROJECT_ROOT / "logs"
_LOG_DIR.mkdir(exist_ok=True)

# 全局 Logger 实例
_logger = None


def get_logger(name: str = "csi500") -> logging.Logger:
    """获取 Logger 实例（单例，避免重复添加 handler）"""
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 控制台 Handler: INFO 及以上
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "[%(levelname)s] %(message)s"
    ))
    logger.addHandler(console)

    # 文件 Handler: DEBUG 及以上（每天一个文件）
    log_file = _LOG_DIR / f"run_{datetime.now().strftime('%Y%m%d')}.log"
    file_h = logging.FileHandler(log_file, encoding="utf-8")
    file_h.setLevel(logging.DEBUG)
    file_h.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(file_h)

    _logger = logger
    return logger
