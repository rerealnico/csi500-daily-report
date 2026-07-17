"""
可视化模块 - 生成复盘分析图表
v2.0 - 美观大气大盘面风格
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.ticker as ticker
import pandas as pd
import numpy as np
from pathlib import Path
from config import REPORT_CONFIG


# ========== 中文字体设置 ==========

FONT_SETUP_DONE = False

def _setup_chinese_font():
    """设置 matplotlib 支持中文显示（兼容 Windows / Linux 云函数）"""
    global FONT_SETUP_DONE
    if FONT_SETUP_DONE:
        return True

    font_candidates = [
        "Microsoft YaHei",      # Windows 微软雅黑
        "SimHei",               # Windows 黑体
        "DengXian",             # Windows 等线
        "WenQuanYi Zen Hei",    # Linux (GitHub Actions)
        "Noto Sans CJK SC",     # Linux
        "Source Han Sans CN",   # 思源黑体
        "DejaVu Sans",          # 通用回退
    ]
    for font_name in font_candidates:
        try:
            fm.findfont(font_name, fallback_to_default=False)
            plt.rcParams["font.sans-serif"] = [font_name]
            plt.rcParams["axes.unicode_minus"] = False
            FONT_SETUP_DONE = True
            return True
        except Exception:
            continue
    print("  [WARN] 未找到中文字体，图表中文可能显示为方框")
    plt.rcParams["axes.unicode_minus"] = False
    return False


# ========== 配色方案 ==========

COLORS = {
    "primary": "#1976D2",
    "secondary": "#388E3C",
    "accent": "#F57C00",
    "danger": "#D32F2F",
    "purple": "#7B1FA2",
    "teal": "#00796B",
    "pink": "#C2185B",
    "bg": "#FAFAFA",
    "grid": "#E0E0E0",
    "text": "#212121",
    "top5": ["#1976D2", "#388E3C", "#F57C00", "#7B1FA2", "#00796B"],
}


def _style_ax(ax, title="", xlabel="", ylabel=""):
    """统一坐标轴样式"""
    ax.set_facecolor(COLORS["bg"])
    ax.set_title(title, fontsize=13, fontweight="bold", color=COLORS["text"], pad=12)
    ax.set_xlabel(xlabel, fontsize=10, color="#555")
    ax.set_ylabel(ylabel, fontsize=10, color="#555")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CCC")
    ax.spines["bottom"].set_color("#CCC")
    ax.tick_params(colors="#555", labelsize=9)
    ax.grid(axis="y", alpha=0.3, color=COLORS["grid"])


# ========== 评分分布图（增强版） ==========

def plot_score_distribution(
    scores: pd.DataFrame,
    output_dir: Path = None,
) -> str:
    """评分分布直方图（增强版）"""
    if output_dir is None:
        output_dir = REPORT_CONFIG["output_dir"]
    _setup_chinese_font()

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.patch.set_facecolor("white")

    # 1. 总分分布
    ax = axes[0, 0]
    _style_ax(ax, "综合评分分布", "综合评分", "股票数量")
    ax.hist(scores["total_score"], bins=35, color=COLORS["primary"],
            edgecolor="white", alpha=0.75, linewidth=0.5)
    median_val = scores["total_score"].median()
    ax.axvline(median_val, color=COLORS["danger"], linestyle="--", linewidth=1.5,
               label=f"中位数 {median_val:.1f}")
    ax.legend(fontsize=9, frameon=True, facecolor="white", edgecolor="#DDD")

    # 2. 估值评分分布
    ax = axes[0, 1]
    _style_ax(ax, "估值评分分布", "估值评分", "股票数量")
    if "valuation_score" in scores.columns:
        ax.hist(scores["valuation_score"].dropna(), bins=30, color=COLORS["secondary"],
                edgecolor="white", alpha=0.75, linewidth=0.5)

    # 3. 量能评分分布
    ax = axes[1, 0]
    _style_ax(ax, "量能评分分布", "量能评分", "股票数量")
    if "volume_score" in scores.columns:
        ax.hist(scores["volume_score"].dropna(), bins=30, color=COLORS["accent"],
                edgecolor="white", alpha=0.75, linewidth=0.5)

    # 4. 估值 vs 量能
    ax = axes[1, 1]
    _style_ax(ax, "估值 vs 量能", "估值评分", "量能评分")
    if "valuation_score" in scores.columns and "volume_score" in scores.columns:
        scatter = ax.scatter(
            scores["valuation_score"], scores["volume_score"],
            c=scores["total_score"], cmap="RdYlGn", alpha=0.5, s=15, edgecolors="white", linewidth=0.3
        )
        cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
        cbar.set_label("综合评分", fontsize=9)
        # 标Top10
        top10 = scores.head(10)
        for _, row in top10.iterrows():
            ax.annotate(
                row.get("stock_name", ""),
                (row["valuation_score"], row["volume_score"]),
                fontsize=7, alpha=0.9, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="gray", lw=0.5),
            )

    plt.tight_layout()
    filepath = output_dir / "score_distribution.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  [OK] 评分分布图已保存: {filepath}")
    return str(filepath)


# ========== TopN 推荐图（增强版） ==========

def plot_top_stocks(
    scores: pd.DataFrame,
    top_n: int = 20,
    output_dir: Path = None,
) -> str:
    """TopN 推荐股票横向柱状图（增强版）"""
    if output_dir is None:
        output_dir = REPORT_CONFIG["output_dir"]
    _setup_chinese_font()

    top = scores.head(top_n).copy()
    top = top.iloc[::-1]

    fig, ax = plt.subplots(figsize=(12, max(6, top_n * 0.42)))
    fig.patch.set_facecolor("white")

    labels = [f"{row.get('stock_name', '')}  {row.get('symbol', '')}" for _, row in top.iterrows()]
    y_pos = range(len(top))
    values = top["total_score"].values
    colors = plt.cm.RdYlGn(values / 100)

    ax.barh(y_pos, values, color=colors, edgecolor="white", linewidth=0.5, height=0.7)

    # 因子分解标注
    for i, (_, row) in enumerate(top.iterrows()):
        parts = []
        if "valuation_score" in row:
            parts.append(f"估{row['valuation_score']:.0f}")
        if "fundamental_score" in row:
            parts.append(f"基{row['fundamental_score']:.0f}")
        if "volume_score" in row:
            parts.append(f"量{row['volume_score']:.0f}")
        info = " | ".join(parts)
        ax.text(
            row["total_score"] + 0.3, i, info,
            va="center", fontsize=7.5, color="#666"
        )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    _style_ax(ax, f"中证500 Top {top_n} 推荐", "综合评分", "")
    ax.set_xlim(0, values.max() + 18)
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()

    filepath = output_dir / "top_stocks.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  [OK] Top{top_n} 推荐图已保存: {filepath}")
    return str(filepath)


# ========== 大盘面仪表盘（新增） ==========

def plot_dashboard(
    scores: pd.DataFrame,
    klines: pd.DataFrame,
    top_n: int = 5,
    output_dir: Path = None,
) -> str:
    """
    综合大盘面仪表盘

    包含:
    - 左上: Top5 评分分解柱
    - 右上: #1 股票的多因子雷达图
    - 下:   Top3 近60日价格走势
    """
    if output_dir is None:
        output_dir = REPORT_CONFIG["output_dir"]
    _setup_chinese_font()

    top_stocks = scores.head(top_n)

    fig = plt.figure(figsize=(18, 10))
    fig.patch.set_facecolor("white")
    fig.suptitle("中证500 每日复盘仪表盘", fontsize=18, fontweight="bold",
                 color=COLORS["text"], y=0.98)

    # ===== 左上: Top5 评分分解 =====
    ax1 = fig.add_axes([0.05, 0.55, 0.42, 0.38])
    _style_ax(ax1, "推荐 Top5 评分分解", "评分", "股票")

    names = [f"{r['stock_name']}\n({r['symbol'][-6:]})" for _, r in top_stocks.iterrows()]
    x = np.arange(len(names))
    width = 0.2

    metrics = [
        ("估值", "valuation_score", COLORS["primary"]),
        ("基本面", "fundamental_score", COLORS["secondary"]),
        ("量能", "volume_score", COLORS["accent"]),
        ("动量", "momentum_score", COLORS["purple"]),
        ("资金流", "capital_flow_score", COLORS["pink"]),
    ]

    for i, (label, col, color) in enumerate(metrics):
        if col in top_stocks.columns:
            vals = top_stocks[col].fillna(50).values
            ax1.bar(x + (i - 1.5) * width, vals, width, label=label,
                    color=color, alpha=0.8, edgecolor="white", linewidth=0.5)

    ax1.set_xticks(x)
    ax1.set_xticklabels(names, fontsize=8)
    ax1.legend(fontsize=8, frameon=True, facecolor="white", edgecolor="#DDD",
               loc="upper right")
    ax1.set_ylim(0, 100)

    # ===== 右上: #1 股票雷达图 =====
    if len(top_stocks) > 0:
        ax2 = fig.add_axes([0.55, 0.55, 0.42, 0.38], projection="polar")
        best = top_stocks.iloc[0]

        categories = ["估值", "基本面", "量能", "动量", "资金流"]
        cols = ["valuation_score", "fundamental_score", "volume_score", "momentum_score", "capital_flow_score"]
        values = [float(best.get(c, 50)) / 100 * 5 for c in cols]

        angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
        values += values[:1]
        angles += angles[:1]

        ax2.plot(angles, values, "o-", linewidth=2, color=COLORS["primary"], alpha=0.8)
        ax2.fill(angles, values, alpha=0.15, color=COLORS["primary"])
        ax2.set_xticks(angles[:-1])
        ax2.set_xticklabels(categories, fontsize=10)
        ax2.set_ylim(0, 5.5)
        ax2.set_title(f"★ {best.get('stock_name', '')}({best.get('symbol', '')[-6:]})",
                      fontsize=12, fontweight="bold", pad=15, color=COLORS["text"])
        ax2.set_yticklabels([])
        ax2.grid(alpha=0.3)

    # ===== 下方: Top3 价格走势 =====
    ax3 = fig.add_axes([0.05, 0.05, 0.92, 0.42])
    _style_ax(ax3, "Top3 推荐 · 近60日价格走势", "日期", "价格（归一化）")

    if klines is not None and not klines.empty:
        top3_symbols = top_stocks["symbol"].tolist()[:3]
        top3_names = {row["symbol"]: row["stock_name"] for _, row in top_stocks.iterrows()}

        # 取每只股票最近60个交易日的数据
        for idx, symbol in enumerate(top3_symbols):
            stock_data = klines[klines["symbol"] == symbol].sort_values("date").tail(60)
            if stock_data.empty:
                continue
            # 归一化价格（以第一日为基准100）
            first_close = stock_data["close"].iloc[0]
            normalized = stock_data["close"] / first_close * 100
            name = top3_names.get(symbol, symbol)
            ax3.plot(stock_data["date"], normalized,
                     color=COLORS["top5"][idx], linewidth=2, alpha=0.85,
                     marker="o", markersize=3, label=f"{name}({symbol[-6:]})")

        ax3.legend(fontsize=9, frameon=True, facecolor="white", edgecolor="#DDD",
                   loc="best", ncol=3)
        ax3.axhline(y=100, color="#999", linestyle="--", linewidth=0.5, alpha=0.5)
        ax3.set_xlim(auto=True)
        #日期标签旋转
        for label in ax3.get_xticklabels():
            label.set_rotation(30)
            label.set_ha("right")
    else:
        ax3.text(0.5, 0.5, "等待行情数据...", ha="center", va="center",
                 fontsize=14, color="#999", transform=ax3.transAxes)

    filepath = output_dir / "dashboard.png"
    fig.savefig(filepath, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  [OK] 大盘面仪表盘已保存: {filepath}")
    return str(filepath)


# ========== 全量生成 ==========

def generate_all_charts(
    scores: pd.DataFrame,
    klines: pd.DataFrame = None,
    output_dir: Path = None,
) -> list[str]:
    """
    生成所有图表

    Returns
    -------
    list[str]
        所有生成的文件路径列表
    """
    if output_dir is None:
        output_dir = REPORT_CONFIG["output_dir"]
    output_dir.mkdir(exist_ok=True)

    charts = []
    try:
        charts.append(plot_score_distribution(scores, output_dir))
    except Exception as e:
        print(f"  [WARN] 评分分布图生成失败: {e}")

    try:
        charts.append(plot_top_stocks(scores, top_n=20, output_dir=output_dir))
    except Exception as e:
        print(f"  [WARN] Top推荐图生成失败: {e}")

    if klines is not None:
        try:
            charts.append(plot_dashboard(scores, klines, top_n=5, output_dir=output_dir))
        except Exception as e:
            print(f"  [WARN] 仪表盘生成失败: {e}")

    return charts


if __name__ == "__main__":
    # 测试可视化
    from data_fetcher import fetch_csi500_constituents, fetch_daily_klines
    from valuation_analyzer import calculate_valuation_scores
    from volume_analyzer import calculate_volume_scores
    from scorer import calculate_final_scores

    constituents = fetch_csi500_constituents()
    symbols = constituents["symbol"].tolist()[:10]
    klines = fetch_daily_klines(symbols)

    val = calculate_valuation_scores(klines)
    vol = calculate_volume_scores(klines)
    final = calculate_final_scores(constituents, val, vol)

    generate_all_charts(final, klines)
    print("\n所有图表生成完成！")
