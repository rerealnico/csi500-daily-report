"""
配置文件 - 中证500每日复盘分析系统
"""
from pathlib import Path
from datetime import datetime

# 项目路径
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# 数据缓存
KLINE_CACHE_FILE = DATA_DIR / "klines.parquet"
FUNDA_CACHE_FILE = DATA_DIR / "fundamentals.parquet"

# 缓存过期配置
CACHE_CONFIG = {
    "kline_max_age_hours": 24,   # 日线缓存超过24小时强制刷新
    "funda_max_age_days": 7,     # 基本面缓存超过7天强制刷新
}

# 中证500 指数代码
CSI500_INDEX_CODE = "000905"

# 估值分析参数
VALUATION_CONFIG = {
    "pe_percentile_years": 10,
    "pb_percentile_years": 10,
    "pe_overvalued_threshold": 80,
    "pe_undervalued_threshold": 20,
}

# 量能分析参数
VOLUME_CONFIG = {
    "volume_ma_windows": [5, 20, 60],
    "volume_surge_ratio": 2.0,
    "turnover_percentile_years": 3,
}

# 评分权重
SCORE_WEIGHTS = {
    "valuation": 0.25,
    "fundamental": 0.25,
    "volume": 0.25,
    "momentum": 0.15,
    "capital_flow": 0.10,
}

def get_latest_financial_period() -> tuple:
    """动态推断最新可用的财报年份和季度（留出财报发布时间缓冲）"""
    now = datetime.now()
    m = now.month
    if m <= 4:      # Jan-Apr: 前一年年报（年报截止4月底发布）
        return now.year - 1, 4
    elif m <= 7:    # May-Jul: 当年一季报（截止4月底）
        return now.year, 1
    elif m <= 10:   # Aug-Oct: 当年中报（截止8月底）
        return now.year, 2
    else:           # Nov-Dec: 当年三季报（截止10月底）
        return now.year, 3


# 基本面分析参数
_year, _quarter = get_latest_financial_period()
FUNDAMENTAL_CONFIG = {
    "year": _year,
    "quarter": _quarter,
    "scoring": {
        "roe_weight": 0.35,
        "margin_weight": 0.25,
        "debt_weight": 0.25,
        "cashflow_weight": 0.15,
    },
    "filters": {
        "exclude_loss": True,  # 排除亏损股
        "min_roe": 0.0,        # ROE最低要求
    },
}

# 报告输出
REPORT_CONFIG = {
    "top_n": 10,
    "output_dir": PROJECT_ROOT / "reports",
}
REPORT_CONFIG["output_dir"].mkdir(exist_ok=True)
