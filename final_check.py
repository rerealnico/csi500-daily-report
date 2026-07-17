import requests, re

TOKEN = 'TOKEN_REMOVED'
OWNER = 'rerealnico'
REPO = 'csi500-daily-report'
headers = {'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/vnd.github+json'}

# 1. 检查最新运行
r = requests.get(f'https://api.github.com/repos/{OWNER}/{REPO}/actions/runs?per_page=3', headers=headers, timeout=15)
runs = r.json().get('workflow_runs', [])
for run in runs[:3]:
    created = run['created_at'][:19]
    status = run['status']
    conclusion = run.get('conclusion', '')
    name = run['name']
    event = run['event']
    print(f'{created} | {status:12s} | {str(conclusion):10s} | {event:12s} | {name}')

# 2. 检查报告
r2 = requests.get('https://rerealnico.github.io/csi500-daily-report/report.html', timeout=30)
print(f'\n报告: HTTP {r2.status_code}, {len(r2.content)} bytes')
m = re.search(r'20\d{2}-\d{2}-\d{2}', r2.text[:500])
if m:
    print(f'报告日期: {m.group()}')
print(f'报告地址: https://rerealnico.github.io/csi500-daily-report/report.html')
