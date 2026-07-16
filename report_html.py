"""
HTML 报告生成模块
生成美观的 HTML 页面，内嵌图表，发布到 GitHub Pages
"""
import base64
from pathlib import Path
from datetime import datetime
from config import REPORT_CONFIG


def _img_to_b64(filepath: str) -> str:
    """图片转 base64 内嵌"""
    path = Path(filepath)
    if not path.exists():
        return None
    suffix = path.suffix.lower()
    mime = "png" if suffix == ".png" else "jpeg"
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/{mime};base64,{data}"


def generate_html_report(
    report_text: str,
    top_stocks: list,
    chart_files: list[str] = None,
    report_date: str = None,
    output_path: str = None,
) -> str:
    """
    生成 HTML 报告页面

    Parameters
    ----------
    report_text : str
        文本报告内容
    chart_files : list[str]
        图表文件路径列表
    report_date : str
        报告日期

    Returns
    -------
    str
        HTML 文件路径
    """
    if report_date is None:
        report_date = datetime.now().strftime("%Y-%m-%d")

    # 图表转 base64
    chart_images = []
    if chart_files:
        for fp in chart_files:
            b64 = _img_to_b64(fp)
            if b64:
                chart_images.append(b64)

    # 解析报告文本
    lines = report_text.strip().split("\n")

    # 构建 Top 表格
    top_rows = ""
    for i, stock in enumerate(top_stocks[:10], 1):
        name = stock.get("stock_name", "")
        symbol = stock.get("symbol", "")
        total = stock.get("total_score", 0)
        val = stock.get("valuation_score", 0)
        fin = stock.get("fundamental_score", 0)
        vol = stock.get("volume_score", 0)
        mom = stock.get("momentum_score", 0)
        roe = stock.get("roe", "")
        action = stock.get("action", "")

        roe_str = ""
        if roe is not None and roe != "":
            try:
                roe_pct = float(roe) * 100
                roe_str = f"{roe_pct:.1f}%"
            except (ValueError, TypeError):
                pass

        top_rows += f"""
        <tr>
            <td class="rank">{i}</td>
            <td class="name"><strong>{name}</strong><span class="code">{symbol}</span></td>
            <td><span class="score-main">{total:.1f}</span></td>
            <td>{val:.0f}</td>
            <td>{fin:.0f}</td>
            <td>{vol:.0f}</td>
            <td>{mom:.0f}</td>
            <td class="roe">{roe_str}</td>
            <td><span class="tag tag-{action}">{action}</span></td>
        </tr>"""

    # 图表区 HTML
    charts_html = ""
    if chart_images:
        charts_html = '<div class="charts-section">\n<h2>📊 图表分析</h2>\n<div class="charts-grid">\n'
        # 仪表盘放最大
        if len(chart_images) >= 3:
            charts_html += f'<div class="chart-full"><img src="{chart_images[2]}" alt="大盘面仪表盘"></div>\n'
        # 分布图和Top图并列
        if len(chart_images) >= 1:
            charts_html += f'<div class="chart-half"><img src="{chart_images[0]}" alt="评分分布"></div>\n'
        if len(chart_images) >= 2:
            charts_html += f'<div class="chart-half"><img src="{chart_images[1]}" alt="Top推荐"></div>\n'
        charts_html += "</div>\n</div>"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>中证500 每日复盘报告 — {report_date}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, "Microsoft YaHei", "PingFang SC", sans-serif;
            background: #f5f6fa;
            color: #2d3436;
            line-height: 1.6;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}

        /* Header */
        .header {{
            background: linear-gradient(135deg, #1976D2, #1565C0);
            color: white;
            border-radius: 12px;
            padding: 32px;
            margin-bottom: 24px;
            text-align: center;
        }}
        .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
        .header .date {{ font-size: 14px; opacity: 0.85; }}
        .header .sub {{ font-size: 13px; opacity: 0.7; margin-top: 4px; }}

        /* Summary cards */
        .summary {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
        .summary-card {{
            flex: 1; min-width: 140px;
            background: white; border-radius: 10px; padding: 18px 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            text-align: center;
        }}
        .summary-card .num {{ font-size: 28px; font-weight: bold; color: #1976D2; }}
        .summary-card .label {{ font-size: 13px; color: #636e72; margin-top: 4px; }}

        /* Table */
        .section {{ background: white; border-radius: 10px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        .section h2 {{ font-size: 18px; margin-bottom: 16px; color: #2d3436; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th {{
            background: #f8f9fa; color: #636e72; font-weight: 600;
            padding: 10px 8px; text-align: left; border-bottom: 2px solid #e9ecef;
            font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;
        }}
        td {{ padding: 10px 8px; border-bottom: 1px solid #f0f0f0; }}
        tr:hover {{ background: #f8f9ff; }}
        .rank {{ font-weight: bold; color: #1976D2; width: 30px; text-align: center; }}
        .name {{ min-width: 100px; }}
        .name .code {{ font-size: 11px; color: #b2bec3; margin-left: 4px; }}
        .score-main {{ font-weight: bold; color: #2d3436; }}
        .roe {{ color: #00b894; font-weight: 500; }}

        /* Tags */
        .tag {{
            display: inline-block; padding: 2px 10px; border-radius: 12px;
            font-size: 11px; font-weight: 500;
        }}
        .tag-推荐关注 {{ background: #00b894; color: white; }}
        .tag-可以关注 {{ background: #00cec9; color: white; }}
        .tag-持有观望 {{ background: #fdcb6e; color: #2d3436; }}
        .tag-谨慎观察 {{ background: #e17055; color: white; }}
        .tag-注意风险 {{ background: #d63031; color: white; }}
        .tag-亏损暂避 {{ background: #636e72; color: white; }}

        /* Charts */
        .charts-section h2 {{ margin-bottom: 16px; }}
        .charts-grid {{ display: flex; flex-wrap: wrap; gap: 16px; }}
        .chart-full {{ width: 100%; }}
        .chart-half {{ flex: 1; min-width: 300px; }}
        .charts-grid img {{
            width: 100%; border-radius: 8px; border: 1px solid #e9ecef;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }}

        /* Footer */
        .footer {{
            text-align: center; padding: 20px; color: #b2bec3; font-size: 12px;
        }}

        @media (max-width: 600px) {{
            .container {{ padding: 10px; }}
            .header {{ padding: 20px; }}
            .header h1 {{ font-size: 18px; }}
            .summary-card .num {{ font-size: 22px; }}
            table {{ font-size: 12px; }}
            td, th {{ padding: 6px 4px; }}
            .chart-half {{ min-width: 100%; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>📈 中证500 每日复盘报告</h1>
            <div class="date">报告日期: {report_date}</div>
            <div class="sub">数据来源: baostock | 评分模型: 估值+基本面+量能+动量</div>
        </div>

        <!-- Summary -->
        <div class="summary">
            <div class="summary-card">
                <div class="num">{len(top_stocks)}</div>
                <div class="label">推荐关注</div>
            </div>
            <div class="summary-card">
                <div class="num">{top_stocks[0]['total_score']:.1f if top_stocks else 0}</div>
                <div class="label">最高评分</div>
            </div>
            <div class="summary-card">
                <div class="num">{top_stocks[0].get('stock_name', '-') if top_stocks else '-'}</div>
                <div class="label">冠军股票</div>
            </div>
        </div>

        <!-- Top Stocks Table -->
        <div class="section">
            <h2>🏆 推荐关注 Top 10</h2>
            <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>股票</th>
                        <th>总分</th>
                        <th>估值</th>
                        <th>基本面</th>
                        <th>量能</th>
                        <th>动量</th>
                        <th>ROE</th>
                        <th>建议</th>
                    </tr>
                </thead>
                <tbody>
                    {top_rows}
                </tbody>
            </table>
            </div>
        </div>

        <!-- Charts -->
        {charts_html}

        <!-- Full Report Text -->
        <div class="section">
            <h2>📝 完整报告</h2>
            <pre style="font-size:13px; color:#555; line-height:1.7; white-space:pre-wrap; font-family:inherit;">{report_text}</pre>
        </div>

        <div class="footer">
            自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · GitHub Actions
        </div>
    </div>
</body>
</html>"""

    # 保存
    output_dir = REPORT_CONFIG["output_dir"]
    output_dir.mkdir(exist_ok=True)
    if output_path is None:
        output_path = str(output_dir / "report.html")

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"  [OK] HTML 报告已生成: {output_path}")
    return output_path
