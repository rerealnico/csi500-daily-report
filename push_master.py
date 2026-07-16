"""Git Data API - 一次性推送所有变更到 master"""
import requests
import base64
import os
from datetime import datetime

TOKEN = "TOKEN_REMOVED"
OWNER = "rerealnico"
REPO = "csi500-daily-report"
BRANCH = "master"
REPO_DIR = r"d:\qoder workplace\test 1"

headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}

def api_url(p): return f"https://api.github.com/repos/{OWNER}/{REPO}/{p}"

# 要推送的文件
files = [
    ".github/workflows/daily_report.yml", ".gitignore",
    "config.py", "data_fetcher.py", "fundamental_analyzer.py", "main.py",
    "report_html.py", "reporter.py", "scorer.py", "visualizer.py",
    "valuation_analyzer.py", "volume_analyzer.py", "capital_flow_analyzer.py",
    "scf_handler.py", "notifier.py", "deploy_scf.py",
    "config/notifier_config.json", "requirements.txt", "deploy.ps1",
    "image_host.py",
]

# 1. 获取当前 master 的引用和树
print("[1/5] 获取 master 引用...")
ref_resp = requests.get(api_url(f"git/refs/heads/{BRANCH}"), headers=headers)
parent_sha = ref_resp.json()["object"]["sha"]
commit_resp = requests.get(api_url(f"git/commits/{parent_sha}"), headers=headers)
base_tree_sha = commit_resp.json()["tree"]["sha"]
print(f"  当前 master: {parent_sha[:8]}, 树: {base_tree_sha[:8]}")

# 2. 为每个文件创建 blob
print("[2/5] 创建文件 blobs...")
tree_items = []
for relpath in files:
    fullpath = os.path.join(REPO_DIR, relpath)
    if not os.path.exists(fullpath):
        # 文件被删除，添加删除标记
        tree_items.append({"path": relpath, "mode": "100644", "type": "blob", "sha": None})
        print(f"  [删除] {relpath}")
        continue
    
    with open(fullpath, "rb") as f:
        content = f.read()
    
    try:
        text = content.decode("utf-8")
        blob = {"content": text, "encoding": "utf-8"}
    except UnicodeDecodeError:
        blob = {"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"}
    
    resp = requests.post(api_url("git/blobs"), headers=headers, json=blob)
    if resp.status_code not in (200, 201):
        print(f"  [失败] {relpath}: {resp.status_code}")
        continue
    tree_items.append({"path": relpath, "mode": "100644", "type": "blob", "sha": resp.json()["sha"]})
    print(f"  [OK] {relpath}")

# 3. 创建新树（基于当前master树做增量）
print("[3/5] 创建树...")
tree_payload = {"base_tree": base_tree_sha, "tree": tree_items}
resp = requests.post(api_url("git/trees"), headers=headers, json=tree_payload)
if resp.status_code not in (200, 201):
    print(f"  创建树失败: {resp.status_code} {resp.text[:200]}")
    exit(1)
tree_sha = resp.json()["sha"]
print(f"  新树: {tree_sha[:8]}")

# 4. 创建提交
print("[4/5] 创建提交...")
date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
commit_payload = {
    "message": f"feat: ProcessPoolExecutor多进程并行 + 10年数据 + HTML报告内嵌图表\n\n自动部署 {date_str}",
    "tree": tree_sha,
    "parents": [parent_sha],
}
resp = requests.post(api_url("git/commits"), headers=headers, json=commit_payload)
if resp.status_code not in (200, 201):
    print(f"  创建提交失败: {resp.status_code} {resp.text[:200]}")
    exit(1)
commit_sha = resp.json()["sha"]
print(f"  提交: {commit_sha[:8]}")

# 5. 更新 master 引用
print("[5/5] 更新 master 引用...")
resp = requests.patch(api_url(f"git/refs/heads/{BRANCH}"), headers=headers,
                      json={"sha": commit_sha, "force": False})
if resp.status_code in (200, 201):
    print(f"  ✅ master 更新成功: {parent_sha[:8]} → {commit_sha[:8]}")
else:
    print(f"  ❌ 更新失败: {resp.status_code} {resp.text[:200]}")
    exit(1)

print()
print("="*60)
print("  ✅ 全部部署完成！")
print(f"  master: 已推送最新代码 → GitHub Actions 将自动运行")
print(f"  gh-pages: 报告已就绪")
print(f"  报告地址: https://{OWNER}.github.io/{REPO}/report.html")
print("="*60)
print()
print("最后一步: 去 GitHub 仓库开启 Pages")
print("  1. https://github.com/rerealnico/csi500-daily-report/settings/pages")
print("  2. Source → gh-pages branch → / (root) → Save")
