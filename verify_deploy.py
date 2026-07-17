import requests, re
from datetime import datetime

TOKEN = 'TOKEN_REMOVED'
headers = {'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/vnd.github+json'}

r = requests.get('https://api.github.com/repos/rerealnico/csi500-daily-report/actions/runs?per_page=1', headers=headers, timeout=15)
run = r.json()['workflow_runs'][0]
c = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
u = datetime.fromisoformat(run['updated_at'].replace('Z', '+00:00'))
print(f'Status: {run["status"]}')
print(f'Conclusion: {run.get("conclusion", "")}')
print(f'Duration: {(u-c).total_seconds()/60:.0f} min')

r2 = requests.get('https://rerealnico.github.io/csi500-daily-report/report.html', timeout=30)
html = r2.text
m = re.search(r'<title>(.*?)</title>', html)
print(f'Title: {m.group(1)}')
print(f'Has screener: {"screener-section" in html}')
print(f'Has stock-data: {"id=\"stock-data\"" in html}')
