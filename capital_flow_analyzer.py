"""
量价配合分析模块 - 从行情数据估算量价关系与活跃度

⚠️ 重要说明：
本模块基于公开行情数据（价格+成交量）间接估算资金活跃度，
并非真实的Level-2资金流数据。输出仅供参考，不反映主力资金真实动向。

分析维度：
- OHLC位置分析（收盘价在当日振幅中的位置 → 买卖压力代理）
- 成交量趋势（近期成交量相对历史均量的变化方向）
- 振幅活跃度（价格波动区间）
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

        # ========== 替换量价背离检测 ==========
        # 原版用 price_trend_5d + vol_trend_5d 判断，与 volume_analyzer 的
        # price_volume_score 高度重合（双重加权）。改用 OHLC 位置分析：
        # 收盘价在当日振幅中的位置 → 买卖压力代理
        # 高开低走收盘在低位 → 卖出压力大
        # 低开高走收盘在高位 → 买入意愿强

        # 仍计算 price_trend_5d 用于输出显示（不用于评分）
        price_trend_5d = (close_series.iloc[-1] / close_series.iloc[-6]) - 1 if len(close_series) >= 6 else 0
        vol_trend_5d = (volume_series.rolling(5).mean().iloc[-1] / volume_series.rolling(5).mean().iloc[-6]) - 1 if len(volume_series) >= 6 else 0

        ohlc_pressure = 0
        count_valid = 0
        for i in range(max(0, len(group)-5), len(group)):
            row = group.iloc[i]
            high = float(row.get("high", 0))
            low = float(row.get("low", 0))
            close = float(row.get("close", 0))
            open_p = float(row.get("open", 0))
            if high > low and close > 0:
                # 收盘在振幅中的位置: 0(最低)~1(最高)
                range_pos = (close - low) / (high - low + 1e-10)
                range_pos = max(0, min(1, range_pos))
                # 收盘在振幅上1/3 → 买入压力 (0.8~1.0区间 → 60~85分)
                # 收盘在振幅下1/3 → 卖出压力 (0~0.33区间 → 15~40分)
                if range_pos > 0.66:
                    ohlc_pressure += 60 + 25 * (range_pos - 0.66) / 0.34
                elif range_pos < 0.33:
                    ohlc_pressure += 40 - 25 * (0.33 - range_pos) / 0.33
                else:
                    ohlc_pressure += 50
                count_valid += 1

        if count_valid > 0:
            divergence_score = ohlc_pressure / count_valid
        else:
            divergence_score = 50

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
    print(f"  [OK] 量价配合评分计算完成，共 {len(result)} 只股票")
    print(f"  [INFO] 注意：评分为基于公开行情的估算值，非真实Level-2资金流数据")
    return result


if __name__ == "__main__":
    from data_fetcher import fetch_csi500_constituents, fetch_daily_klines

    constituents = fetch_csi500_constituents()
    symbols = constituents["symbol"].tolist()[:10]
    klines = fetch_daily_klines(symbols)

    result = calculate_capital_flow_scores(klines)
    print(result.head(10))
