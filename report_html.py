"""
HTML 报告生成模块
生成美观的 HTML 页面，内嵌图表，发布到 GitHub Pages
"""
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from config import REPORT_CONFIG




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
    top_stocks: list,
    report_date: str = None,
    output_path: str = None,
    all_stocks: list = None,
    price_history: dict = None,
) -> str:
    """生成 HTML 报告页面"""
    if report_date is None:
        report_date = datetime.now().strftime("%Y-%m-%d")

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

    # 历史分位数计算
    percentiles_json = "{}"
    if all_stocks:
        try:
            pdf = pd.DataFrame(all_stocks)
            percentiles = {}
            for factor in ['valuation_score','fundamental_score','volume_score','momentum_score','capital_flow_score']:
                if factor in pdf.columns:
                    ranks = pdf[factor].rank(pct=True)
                    for i, symbol in enumerate(pdf['symbol']):
                        if symbol not in percentiles:
                            percentiles[symbol] = {}
                        percentiles[symbol][factor] = round(float(ranks.iloc[i]), 3)
            percentiles_json = json.dumps(percentiles, ensure_ascii=False)
        except Exception as e:
            print(f"  [WARN] 分位数计算失败: {e}")

    # 股价历史数据
    price_history_json = "{}"
    if price_history:
        try:
            price_history_json = json.dumps(price_history, ensure_ascii=False)
        except Exception as e:
            print(f"  [WARN] 股价历史序列化失败: {e}")

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>中证500 股票分析 — {report_date}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, "Microsoft YaHei", "PingFang SC", sans-serif;
            background: linear-gradient(135deg, #f0f2f5 0%, #e8ecf1 100%);
            color: #2d3436;
            line-height: 1.6;
            transition: background 0.4s, color 0.3s;
            min-height: 100vh;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}

        /* Header */
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border-radius: 16px; padding: 32px;
            margin-bottom: 24px; text-align: center;
            box-shadow: 0 8px 32px rgba(102,126,234,0.3);
        }}
        .header h1 {{ font-size: 24px; margin-bottom: 6px; }}
        .header .date {{ font-size: 14px; opacity: 0.85; }}
        .header .sub {{ font-size: 12px; opacity: 0.7; margin-top: 4px; }}

        /* Theme Toggle */
        .theme-toggle {{
            position: fixed; top: 16px; right: 16px; z-index: 999;
            background: rgba(255,255,255,0.2); backdrop-filter: blur(8px);
            border: 1px solid rgba(255,255,255,0.3);
            color: white; width: 40px; height: 40px; border-radius: 50%;
            cursor: pointer; font-size: 18px; transition: all 0.3s;
        }}
        .theme-toggle:hover {{ background: rgba(255,255,255,0.3); transform: scale(1.1); }}

        /* Summary Cards */
        .summary {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
        .summary-card {{
            flex: 1; min-width: 120px;
            background: white; border-radius: 12px; padding: 18px 16px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.06); text-align: center;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .summary-card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.1); }}
        .summary-card .num {{ font-size: 28px; font-weight: bold; color: #667eea; }}
        .summary-card .label {{ font-size: 13px; color: #636e72; margin-top: 4px; }}

        /* Section */
        .section {{
            background: white; border-radius: 12px; padding: 24px;
            margin-bottom: 24px; box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        }}
        .section h2 {{ font-size: 18px; margin-bottom: 16px; color: #2d3436; }}

        /* Search Section */
        .search-section {{
            background: white; border-radius: 16px; padding: 24px;
            margin-bottom: 20px; box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        }}
        .search-bar {{
            display: flex; gap: 12px; margin-bottom: 16px;
        }}
        .search-bar input {{
            flex: 1; padding: 14px 20px; font-size: 16px;
            border: 2px solid #e9ecef; border-radius: 12px;
            outline: none; transition: border-color 0.2s;
            background: #f8f9fa; color: #2d3436;
        }}
        .search-bar input:focus {{ border-color: #667eea; background: white; }}
        .search-bar button {{
            padding: 14px 28px; font-size: 15px; font-weight: 600;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white; border: none; border-radius: 12px;
            cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;
            white-space: nowrap;
        }}
        .search-bar button:hover {{ transform: translateY(-1px); box-shadow: 0 4px 12px rgba(102,126,234,0.4); }}

        /* Filter Row */
        .filter-row {{
            display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
        }}
        .filter-row input, .filter-row select {{
            padding: 8px 12px; border: 1px solid #e9ecef; border-radius: 8px;
            font-size: 13px; background: white; color: #2d3436;
            transition: border-color 0.2s;
        }}
        .filter-row input:focus, .filter-row select:focus {{ outline: none; border-color: #667eea; }}
        .filter-row input[type="number"] {{ width: 80px; }}
        .filter-row label {{ font-size: 12px; color: #636e72; display: flex; align-items: center; gap: 4px; }}

        /* Quick Filter Buttons */
        .quick-btns {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }}
        .quick-btns button {{
            padding: 6px 16px; border: 1px solid #e9ecef; border-radius: 20px;
            background: white; color: #636e72; font-size: 12px; cursor: pointer;
            transition: all 0.2s;
        }}
        .quick-btns button:hover {{
            background: #667eea; color: white; border-color: #667eea;
        }}
        .quick-btns button.active {{
            background: #667eea; color: white; border-color: #667eea;
            box-shadow: 0 2px 8px rgba(102,126,234,0.3);
        }}

        .result-count {{ font-size: 13px; color: #636e72; margin: 8px 0; }}
        .result-count strong {{ color: #667eea; }}

        /* Stock Grid */
        .stock-grid {{
            display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
            gap: 14px; margin-bottom: 24px;
        }}
        .stock-card {{
            background: white; border-radius: 14px; padding: 18px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.04);
            cursor: pointer; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 2px solid transparent;
            animation: cardIn 0.4s ease both;
        }}
        @keyframes cardIn {{
            from {{ opacity: 0; transform: translateY(20px) scale(0.95); }}
            to {{ opacity: 1; transform: translateY(0) scale(1); }}
        }}
        .stock-card:nth-child(1) {{ animation-delay: 0.02s; }}
        .stock-card:nth-child(2) {{ animation-delay: 0.04s; }}
        .stock-card:nth-child(3) {{ animation-delay: 0.06s; }}
        .stock-card:nth-child(4) {{ animation-delay: 0.08s; }}
        .stock-card:nth-child(5) {{ animation-delay: 0.10s; }}
        .stock-card:nth-child(6) {{ animation-delay: 0.12s; }}
        .stock-card:nth-child(7) {{ animation-delay: 0.14s; }}
        .stock-card:nth-child(8) {{ animation-delay: 0.16s; }}
        .stock-card:nth-child(9) {{ animation-delay: 0.18s; }}
        .stock-card:nth-child(10) {{ animation-delay: 0.20s; }}
        .stock-card:nth-child(11) {{ animation-delay: 0.22s; }}
        .stock-card:nth-child(12) {{ animation-delay: 0.24s; }}
        .stock-card:nth-child(13) {{ animation-delay: 0.26s; }}
        .stock-card:nth-child(14) {{ animation-delay: 0.28s; }}
        .stock-card:nth-child(15) {{ animation-delay: 0.30s; }}
        .stock-card:nth-child(16) {{ animation-delay: 0.32s; }}
        .stock-card:nth-child(17) {{ animation-delay: 0.34s; }}
        .stock-card:nth-child(18) {{ animation-delay: 0.36s; }}
        .stock-card:nth-child(19) {{ animation-delay: 0.38s; }}
        .stock-card:nth-child(20) {{ animation-delay: 0.40s; }}
        .stock-card:hover {{
            transform: translateY(-6px);
            box-shadow: 0 16px 32px rgba(102,126,234,0.15);
            border-color: #667eea;
        }}
        .stock-card .card-header {{
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 10px;
        }}
        .stock-card .card-name {{ font-size: 16px; font-weight: 600; color: #2d3436; }}
        .stock-card .card-code {{ font-size: 12px; color: #b2bec3; margin-left: 6px; }}
        .stock-card .card-score {{
            font-size: 22px; font-weight: bold; color: #667eea;
        }}
        .stock-card .card-factors {{
            display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0;
        }}
        .stock-card .card-factors span {{
            font-size: 11px; padding: 2px 8px; border-radius: 6px;
            background: #f0f2f5; color: #636e72;
        }}
        .stock-card .tag {{
            display: inline-block; padding: 3px 12px; border-radius: 12px;
            font-size: 11px; font-weight: 500;
        }}

        /* Detail Panel */
        .detail-panel {{
            background: white; border-radius: 16px; padding: 28px;
            margin-bottom: 24px; box-shadow: 0 8px 32px rgba(0,0,0,0.08);
            animation: slideIn 0.3s ease;
        }}
        @keyframes slideIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}

        .back-btn {{
            padding: 8px 20px; border: 1px solid #e9ecef; border-radius: 8px;
            background: white; color: #636e72; font-size: 13px; cursor: pointer;
            margin-bottom: 20px; transition: all 0.2s;
        }}
        .back-btn:hover {{ background: #f8f9fa; border-color: #667eea; color: #667eea; }}

        .detail-header {{
            display: flex; justify-content: space-between; align-items: center;
            flex-wrap: wrap; margin-bottom: 24px;
            padding-bottom: 20px; border-bottom: 1px solid #f0f0f0;
        }}
        .detail-header .dh-left {{ display: flex; align-items: baseline; gap: 12px; }}
        .detail-header .dh-name {{ font-size: 26px; font-weight: 700; color: #2d3436; }}
        .detail-header .dh-code {{ font-size: 15px; color: #b2bec3; }}
        .detail-header .dh-score {{ font-size: 36px; font-weight: 800; color: #667eea; }}
        .detail-header .dh-meta {{ font-size: 13px; color: #636e72; }}

        /* Chart Row */
        .chart-row {{ display: flex; gap: 20px; flex-wrap: wrap; }}
        .chart-box {{
            flex: 1; min-width: 300px; padding: 16px;
            background: #f8f9fa; border-radius: 12px;
        }}
        .chart-box h3 {{ font-size: 14px; color: #636e72; margin-bottom: 12px; }}
        .chart-box canvas {{ width: 100%; height: auto; }}

        /* Footer */
        .footer {{
            text-align: center; padding: 20px; color: #b2bec3; font-size: 12px;
        }}
        .footer .info {{ margin-top: 8px; font-size: 11px; line-height: 1.7; }}

        /* Tags */
        .tag-推荐关注 {{ background: #00b894; color: white; }}
        .tag-可以关注 {{ background: #00cec9; color: white; }}
        .tag-持有观望 {{ background: #fdcb6e; color: #2d3436; }}
        .tag-谨慎观察 {{ background: #e17055; color: white; }}
        .tag-注意风险 {{ background: #d63031; color: white; }}
        .tag-亏损暂避 {{ background: #636e72; color: white; }}

        /* Dark Mode */
        @media (prefers-color-scheme: dark) {{
            body.dark-mode, body:not(.light-mode) {{ background: #1a1b2e; color: #dfe6e9; }}
            body.dark-mode .section, body:not(.light-mode) .section,
            body.dark-mode .summary-card, body:not(.light-mode) .summary-card,
            body.dark-mode .search-section, body:not(.light-mode) .search-section,
            body.dark-mode .stock-card, body:not(.light-mode) .stock-card,
            body.dark-mode .detail-panel, body:not(.light-mode) .detail-panel {{
                background: #2d2d44; color: #dfe6e9;
            }}
            body.dark-mode .section h2, body:not(.light-mode) .section h2 {{ color: #dfe6e9; }}
            body.dark-mode .search-bar input {{
                background: #3d3d56; color: #dfe6e9; border-color: #3d3d56;
            }}
            body.dark-mode .search-bar input:focus {{ border-color: #667eea; }}
            body.dark-mode .filter-row input, body.dark-mode .filter-row select {{
                background: #3d3d56; color: #dfe6e9; border-color: #3d3d56;
            }}
            body.dark-mode .quick-btns button {{
                background: #3d3d56; color: #b2bec3; border-color: #3d3d56;
            }}
            body.dark-mode .quick-btns button:hover {{ background: #667eea; color: white; }}
            body.dark-mode .stock-card .card-factors span {{
                background: #3d3d56; color: #b2bec3;
            }}
            body.dark-mode .stock-card .card-name {{ color: #dfe6e9; }}
            body.dark-mode .chart-box {{ background: #3d3d56; }}
            body.dark-mode .summary-card .label {{ color: #b2bec3; }}
            body.dark-mode .back-btn {{ background: #3d3d56; color: #b2bec3; border-color: #3d3d56; }}
            body.dark-mode .back-btn:hover {{ border-color: #667eea; }}
            body.dark-mode .analysis-table .alabel {{ color: #dfe6e9; }}
            body.dark-mode .analysis-table .avalue {{ color: #dfe6e9; }}
            body.dark-mode .analysis-table .apctile {{ color: #b2bec3; }}
            body.dark-mode .analysis-table .ainsight {{ color: #b2bec3; }}
            body.dark-mode .analysis-table .abar-track {{ background: #3d3d56; }}
            body.dark-mode .detail-sub {{ color: #b2bec3; border-bottom-color: #3d3d56; }}
        }}

        /* Explicit dark mode */
        body.dark-mode {{ background: #1a1b2e; color: #dfe6e9; }}
        body.dark-mode .section, body.dark-mode .summary-card,
        body.dark-mode .search-section, body.dark-mode .stock-card,
        body.dark-mode .detail-panel {{ background: #2d2d44; color: #dfe6e9; }}
        body.dark-mode .section h2 {{ color: #dfe6e9; }}

        /* Analysis Table */
        .analysis-table {{ width: 100%; border-collapse: separate; border-spacing: 0 6px; }}
        .analysis-table td {{ padding: 4px 8px; vertical-align: middle; }}
        .analysis-table .alabel {{ font-size: 13px; font-weight: 600; color: #2d3436; white-space: nowrap; width: 48px; }}
        .analysis-table .abar {{ position: relative; width: 100%; }}
        .analysis-table .abar-track {{
            height: 20px; background: #f0f2f5; border-radius: 10px; overflow: hidden; position: relative;
        }}
        .analysis-table .abar-fill {{
            height: 100%; border-radius: 10px; transition: width 1s ease;
            display: flex; align-items: center; justify-content: flex-end;
            padding-right: 6px; font-size: 10px; color: white; font-weight: 700;
            min-width: 24px;
        }}
        .analysis-table .avalue {{ font-size: 14px; font-weight: 700; color: #2d3436; width: 32px; text-align: center; }}
        .analysis-table .apctile {{ font-size: 12px; color: #636e72; width: 36px; text-align: center; }}
        .analysis-table .ainsight {{ font-size: 11px; color: #636e72; padding-left: 8px; min-width: 56px; }}
        .ainsight-badge {{ display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 11px; font-weight: 600; }}
        .ainsight-badge.excellent {{ background: #00b894; color: white; }}
        .ainsight-badge.good {{ background: #0984e3; color: white; }}
        .ainsight-badge.average {{ background: #fdcb6e; color: #2d3436; }}
        .ainsight-badge.poor {{ background: #e17055; color: white; }}
        .ainsight-badge.bad {{ background: #d63031; color: white; }}

        /* Detail Sub-header */
        .detail-sub {{ font-size: 13px; color: #636e72; margin: 20px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #f0f0f0; }}
        .detail-sub span {{ font-weight: 600; }}

        @media (max-width: 600px) {{
            .container {{ padding: 10px; }}
            .header {{ padding: 20px; }}
            .header h1 {{ font-size: 18px; }}
            .summary-card .num {{ font-size: 22px; }}
            .stock-grid {{ grid-template-columns: 1fr; }}
            .chart-box {{ min-width: 100%; }}
            .search-bar {{ flex-direction: column; }}
            .detail-header {{ flex-direction: column; align-items: flex-start; gap: 8px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
    <!-- Header -->
    <button class="theme-toggle" onclick="toggleDarkMode()" title="切换暗色模式">🌙</button>
    <div class="header">
        <h1>📈 中证500 多因子分析</h1>
        <div class="date">报告日期: {report_date}</div>
        <div class="sub">数据来源: baostock | 评分模型: 估值+基本面+量能+动量+资金流</div>
    </div>

    <!-- Summary -->
    <div class="summary">
        <div class="summary-card"><div class="num">{len(all_stocks)}</div><div class="label">覆盖股票</div></div>
        <div class="summary-card"><div class="num">{f"{top_stocks[0]['total_score']:.1f}" if top_stocks else '0'}</div><div class="label">最高评分</div></div>
        <div class="summary-card"><div class="num">{top_stocks[0].get('stock_name', '-') if top_stocks else '-'}</div><div class="label">冠军股票</div></div>
        {_build_industry_distribution(top_stocks)}
    </div>

    <!-- Search + Stock Cards -->
    <div class="search-section">
        <div class="search-bar">
            <input type="text" id="stockSearch" placeholder="输入股票名称或代码搜索..." onkeydown="if(event.key==='Enter') searchStock()">
            <button onclick="searchStock()">🔍 搜索</button>
        </div>
        <div class="quick-btns">
            <button data-type="all" onclick="quickFilter('all')">📋 全部</button>
            <button data-type="推荐关注" onclick="quickFilter('推荐关注')">⭐ 推荐关注</button>
            <button data-type="注意风险" onclick="quickFilter('注意风险')">⚠️ 风险</button>
            <button data-type="top20" onclick="quickFilter('top20')">🏆 Top20</button>
        </div>
        <div class="result-count">共 <strong id="stockCount">0</strong> 只股票</div>
        <div class="stock-grid" id="stockGrid"></div>
    </div>

    <!-- Detail Panel -->
    <div class="detail-panel" id="detailPanel" style="display:none">
        <button class="back-btn" onclick="hideDetail()">← 返回列表</button>
        <div class="detail-header">
            <div class="dh-left">
                <span class="dh-name" id="dName"></span>
                <span class="dh-code" id="dCode"></span>
                <span id="dTag" style="display:none"></span>
            </div>
            <div><span class="dh-score" id="dScore"></span> <span class="dh-meta">综合评分</span></div>
        </div>
        <div class="chart-row">
            <div class="chart-box"><h3>📊 多因子雷达</h3><canvas id="radarChart" width="360" height="300"></canvas></div>
            <div class="chart-box"><h3>📈 长期股价走势</h3><canvas id="priceChart" width="400" height="260"></canvas></div>
        </div>
        <div class="detail-sub">📋 <span>因子分析</span> · 评分 vs 全市场分位</div>
        <table class="analysis-table" id="analysisTable"></table>
    </div>

    <div class="footer">
        自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · 数据驱动决策
        <div class="info">
            📊 数据来源: baostock (日线行情+财务数据) | akshare (成分股列表)<br>
            📈 评分模型: 估值(25%) + 基本面(25%) + 量能(25%) + 动量(15%) + 资金流(10%)<br>
            ⚠️ 本报告仅供参考，不构成投资建议
        </div>
    </div>
</div>

<script id="stock-data" type="application/json">{all_stocks_json}</script>
<script id="price-history-data" type="application/json">{price_history_json}</script>
<script id="percentiles-data" type="application/json">{percentiles_json}</script>

<script>
var allStocks = [];
var priceHistory = {{}};
var percentiles = {{}};
try {{ allStocks = JSON.parse(document.getElementById('stock-data').textContent); }} catch(e) {{}}
try {{ priceHistory = JSON.parse(document.getElementById('price-history-data').textContent); }} catch(e) {{}}
try {{ percentiles = JSON.parse(document.getElementById('percentiles-data').textContent); }} catch(e) {{}}

var FACTORS = ['valuation_score','fundamental_score','volume_score','momentum_score','capital_flow_score'];
var FACTOR_LABELS = ['估值','基本面','量能','动量','资金流'];
var FACTOR_COLORS = ['#6c5ce7','#00b894','#0984e3','#fdcb6e','#e17055'];

function toggleDarkMode() {{
  document.body.classList.toggle('dark-mode');
  document.querySelector('.theme-toggle').textContent = document.body.classList.contains('dark-mode') ? '☀️' : '🌙';
  localStorage.setItem('theme', document.body.classList.contains('dark-mode') ? 'dark' : 'light');
}}
  var t = localStorage.getItem('theme');
if (t === 'dark') {{ document.body.classList.add('dark-mode'); document.querySelector('.theme-toggle').textContent = '☀️'; }}

function renderCards(data) {{
  var grid = document.getElementById('stockGrid');
  document.getElementById('stockCount').textContent = data.length;
  if (!data.length) {{
    grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:48px;color:#b2bec3;">没有匹配的股票</div>';
    return;
  }}
  var h = '';
  for (var i = 0; i < data.length; i++) {{
    var s = data[i];
    var score = s.total_score !== null ? s.total_score.toFixed(1) : '-';
    var tag = s.action || '';
    h += '<div class="stock-card" onclick="showDetail(\'' + s.symbol + '\')">' +
      '<div class="card-header">' +
        '<div><span class="card-name">' + s.stock_name + '</span><span class="card-code">' + s.symbol + '</span></div>' +
        '<div class="card-score">' + score + '</div>' +
      '</div>' +
      '<div class="card-factors">' +
        '<span>估' + (s.valuation_score !== null ? s.valuation_score.toFixed(0) : '-') + '</span>' +
        '<span>基' + (s.fundamental_score !== null ? s.fundamental_score.toFixed(0) : '-') + '</span>' +
        '<span>量' + (s.volume_score !== null ? s.volume_score.toFixed(0) : '-') + '</span>' +
        '<span>动' + (s.momentum_score !== null ? s.momentum_score.toFixed(0) : '-') + '</span>' +
        '<span>资' + (s.capital_flow_score !== null ? s.capital_flow_score.toFixed(0) : '-') + '</span>' +
      '</div>' +
      (tag ? '<span class="tag tag-' + tag + '">' + tag + '</span>' : '') +
    '</div>';
  }}
  grid.innerHTML = h;
}}

function searchStock() {{
  var q = document.getElementById('stockSearch').value.trim().toLowerCase();
  if (!q) {{ renderCards(allStocks); return; }}
  renderCards(allStocks.filter(function(s) {{
    return s.stock_name.toLowerCase().indexOf(q) !== -1 || s.symbol.indexOf(q) !== -1;
  }}));
}}

function quickFilter(type) {{
  document.getElementById('stockSearch').value = '';
  var btns = document.querySelectorAll('.quick-btns button');
  for (var i = 0; i < btns.length; i++) btns[i].classList.remove('active');
  var activeBtn = document.querySelector('.quick-btns button[data-type="' + type + '"]');
  if (activeBtn) activeBtn.classList.add('active');
  if (type === 'all') renderCards(allStocks);
  else if (type === 'top20') {{
    var sorted = [].concat(allStocks).sort(function(a,b){{return b.total_score-a.total_score}}).slice(0,20);
    renderCards(sorted);
  }} else renderCards(allStocks.filter(function(s){{return s.action===type}}));
}}

function hideDetail() {{ document.getElementById('detailPanel').style.display = 'none'; }}

function _getInsight(score) {{
  if (score >= 80) return {{ text: '优秀', cls: 'excellent' }};
  if (score >= 60) return {{ text: '良好', cls: 'good' }};
  if (score >= 40) return {{ text: '一般', cls: 'average' }};
  if (score >= 20) return {{ text: '较差', cls: 'poor' }};
  return {{ text: '很差', cls: 'bad' }};
}}

function showDetail(symbol) {{
  var s = allStocks.find(function(x){{return x.symbol===symbol}});
  if (!s) return;
  document.getElementById('dName').textContent = s.stock_name;
  document.getElementById('dCode').textContent = s.symbol;
  document.getElementById('dScore').textContent = s.total_score !== null ? s.total_score.toFixed(1) : '-';
  var tag = s.action || '';
  var dTag = document.getElementById('dTag');
  if (tag) {{ dTag.textContent = tag; dTag.style.display = 'inline-block'; dTag.className = 'tag tag-' + tag; }}
  else {{ dTag.style.display = 'none'; }}

  // Build unified analysis table
  var tbl = document.getElementById('analysisTable');
  tbl.innerHTML = '';
  var rows = '';
  for (var i = 0; i < FACTORS.length; i++) {{
    var score = s[FACTORS[i]];
    score = score !== null && score !== undefined ? score : 0;
    var pct = (percentiles[symbol] || {{}})[FACTORS[i]];
    pct = pct !== undefined ? (pct * 100) : 0;
    var insight = _getInsight(Math.round(score));
    rows += '<tr>' +
      '<td class="alabel" style="color:' + FACTOR_COLORS[i] + '">' + FACTOR_LABELS[i] + '</td>' +
      '<td class="abar"><div class="abar-track"><div class="abar-fill" style="width:' + score + '%;background:' + FACTOR_COLORS[i] + '">' + Math.round(score) + '</div></div></td>' +
      '<td class="avalue">' + Math.round(score) + '</td>' +
      '<td class="apctile">' + Math.round(pct) + '%</td>' +
      '<td class="abar"><div class="abar-track"><div class="abar-fill" style="width:' + pct + '%;background:' + FACTOR_COLORS[i] + ';opacity:0.5"></div></div></td>' +
      '<td class="ainsight"><span class="ainsight-badge ' + insight.cls + '">' + insight.text + '</span></td>' +
      '</tr>';
  }}
  tbl.innerHTML = rows;

  drawRadar(s);
  drawPriceChart(symbol);
  document.getElementById('detailPanel').style.display = 'block';
  document.getElementById('detailPanel').scrollIntoView({{behavior:'smooth', block:'start'}});
}}

function drawRadar(stock) {{
  var c = document.getElementById('radarChart');
  var ctx = c.getContext('2d');
  var W = c.width, H = c.height, cx = W/2, cy = H/2 - 8, R = Math.min(W,H)/2 - 45;
  ctx.clearRect(0,0,W,H);
  // Draw background grid rings with scale labels
  ctx.font = '9px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  for (var r = 0.2; r <= 1; r += 0.2) {{
    ctx.beginPath();
    for (var i = 0; i <= FACTORS.length; i++) {{
      var a = Math.PI*2*i/FACTORS.length - Math.PI/2;
      var x = cx + R*r*Math.cos(a), y = cy + R*r*Math.sin(a);
      i===0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
    }}
    ctx.closePath(); ctx.strokeStyle = '#e0e4ea'; ctx.lineWidth = 0.5; ctx.stroke();
    // Scale label at top axis
    var lx = cx, ly = cy - R*r;
    ctx.fillStyle = '#b2bec3'; ctx.fillText(Math.round(r*100), lx, ly);
  }}
  // Draw axis lines
  for (var i = 0; i < FACTORS.length; i++) {{
    var a = Math.PI*2*i/FACTORS.length - Math.PI/2;
    ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(cx+R*Math.cos(a), cy+R*Math.sin(a));
    ctx.strokeStyle = '#e0e4ea'; ctx.lineWidth = 0.5; ctx.stroke();
    var lx = cx+(R+22)*Math.cos(a), ly = cy+(R+22)*Math.sin(a);
    ctx.fillStyle = '#636e72'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(FACTOR_LABELS[i], lx, ly);
  }}
  // Draw data polygon
  ctx.beginPath();
  for (var i = 0; i <= FACTORS.length; i++) {{
    var idx = i % FACTORS.length;
    var v = stock[FACTORS[idx]];
    v = v !== null && v !== undefined ? v/100 : 0;
    var a = Math.PI*2*idx/FACTORS.length - Math.PI/2;
    var x = cx + R*v*Math.cos(a), y = cy + R*v*Math.sin(a);
    i===0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
  }}
  ctx.closePath(); ctx.fillStyle = 'rgba(108,92,231,0.12)'; ctx.fill();
  ctx.strokeStyle = '#6c5ce7'; ctx.lineWidth = 2; ctx.stroke();
  // Draw data points with value labels
  ctx.font = 'bold 10px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  for (var i = 0; i < FACTORS.length; i++) {{
    var v = stock[FACTORS[i]];
    v = v !== null && v !== undefined ? v/100 : 0;
    var a = Math.PI*2*i/FACTORS.length - Math.PI/2;
    var px = cx + R*v*Math.cos(a), py = cy + R*v*Math.sin(a);
    ctx.beginPath(); ctx.arc(px, py, 4, 0, Math.PI*2);
    ctx.fillStyle = '#6c5ce7'; ctx.fill();
    ctx.strokeStyle = 'white'; ctx.lineWidth = 2; ctx.stroke();
    // Value label offset outward from point
    var off = 14;
    var lx = px + off*Math.cos(a), ly = py + off*Math.sin(a);
    ctx.fillStyle = document.body.classList.contains('dark-mode') ? '#dfe6e9' : '#2d3436';
    ctx.font = 'bold 11px sans-serif';
    ctx.fillText(Math.round(stock[FACTORS[i]]), lx, ly);
  }}
}}

function drawPriceChart(symbol) {{
  var c = document.getElementById('priceChart');
  var ctx = c.getContext('2d');
  var W = c.width, H = c.height, pt = 28, pr = 18, pb = 36, pl = 56;
  var cw = W-pl-pr, ch = H-pt-pb;
  ctx.clearRect(0,0,W,H);
  var data = priceHistory[symbol] || [];
  if (data.length < 2) {{
    ctx.fillStyle = '#b2bec3'; ctx.font = '14px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('暂无长期数据', W/2, H/2); return;
  }}
  var prices = data.map(function(d){{return d.close}});
  var mn = Math.min.apply(null, prices), mx = Math.max.apply(null, prices), rg = mx-mn || 1;
  // Draw Y-axis grid + price labels
  ctx.font = '10px sans-serif'; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
  ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.font = '10px sans-serif';
  for (var i = 0; i <= 4; i++) {{
    var y = pt + ch*i/4;
    var price = mx - rg*i/4;
    ctx.beginPath(); ctx.moveTo(pl,y); ctx.lineTo(W-pr,y);
    ctx.strokeStyle = '#eef0f4'; ctx.lineWidth = 0.5; ctx.stroke();
    ctx.fillStyle = '#b2bec3'; ctx.fillText(price.toFixed(1), pl-6, y);
  }}
  // Price line
  ctx.beginPath();
  for (var i = 0; i < data.length; i++) {{
    var x = pl + cw*i/(data.length-1), y = pt + ch*(1-(data[i].close-mn)/rg);
    i===0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
  }}
  ctx.strokeStyle = '#0984e3'; ctx.lineWidth = 2; ctx.stroke();
  // Gradient fill
  var grad = ctx.createLinearGradient(0,pt,0,pt+ch);
  grad.addColorStop(0, 'rgba(9,132,227,0.10)'); grad.addColorStop(1, 'rgba(9,132,227,0.01)');
  ctx.lineTo(pl+cw, pt+ch); ctx.lineTo(pl, pt+ch); ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
  // Annotate high/low points
  var maxIdx = 0, minIdx = 0;
  for (var i = 0; i < prices.length; i++) {{
    if (prices[i] > prices[maxIdx]) maxIdx = i;
    if (prices[i] < prices[minIdx]) minIdx = i;
  }}
  var annotatePoint = function(idx, color, label, arrow) {{
    var x = pl + cw*idx/(data.length-1), y = pt + ch*(1-(prices[idx]-mn)/rg);
    ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI*2);
    ctx.fillStyle = color; ctx.fill(); ctx.strokeStyle = 'white'; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = color; ctx.font = 'bold 10px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(label + ' ' + prices[idx].toFixed(1) + arrow, x, y-12);
  }}
  annotatePoint(maxIdx, '#d63031', '高', '↗');
  annotatePoint(minIdx, '#00b894', '低', '↘');
  // X-axis date labels (show ~5 evenly spaced dates)
  ctx.fillStyle = '#b2bec3'; ctx.font = '9px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  var steps = Math.min(5, data.length);
  var interval = Math.max(1, Math.floor((data.length-1)/(steps-1)));
  for (var i = 0; i < data.length; i += interval) {{
    var x = pl + cw*i/(data.length-1);
    var dateStr = data[i].date.slice(0,7);
    ctx.fillText(dateStr, x, H-14);
  }}
  // Last date label
  ctx.fillText(data[data.length-1].date.slice(0,7), W-pr, H-14);
}}

if (allStocks.length > 0) {{
  var top20 = [].concat(allStocks).sort(function(a,b){{return b.total_score-a.total_score}}).slice(0,20);
  renderCards(top20);
}}
</script>
</body>
</html>'''

    # 保存
    output_dir = REPORT_CONFIG["output_dir"]
    output_dir.mkdir(exist_ok=True)
    if output_path is None:
        output_path = str(output_dir / "report.html")

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"  [OK] HTML 报告已生成: {output_path}")
    return output_path
