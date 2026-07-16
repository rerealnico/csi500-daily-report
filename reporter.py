"""
报告生成模块 - 输出文本报告到控制台和文件
"""
from datetime import datetime
from config import REPORT_CONFIG


def generate_report(
    constituents_count: int,
    top_stocks: list,
    bottom_stocks: list,
    report_date: str = None,
) -> str:
    """
    生成每日复盘报告

    Parameters
    ----------
    constituents_count : int
        分析的成分股数量
    top_stocks : list[dict]
        推荐列表
    bottom_stocks : list[dict]
        风险列表
    report_date : str
        报告日期

    Returns
    -------
    str
        报告文本
    """
    if report_date is None:
        report_date = datetime.now().strftime("%Y-%m-%d")

    lines = []
    lines.append("=" * 60)
    lines.append(f"  CSI 500 每日复盘报告    {report_date}")
    lines.append("=" * 60)

    if top_stocks:
        lines.append("")
        lines.append(f"[推荐关注] 共 {len(top_stocks)} 只")
        lines.append("-" * 60)
        for i, stock in enumerate(top_stocks, 1):
            name = stock.get("stock_name", "")
            symbol = stock.get("symbol", "")
            score = stock.get("total_score", 0)
            val = stock.get("valuation_score", 0)
            vol = stock.get("volume_score", 0)
            mom = stock.get("momentum_score", 0)
            fin = stock.get("fundamental_score", 0)
            roe = stock.get("roe", "")
            roe_str = f"ROE:{float(roe)*100:.1f}%" if roe not in (None, "") and not (isinstance(roe, float) and roe != roe) else ""
            lines.append(
                f"  {i:2d}. {name}({symbol}) 总分:{score:.1f}  "
                f"估值:{val:.0f} 基本面:{fin:.0f} 量能:{vol:.0f} 动量:{mom:.0f} "
                f"{roe_str}"
            )

    if bottom_stocks:
        lines.append("")
        lines.append(f"[风险提示] 共 {len(bottom_stocks)} 只")
        lines.append("-" * 60)
        for i, stock in enumerate(bottom_stocks, 1):
            name = stock.get("stock_name", "")
            symbol = stock.get("symbol", "")
            score = stock.get("total_score", 0)
            lines.append(
                f"  {i:2d}. {name}({symbol}) 总分:{score:.1f}  注意风险"
            )

    lines.append("")
    lines.append("-" * 60)
    lines.append(f"  本次共分析 {constituents_count} 只成分股")
    lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)

    return "\n".join(lines)


def save_report(report_text: str) -> str:
    """保存报告到文件"""
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = REPORT_CONFIG["output_dir"] / f"report_{date_str}.txt"
    filepath.write_text(report_text, encoding="utf-8")
    print(f"\n[报告] 已保存至: {filepath}")
    return str(filepath)


if __name__ == "__main__":
    # 测试
    top = [
        {"stock_name": "测试A", "symbol": "000001",
         "total_score": 85.0, "valuation_score": 90,
         "volume_score": 80, "momentum_score": 75},
        {"stock_name": "测试B", "symbol": "000002",
         "total_score": 78.0, "valuation_score": 70,
         "volume_score": 85, "momentum_score": 82},
    ]
    bottom = [
        {"stock_name": "测试C", "symbol": "000003",
         "total_score": 25.0, "valuation_score": 20,
         "volume_score": 30, "momentum_score": 15},
    ]
    text = generate_report(2, top, bottom)
    print(text)
    save_report(text)
