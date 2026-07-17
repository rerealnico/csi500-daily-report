import requests

TOKEN = 'TOKEN_REMOVED'
OWNER = 'rerealnico'
REPO = 'csi500-daily-report'
headers = {'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/vnd.github+json'}

# 正在运行的job详情
r = requests.get(f'https://api.github.com/repos/{OWNER}/{REPO}/actions/runs', headers=headers, timeout=15)
for run in r.json().get('workflow_runs', []):
    if run['status'] == 'in_progress':
        r2 = requests.get(f'https://api.github.com/repos/{OWNER}/{REPO}/actions/runs/{run["id"]}/jobs', headers=headers, timeout=15)
        for job in r2.json().get('jobs', []):
            print(f'Job: {job["name"]} ({job["status"]})')
            for step in job.get('steps', []):
                status = step['status']
                conclusion = step.get('conclusion', '')
                dur = step.get('completed_at', '') or ''
                if status == 'in_progress':
                    print(f'  >>> {step["name"]} ...')
                elif conclusion == 'success':
                    print(f'  OK {step["name"]}')
        break
