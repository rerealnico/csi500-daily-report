"""
量能分析模块 - 计算成交量变化、换手率、量价配合度
"""
import pandas as pd
import numpy as np
from config import VOLUME_CONFIG


def calculate_volume_scores(klines: pd.DataFrame) -> pd.DataFrame:
    """
    计算每只股票的量能评分

    Parameters
    ----------
    klines : pd.DataFrame
        日线行情数据（需含 date, close, volume, turnover, symbol）

    Returns
    -------
    pd.DataFrame
        每只股票的量能分析结果
    """
    print("\n[量能分析] 正在计算量能评分...")

    df = klines.copy().sort_values(["symbol", "date"])

    # 计算各类量能指标
    results = []

    for symbol, group in df.groupby("symbol"):
        group = group.reset_index(drop=True)

        if len(group) < 60:
            continue

        latest = group.iloc[-1]
        volume_series = group["volume"].astype(float)

        # 1. 成交量均线偏离度
        volume_ma = {}
        for window in VOLUME_CONFIG["volume_ma_windows"]:
            ma = volume_series.rolling(window=window).mean().iloc[-1]
            volume_ma[f"volume_ma_{window}"] = ma

        latest_volume = latest["volume"]
        volume_ma5 = volume_ma["volume_ma_5"]
        volume_ma20 = volume_ma["volume_ma_20"]

        # 量比：当日量 / 20日均量
        volume_ratio_20 = latest_volume / (volume_ma20 + 1e-10)

        # 2. 换手率分析
        turnover_series = group["turnover"].astype(float)
        turnover_ma20 = turnover_series.rolling(20).mean().iloc[-1]

        # 3. 量价配合度
        # 过去5日：价格上涨+放量 = 正向信号，价格下跌+放量 = 负向信号
        recent_5 = group.tail(5)
        price_trend = (
            recent_5["close"].iloc[-1] - recent_5["close"].iloc[0]
        ) / recent_5["close"].iloc[0]

        volume_trend = (
            recent_5["volume"].astype(float).mean()
            / (volume_series.tail(20).mean() + 1e-10)
        )

        # 量价配合得分：上涨放量(+)、上涨缩量(中性)、下跌放量(-)、下跌缩量(中性)
        if price_trend > 0.01 and volume_trend > 1.2:
            price_volume_score = 80  # 上涨放量，积极信号
        elif price_trend > 0.01 and volume_trend > 1.0:
            price_volume_score = 60  # 上涨正常
        elif price_trend < -0.01 and volume_trend > 1.2:
            price_volume_score = 20  # 下跌放量，风险信号
        elif price_trend < -0.01 and volume_trend < 0.8:
            price_volume_score = 60  # 下跌缩量，抛压减弱
        else:
            price_volume_score = 40  # 中性

        # 4. 成交量突变检测
        volume_std = volume_series.tail(60).std()
        volume_mean = volume_series.tail(60).mean()
        if volume_mean > 0:
            volume_zscore = (latest_volume - volume_mean) / (volume_std + 1e-10)
        else:
            volume_zscore = 0

        # 突变得分：大幅放量或缩量都值得关注
        if abs(volume_zscore) > 3:
            surge_score = 30  # 极端放量/缩量，需要警惕
        elif volume_zscore > 2:
            surge_score = 70  # 明显放量
        elif volume_zscore > 1:
            surge_score = 60  # 温和放量
        elif volume_zscore < -1:
            surge_score = 40  # 缩量
        else:
            surge_score = 50  # 正常

        # 5. 综合量能评分
        volume_score = (
            0.35 * _volume_ratio_score(volume_ratio_20)
            + 0.30 * price_volume_score
            + 0.20 * surge_score
            + 0.15 * _turnover_score(turnover_ma20)
        )

        results.append({
            "symbol": symbol,
            "latest_volume": latest_volume,
            "volume_ratio_20": round(volume_ratio_20, 2),
            "volume_ma5": round(volume_ma5, 0),
            "volume_ma20": round(volume_ma20, 0),
            "turnover": latest["turnover"],
            "turnover_ma20": round(turnover_ma20, 2),
            "price_trend_5d": round(price_trend * 100, 2),
            "volume_trend_5d": round(volume_trend, 2),
            "price_volume_score": round(price_volume_score, 1),
            "volume_zscore": round(volume_zscore, 2),
            "surge_score": round(surge_score, 1),
            "volume_score": round(volume_score, 1),
        })

    result = pd.DataFrame(results)
    print(f"  [OK] 量能评分计算完成，共 {len(result)} 只股票")
    return result


def _volume_ratio_score(ratio: float) -> float:
    """
    量比评分
    ratio=1 正常，ratio>1 放量，ratio<1 缩量
    """
    if ratio > 3:
        return 30   # 异常放量，警惕
    elif ratio > 2:
        return 70   # 明显放量，偏积极
    elif ratio > 1.2:
        return 60   # 温和放量
    elif ratio > 0.8:
        return 50   # 正常
    elif ratio > 0.5:
        return 40   # 缩量
    else:
        return 30   # 严重缩量


def _turnover_score(turnover_ma20: float) -> float:
    """
    换手率评分：过高(>10%)偏低分(筹码不稳定)，过低(<0.5%)也偏低分(流动性差)
    1%~5% 为最佳区间
    """
    if turnover_ma20 > 10:
        return 30
    elif turnover_ma20 > 5:
        return 60
    elif turnover_ma20 > 1:
        return 80
    elif turnover_ma20 > 0.5:
        return 60
    else:
        return 30


if __name__ == "__main__":
    from data_fetcher import fetch_csi500_constituents, fetch_daily_klines

    constituents = fetch_csi500_constituents()
    symbols = constituents["symbol"].tolist()[:10]

    klines = fetch_daily_klines(symbols)

    result = calculate_volume_scores(klines)
    print(result.head(10))
