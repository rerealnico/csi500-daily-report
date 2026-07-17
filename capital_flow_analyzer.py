"""
资金流分析模块 - 从行情数据估算资金流向与活跃度
基于量价背离、成交量趋势、振幅活跃度等指标
"""
import pandas as pd
import numpy as np


def calculate_capital_flow_scores(klines: pd.DataFrame) -> pd.DataFrame:
    """
    计算每只股票的资金流评分

    估算维度：
    - 量价配合（价格与成交量的趋势一致性）
    - 成交量趋势（近期成交量相对历史均量的变化方向）
    - 振幅活跃度（价格波动区间与成交量的关联）

    Parameters
    ----------
    klines : pd.DataFrame
        日线行情（需含 date, close, volume, symbol）

    Returns
    -------
    pd.DataFrame
        每只股票的资金流评分
    """
    print("\n[资金流] 正在估算资金流向评分...")

    df = klines.copy().sort_values(["symbol", "date"])
    results = []

    for symbol, group in df.groupby("symbol"):
        group = group.reset_index(drop=True)

        if len(group) < 20:
            continue

        latest = group.iloc[-1]
        recent = group.tail(20)
        volume_series = group["volume"].astype(float)
        close_series = group["close"].astype(float)

        # 1. 量价背离检测
        price_ma5 = close_series.rolling(5).mean()
        volume_ma5 = volume_series.rolling(5).mean()

        # 近5日价格趋势 vs 量能趋势
        price_trend_5d = (close_series.iloc[-1] / close_series.iloc[-6]) - 1 if len(close_series) >= 6 else 0
        vol_trend_5d = (volume_ma5.iloc[-1] / volume_ma5.iloc[-6]) - 1 if len(volume_ma5) >= 6 else 0

        # 量价配合评分
        if price_trend_5d > 0.02 and vol_trend_5d > 0.05:
            divergence_score = 85   # 价涨量增 → 资金流入
        elif price_trend_5d > 0.02 and vol_trend_5d > -0.05:
            divergence_score = 65   # 价涨量稳
        elif price_trend_5d > 0.02:
            divergence_score = 50   # 价涨量缩 → 上涨乏力
        elif price_trend_5d < -0.02 and vol_trend_5d > 0.05:
            divergence_score = 20   # 价跌量增 → 资金流出
        elif price_trend_5d < -0.02 and vol_trend_5d < -0.05:
            divergence_score = 60   # 价跌量缩 → 抛压减弱
        else:
            divergence_score = 45   # 中性

        # 2. 成交量趋势评分（近10日均量 vs 近60日均量）
        vol_ma10 = volume_series.tail(10).mean()
        vol_ma60 = volume_series.tail(60).mean() if len(volume_series) >= 60 else volume_series.mean()
        vol_ratio = vol_ma10 / (vol_ma60 + 1e-10)

        if vol_ratio > 1.3:
            vol_trend_score = 75   # 明显放量 → 资金活跃
        elif vol_ratio > 1.1:
            vol_trend_score = 60   # 温和放量
        elif vol_ratio > 0.9:
            vol_trend_score = 50   # 正常
        elif vol_ratio > 0.7:
            vol_trend_score = 40   # 缩量
        else:
            vol_trend_score = 30   # 严重缩量 → 资金冷淡

        # 3. 振幅活跃度评分
        if "high" in recent.columns and "low" in recent.columns:
            recent_amp = (recent["high"].astype(float) - recent["low"].astype(float)) / recent["close"].astype(float)
            avg_amp = recent_amp.mean()
        else:
            avg_amp = 0.02

        # 用近20日振幅中位数衡量活跃度
        if avg_amp > 0.05:
            amp_score = 70   # 高活跃
        elif avg_amp > 0.03:
            amp_score = 60   # 较活跃
        elif avg_amp > 0.02:
            amp_score = 50   # 正常
        elif avg_amp > 0.01:
            amp_score = 35   # 不活跃
        else:
            amp_score = 25   # 极不活跃

        # 4. 综合资金流评分
        capital_flow_score = (
            0.40 * divergence_score
            + 0.35 * vol_trend_score
            + 0.25 * amp_score
        )

        results.append({
            "symbol": symbol,
            "price_trend_5d": round(price_trend_5d * 100, 2),
            "vol_trend_5d": round(vol_trend_5d * 100, 2),
            "vol_ratio_10_60": round(vol_ratio, 2),
            "divergence_score": round(divergence_score, 1),
            "vol_trend_score": round(vol_trend_score, 1),
            "amp_score": round(amp_score, 1),
            "capital_flow_score": round(capital_flow_score, 1),
        })

    result = pd.DataFrame(results)
    print(f"  [OK] 资金流评分计算完成，共 {len(result)} 只股票")
    return result


if __name__ == "__main__":
    from data_fetcher import fetch_csi500_constituents, fetch_daily_klines

    constituents = fetch_csi500_constituents()
    symbols = constituents["symbol"].tolist()[:10]
    klines = fetch_daily_klines(symbols)

    result = calculate_capital_flow_scores(klines)
    print(result.head(10))
