"""
HTML 报告生成模块
生成美观的 HTML 页面，内嵌图表，发布到 GitHub Pages
"""
import base64
import json
import pandas as pd
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


def _classify_board(symbol: str) -> str:
    """根据代码前缀判断板块：000=主板, 002=中小板, 300=创业板, 688=科创板, 其他=未知"""
    if symbol.startswith("6"):
        return "主板"
    elif symbol.startswith("00"):
        return "主板"
    elif symbol.startswith("002"):
        return "中小板"
    elif symbol.startswith("300"):
        return "创业板"
    elif symbol.startswith("688"):
        return "科创板"
    else:
        return "其他"


def _build_industry_distribution(top_stocks: list) -> str:
    """分析推荐股票的板块分布，返回 HTML 卡片"""
    boards = {}
    for stock in top_stocks:
        symbol = stock.get("symbol", "")
        board = _classify_board(symbol)
        boards[board] = boards.get(board, 0) + 1

    cards = ""
    for board in ["主板", "中小板", "创业板", "科创板"]:
        count = boards.get(board, 0)
        cards += f'<div class="summary-card"><div class="num">{count}</div><div class="label">{board}</div></div>\n'
    return cards


def generate_html_report(
    report_text: str,
    top_stocks: list,
    chart_files: list[str] = None,
    report_date: str = None,
    output_path: str = None,
    all_stocks: list = None,
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

    # 全量股票数据 JSON（用于客户端筛选选股）
    all_stocks_json = "[]"
    if all_stocks:
        try:
            # 清理 NaN/Infinity 等 JSON 不支持的数值
            clean = []
            for s in all_stocks:
                item = {}
                for k, v in s.items():
                    if k in ('symbol', 'stock_name', 'action', 'is_loss'):
                        item[k] = str(v) if not pd.isna(v) else ''
                    elif k == 'roe':
                        try:
                            item[k] = round(float(v), 4) if v is not None and not pd.isna(v) else None
                        except (ValueError, TypeError):
                            item[k] = None
                    else:
                        try:
                            item[k] = round(float(v), 1) if v is not None and not pd.isna(v) else None
                        except (ValueError, TypeError):
                            item[k] = None
                clean.append(item)
            all_stocks_json = json.dumps(clean, ensure_ascii=False)
        except Exception as e:
            print(f"  [WARN] 全量股票序列化失败: {e}")

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
            background: #f0f2f5;
            color: #2d3436;
            line-height: 1.6;
            transition: background 0.3s, color 0.3s;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}

        /* Header - Gradient */
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 16px;
            padding: 36px 32px;
            margin-bottom: 24px;
            text-align: center;
            box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
        }}
        .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
        .header .date {{ font-size: 14px; opacity: 0.85; }}
        .header .sub {{ font-size: 13px; opacity: 0.7; margin-top: 4px; }}

        /* Dark Mode Toggle */
        .theme-toggle {{
            position: fixed; top: 16px; right: 16px; z-index: 999;
            background: rgba(255,255,255,0.2); backdrop-filter: blur(8px);
            border: 1px solid rgba(255,255,255,0.3);
            color: white; width: 40px; height: 40px; border-radius: 50%;
            cursor: pointer; font-size: 18px;
            transition: all 0.3s;
        }}
        .theme-toggle:hover {{ background: rgba(255,255,255,0.3); transform: scale(1.1); }}

        /* Summary cards */
        .summary {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
        .summary-card {{
            flex: 1; min-width: 120px;
            background: white; border-radius: 12px; padding: 18px 16px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
            text-align: center;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .summary-card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.1); }}
        .summary-card .num {{ font-size: 28px; font-weight: bold; color: #667eea; }}
        .summary-card .label {{ font-size: 13px; color: #636e72; margin-top: 4px; }}

        /* Sections */
        .section {{
            background: white; border-radius: 12px; padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
            transition: box-shadow 0.2s;
        }}
        .section:hover {{ box-shadow: 0 8px 32px rgba(0,0,0,0.1); }}
        .section h2 {{ font-size: 18px; margin-bottom: 16px; color: #2d3436; }}

        /* Table - Sortable */
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th {{
            background: #f8f9fa; color: #636e72; font-weight: 600;
            padding: 10px 8px; text-align: left; border-bottom: 2px solid #e9ecef;
            font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;
            cursor: pointer; user-select: none;
            white-space: nowrap;
            transition: background 0.2s;
        }}
        th:hover {{ background: #eef1f5; }}
        th.sort-asc::after {{ content: " \25B2"; font-size: 10px; }}
        th.sort-desc::after {{ content: " \25BC"; font-size: 10px; }}
        td {{ padding: 10px 8px; border-bottom: 1px solid #f0f0f0; }}
        tr:hover {{ background: #f0f4ff; }}
        tr {{ transition: background 0.15s; }}
        .rank {{ font-weight: bold; color: #667eea; width: 30px; text-align: center; }}
        .name {{ min-width: 100px; }}
        .name .code {{ font-size: 11px; color: #b2bec3; margin-left: 4px; }}
        .score-main {{ font-weight: bold; color: #2d3436; }}
        .roe {{ color: #00b894; font-weight: 500; }}

        /* Tags */
        .tag {{
            display: inline-block; padding: 2px 10px; border-radius: 12px;
            font-size: 11px; font-weight: 500;
            transition: transform 0.2s;
        }}
        .tag:hover {{ transform: scale(1.05); }}
        .tag-\u63a8\u8350\u5173\u6ce8 {{ background: #00b894; color: white; }}
        .tag-\u53ef\u4ee5\u5173\u6ce8 {{ background: #00cec9; color: white; }}
        .tag-\u6301\u6709\u89c2\u671b {{ background: #fdcb6e; color: #2d3436; }}
        .tag-\u8c28\u614e\u89c2\u5bdf {{ background: #e17055; color: white; }}
        .tag-\u6ce8\u610f\u98ce\u9669 {{ background: #d63031; color: white; }}
        .tag-\u4e8f\u635f\u6682\u907f {{ background: #636e72; color: white; }}

        /* Charts */
        .charts-section h2 {{ margin-bottom: 16px; }}
        .charts-grid {{ display: flex; flex-wrap: wrap; gap: 16px; }}
        .chart-full {{ width: 100%; }}
        .chart-half {{ flex: 1; min-width: 300px; }}
        .charts-grid img {{
            width: 100%; border-radius: 8px; border: 1px solid #e9ecef;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            cursor: zoom-in;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .charts-grid img:hover {{
            transform: scale(1.01);
            box-shadow: 0 4px 16px rgba(0,0,0,0.12);
        }}

        /* Lightbox */
        .lightbox {{
            display: none; position: fixed; z-index: 9999;
            left: 0; top: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.9);
            cursor: zoom-out;
        }}
        .lightbox img {{
            max-width: 90%; max-height: 90%;
            margin: auto; position: absolute;
            top: 50%; left: 50%; transform: translate(-50%, -50%);
            border-radius: 8px;
        }}

        /* Footer */
        /* Stock Screener */
        .screener-section {{ margin-bottom: 24px; }}
        .screener-toolbar {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }}
        .screener-toolbar input, .screener-toolbar select {{
            padding: 8px 12px; border: 1px solid #e9ecef; border-radius: 8px;
            font-size: 13px; background: white; color: #2d3436;
            transition: border-color 0.2s;
        }}
        .screener-toolbar input:focus, .screener-toolbar select:focus {{
            outline: none; border-color: #667eea;
        }}
        .screener-toolbar input[type="text"] {{ flex: 1; min-width: 180px; }}
        .screener-toolbar input[type="number"] {{ width: 80px; }}
        .screener-toolbar label {{ font-size: 12px; color: #636e72; display: flex; align-items: center; gap: 4px; }}
        .screener-count {{ font-size: 13px; color: #636e72; margin-bottom: 12px; }}
        .screener-count strong {{ color: #667eea; }}
        .screener-table-wrap {{ max-height: 500px; overflow-y: auto; border: 1px solid #e9ecef; border-radius: 8px; }}
        .screener-table-wrap table {{ font-size: 13px; }}
        .screener-table-wrap th {{ position: sticky; top: 0; z-index: 1; }}
        .dark-mode .screener-toolbar input, .dark-mode .screener-toolbar select {{
            background: #3d3d56; color: #dfe6e9; border-color: #3d3d56;
        }}
        .dark-mode .screener-table-wrap {{ border-color: #3d3d56; }}
        .screener-quick {{
            display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px;
        }}
        .screener-quick button {{
            padding: 4px 12px; border: 1px solid #e9ecef; border-radius: 20px;
            background: white; color: #636e72; font-size: 12px; cursor: pointer;
            transition: all 0.2s;
        }}
        .screener-quick button:hover {{
            background: #667eea; color: white; border-color: #667eea;
        }}
        .screener-quick button.active {{
            background: #667eea; color: white; border-color: #667eea;
        }}
        .dark-mode .screener-quick button {{
            background: #3d3d56; color: #b2bec3; border-color: #3d3d56;
        }}
        .dark-mode .screener-quick button:hover {{
            background: #667eea; color: white;
        }}

        .footer {{
            text-align: center; padding: 20px; color: #b2bec3; font-size: 12px;
        }}
        .footer .info {{ margin-top: 8px; font-size: 11px; line-height: 1.7; }}

        /* Dark Mode */
        @media (prefers-color-scheme: dark) {{
            body.dark-mode, body:not(.light-mode) {{ background: #1a1b2e; color: #dfe6e9; }}
            body.dark-mode .section, body:not(.light-mode) .section,
            body.dark-mode .summary-card, body:not(.light-mode) .summary-card {{
                background: #2d2d44; color: #dfe6e9;
            }}
            body.dark-mode .section h2, body:not(.light-mode) .section h2 {{ color: #dfe6e9; }}
            body.dark-mode th, body:not(.light-mode) th {{
                background: #3d3d56; color: #b2bec3;
            }}
            body.dark-mode td, body:not(.light-mode) td {{ border-bottom-color: #3d3d56; }}
            body.dark-mode tr:hover, body:not(.light-mode) tr:hover {{ background: #3d3d56; }}
            body.dark-mode .summary-card .label,
            body:not(.light-mode) .summary-card .label {{ color: #b2bec3; }}
            body.dark-mode .name .code,
            body:not(.light-mode) .name .code {{ color: #636e72; }}
            body.dark-mode .score-main,
            body:not(.light-mode) .score-main {{ color: #dfe6e9; }}
        }}

        /* Explicit dark mode override */
        body.dark-mode {{ background: #1a1b2e; color: #dfe6e9; }}
        body.dark-mode .section,
        body.dark-mode .summary-card {{ background: #2d2d44; color: #dfe6e9; }}
        body.dark-mode .section h2 {{ color: #dfe6e9; }}
        body.dark-mode th {{ background: #3d3d56; color: #b2bec3; }}
        body.dark-mode td {{ border-bottom-color: #3d3d56; }}
        body.dark-mode tr:hover {{ background: #3d3d56; }}
        body.dark-mode .summary-card .label {{ color: #b2bec3; }}
        body.dark-mode .name .code {{ color: #636e72; }}
        body.dark-mode .score-main {{ color: #dfe6e9; }}

        /* Responsive */
        @media (max-width: 600px) {{
            .container {{ padding: 10px; }}
            .header {{ padding: 20px; }}
            .header h1 {{ font-size: 18px; }}
            .summary-card .num {{ font-size: 22px; }}
            table {{ font-size: 12px; }}
            td, th {{ padding: 6px 4px; }}
            .chart-half {{ min-width: 100%; }}
            .section {{ padding: 16px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <button class="theme-toggle" onclick="toggleDarkMode()" title="切换暗色模式">🌙</button>
        <div class="header">
            <h1>📈 中证500 每日复盘报告</h1>
            <div class="date">报告日期: {report_date}</div>
            <div class="sub">数据来源: baostock | 评分模型: 估值+基本面+量能+动量+资金流</div>
        </div>

        <!-- Summary -->
        <div class="summary">
            <div class="summary-card">
                <div class="num">{len(top_stocks)}</div>
                <div class="label">推荐关注</div>
            </div>
            <div class="summary-card">
                <div class="num">{f"{top_stocks[0]['total_score']:.1f}" if top_stocks else '0'}</div>
                <div class="label">最高评分</div>
            </div>
            <div class="summary-card">
                <div class="num">{top_stocks[0].get('stock_name', '-') if top_stocks else '-'}</div>
                <div class="label">冠军股票</div>
            </div>
            {_build_industry_distribution(top_stocks)}
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

        <!-- Stock Screener -->
        <div class="section screener-section">
            <h2>🔍 条件选股</h2>
            <div class="screener-toolbar">
                <input type="text" id="screener-search" placeholder="搜索股票名称或代码..." oninput="filterStocks()">
                <label>总分 <input type="number" id="screener-min" placeholder="最低" oninput="filterStocks()"></label>
                <label>~ <input type="number" id="screener-max" placeholder="最高" oninput="filterStocks()"></label>
                <select id="screener-action" onchange="filterStocks()">
                    <option value="">全部建议</option>
                    <option value="推荐关注">推荐关注</option>
                    <option value="可以关注">可以关注</option>
                    <option value="持有观望">持有观望</option>
                    <option value="谨慎观察">谨慎观察</option>
                    <option value="注意风险">注意风险</option>
                    <option value="亏损暂避">亏损暂避</option>
                </select>
            </div>
            <div class="screener-quick">
                <button onclick="quickFilter('top20')">Top 20</button>
                <button onclick="quickFilter('推荐关注')">推荐关注</button>
                <button onclick="quickFilter('注意风险')">注意风险</button>
                <button onclick="quickFilter('clear')">清除筛选</button>
            </div>
            <div class="screener-count" id="screener-count">共 <strong>0</strong> 只</div>
            <div class="screener-table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th onclick="sortScreener(0)">#</th>
                            <th onclick="sortScreener(1)">股票</th>
                            <th onclick="sortScreener(2)">总分</th>
                            <th onclick="sortScreener(3)">估值</th>
                            <th onclick="sortScreener(4)">基本面</th>
                            <th onclick="sortScreener(5)">量能</th>
                            <th onclick="sortScreener(6)">动量</th>
                            <th onclick="sortScreener(7)">ROE</th>
                            <th onclick="sortScreener(8)">建议</th>
                        </tr>
                    </thead>
                    <tbody id="screener-tbody"></tbody>
                </table>
            </div>
        </div>

        <!-- Full Report Text -->
        <div class="section">
            <h2>📝 完整报告</h2>
            <pre style="font-size:13px; color:#555; line-height:1.7; white-space:pre-wrap; font-family:inherit;">{report_text}</pre>
        </div>

        <div class="footer">
            自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · GitHub Actions
            <div class="info">
                📊 数据来源: baostock (日线行情+财务数据) ｜ akshare (成分股列表)<br>
                📈 评分模型: 估值(25%) + 基本面(25%) + 量能(25%) + 动量(15%) + 资金流(10%)<br>
                ⚠️ 本报告仅供参考，不构成投资建议
            </div>
        </div>
    </div>

    <!-- Lightbox -->
    <div class="lightbox" id="lightbox" onclick="this.style.display='none'">
        <img id="lightbox-img" src="" alt="放大查看">
    </div>

    <!-- 全量股票数据（条件选股用） -->
    <script id="stock-data" type="application/json">{all_stocks_json}</script>

    <script>
    // 暗色模式切换
    function toggleDarkMode() {{
        var body = document.body;
        body.classList.toggle('dark-mode');
        var btn = document.querySelector('.theme-toggle');
        btn.textContent = body.classList.contains('dark-mode') ? '☀️' : '🌙';
        localStorage.setItem('theme', body.classList.contains('dark-mode') ? 'dark' : 'light');
    }}
    // 恢复上次主题
    if (localStorage.getItem('theme') === 'dark') {{
        document.body.classList.add('dark-mode');
        document.querySelector('.theme-toggle').textContent = '☀️';
    }}

    // 图片点击放大 (Lightbox)
    document.addEventListener('click', function(e) {{
        var img = e.target.closest('.charts-grid img');
        if (img) {{
            document.getElementById('lightbox-img').src = img.src;
            document.getElementById('lightbox').style.display = 'block';
        }}
    }});

    // 表格排序
    document.addEventListener('DOMContentLoaded', function() {{
        document.querySelectorAll('table th').forEach(function(th, index) {{
            th.addEventListener('click', function() {{
                var table = th.closest('table');
                var tbody = table.querySelector('tbody');
                var rows = Array.from(tbody.querySelectorAll('tr'));
                var dir = th.classList.contains('sort-asc') ? -1 : 1;

                // 清除其他列的排序状态
                table.querySelectorAll('th').forEach(function(h) {{
                    h.classList.remove('sort-asc', 'sort-desc');
                }});

                rows.sort(function(a, b) {{
                    var aVal = a.children[index].textContent.trim();
                    var bVal = b.children[index].textContent.trim();
                    var aNum = parseFloat(aVal.replace(/[^0-9.-]/g, ''));
                    var bNum = parseFloat(bVal.replace(/[^0-9.-]/g, ''));
                    if (!isNaN(aNum) && !isNaN(bNum)) {{
                        return (aNum - bNum) * dir;
                    }}
                    return aVal.localeCompare(bVal) * dir;
                }});

                rows.forEach(function(row) {{ tbody.appendChild(row); }});
                th.classList.add(dir === 1 ? 'sort-asc' : 'sort-desc');
            }});
        }});
    }});
        
    // ========== 条件选股 (Stock Screener) ==========
    var screenerData = [];
    var screenerSortKey = 2;
    var screenerSortDesc = true;
        
    try {{
        var el = document.getElementById('stock-data');
        if (el) screenerData = JSON.parse(el.textContent);
    }} catch(e) {{ console.warn('Stock data parse error:', e); }}
        
    function filterStocks() {{
        var q = (document.getElementById('screener-search').value || '').toLowerCase();
        var min = parseFloat(document.getElementById('screener-min').value) || 0;
        var max = parseFloat(document.getElementById('screener-max').value) || 100;
        var act = document.getElementById('screener-action').value;
    
        var filtered = screenerData.filter(function(s) {{
            if (q && s.stock_name.toLowerCase().indexOf(q) === -1 && s.symbol.indexOf(q) === -1) return false;
            if (s.total_score !== null && (s.total_score < min || s.total_score > max)) return false;
            if (act && s.action !== act) return false;
            return true;
        }});
    
        // 排序
        var keys = [null, 'stock_name', 'total_score', 'valuation_score', 'fundamental_score', 'volume_score', 'momentum_score', 'roe', 'action'];
        var key = keys[screenerSortKey] || 'total_score';
        filtered.sort(function(a, b) {{
            var av = a[key], bv = b[key];
            if (av === null || av === undefined) av = screenerSortDesc ? -999999 : 999999;
            if (bv === null || bv === undefined) bv = screenerSortDesc ? -999999 : 999999;
            if (typeof av === 'string') {{
                return screenerSortDesc ? bv.localeCompare(av) : av.localeCompare(bv);
            }}
            return screenerSortDesc ? bv - av : av - bv;
        }});
    
        renderScreener(filtered);
    }}
    
    function renderScreener(data) {{
        var tbody = document.getElementById('screener-tbody');
        document.getElementById('screener-count').innerHTML = '共 <strong>' + data.length + '</strong> 只';
        if (data.length === 0) {{
            tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#b2bec3;padding:32px">没有符合筛选条件的股票</td></tr>';
            return;
        }}
        var h = '';
        for (var i = 0; i < data.length; i++) {{
            var s = data[i];
            var roeStr = '';
            if (s.roe !== null && s.roe !== undefined) {{
                roeStr = (s.roe * 100).toFixed(1) + '%';
            }}
            h += '<tr>' +
                '<td class="rank">' + (i + 1) + '</td>' +
                '<td class="name"><strong>' + s.stock_name + '</strong><span class="code">' + s.symbol + '</span></td>' +
                '<td><span class="score-main">' + (s.total_score !== null ? s.total_score.toFixed(1) : '-') + '</span></td>' +
                '<td>' + (s.valuation_score !== null ? s.valuation_score.toFixed(0) : '-') + '</td>' +
                '<td>' + (s.fundamental_score !== null ? s.fundamental_score.toFixed(0) : '-') + '</td>' +
                '<td>' + (s.volume_score !== null ? s.volume_score.toFixed(0) : '-') + '</td>' +
                '<td>' + (s.momentum_score !== null ? s.momentum_score.toFixed(0) : '-') + '</td>' +
                '<td class="roe">' + roeStr + '</td>' +
                '<td><span class="tag tag-' + s.action + '">' + s.action + '</span></td>' +
                '</tr>';
        }}
        tbody.innerHTML = h;
    }}
    
    function quickFilter(type) {{
        if (type === 'clear') {{
            document.getElementById('screener-search').value = '';
            document.getElementById('screener-min').value = '';
            document.getElementById('screener-max').value = '';
            document.getElementById('screener-action').value = '';
            filterStocks();
            return;
        }}
        if (type === 'top20') {{
            document.getElementById('screener-search').value = '';
            document.getElementById('screener-min').value = '';
            document.getElementById('screener-max').value = '';
            document.getElementById('screener-action').value = '';
            var sorted = [].concat(screenerData).sort(function(a,b){{return b.total_score - a.total_score}}).slice(0, 20);
            renderScreener(sorted);
            return;
        }}
        document.getElementById('screener-action').value = type;
        document.getElementById('screener-search').value = '';
        filterStocks();
    }}
    
    function sortScreener(col) {{
        if (col === screenerSortKey) screenerSortDesc = !screenerSortDesc;
        else {{ screenerSortKey = col; screenerSortDesc = true; }}
        filterStocks();
    }}
    
    // 初始渲染
    if (screenerData.length > 0) {{
        var top20 = [].concat(screenerData).sort(function(a,b){{return b.total_score - a.total_score}}).slice(0, 20);
        renderScreener(top20);
    }}
    </script>
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
