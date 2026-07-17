import requests
h = {'Authorization': 'Bearer TOKEN_REMOVED', 'Accept': 'application/vnd.github+json'}
r = requests.get('https://api.github.com/repos/rerealnico/csi500-daily-report/actions/runs?per_page=1', headers=h, timeout=15).json()
rid = r['workflow_runs'][0]['id']
r2 = requests.get(f'https://api.github.com/repos/rerealnico/csi500-daily-report/actions/runs/{rid}/jobs', headers=h, timeout=15).json()
for j in r2['jobs']:
    print(f'Job: {j["name"]} ({j["status"]})')
    for step in j.get('steps', []):
        s = step['status']
        c = step.get('conclusion', '') or ''
        icon = '>>>' if s == 'in_progress' else ('OK' if c == 'success' else ('FAIL' if c == 'failure' else '?'))
        print(f'  [{icon}] {step["name"]}')
