"""通过 GitHub API 推送报告到 gh-pages 分支 (v2)"""
import requests
import base64
import os
from datetime import datetime

TOKEN = "TOKEN_REMOVED"
OWNER = "rerealnico"
REPO = "csi500-daily-report"
BRANCH = "gh-pages"
REPO_DIR = r"d:\qoder workplace\test 1"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
}

files_to_upload = [
    ("report.html", os.path.join(REPO_DIR, "reports", "report.html"), "text/html"),
    ("dashboard.png", os.path.join(REPO_DIR, "reports", "dashboard.png"), "image/png"),
    ("score_distribution.png", os.path.join(REPO_DIR, "reports", "score_distribution.png"), "image/png"),
    ("top_stocks.png", os.path.join(REPO_DIR, "reports", "top_stocks.png"), "image/png"),
]

def api_url(path):
    return f"https://api.github.com/repos/{OWNER}/{REPO}/{path}"

# 1. 获取分支引用
print("[1/6] 获取分支引用...")
resp = requests.get(api_url(f"git/refs/heads/{BRANCH}"), headers=headers)
if resp.status_code == 200:
    parent_sha = resp.json()["object"]["sha"]
    # 获取当前分支的最新提交的树
    commit_resp = requests.get(api_url(f"git/commits/{parent_sha}"), headers=headers)
    if commit_resp.status_code == 200:
        base_tree_sha = commit_resp.json()["tree"]["sha"]
        print(f"  分支已存在，当前提交: {parent_sha[:8]}，树: {base_tree_sha[:8]}")
    else:
        print(f"  获取提交信息失败: {commit_resp.status_code}")
        base_tree_sha = None
elif resp.status_code == 404:
    parent_sha = None
    base_tree_sha = None
    print(f"  分支不存在，将创建新分支")
else:
    print(f"  错误: {resp.status_code} {resp.text}")
    exit(1)

# 2. 创建blobs
print("[2/6] 创建文件 blobs...")
tree_items = []
for name, path, mime in files_to_upload:
    with open(path, "rb") as f:
        content = f.read()
    
    if mime.startswith("text/"):
        blob_data = {"content": content.decode("utf-8"), "encoding": "utf-8"}
    else:
        blob_data = {"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"}
    
    resp = requests.post(api_url("git/blobs"), headers=headers, json=blob_data)
    if resp.status_code not in (200, 201):
        print(f"  创建 blob 失败 [{name}]: {resp.status_code}")
        continue
    blob_sha = resp.json()["sha"]
    tree_items.append({"path": name, "mode": "100644", "type": "blob", "sha": blob_sha})
    print(f"  {name}: {blob_sha[:8]}")

# 3. 创建树（不指定 base_tree，直接从空构建）
print("[3/6] 创建树...")
tree_payload = {"tree": tree_items}  # 不传 base_tree，全量替换
resp = requests.post(api_url("git/trees"), headers=headers, json=tree_payload)
if resp.status_code not in (200, 201):
    print(f"  创建树失败: {resp.status_code} {resp.text}")
    exit(1)
tree_sha = resp.json()["sha"]
print(f"  树: {tree_sha[:8]}")

# 4. 创建提交（parent指向当前分支最新提交，或master）
print("[4/6] 创建提交...")
if parent_sha:
    parents = [parent_sha]
    print(f"  parent: gh-pages@{parent_sha[:8]}")
else:
    # 新分支，从master衍生
    resp = requests.get(api_url("git/refs/heads/master"), headers=headers)
    master_sha = resp.json()["object"]["sha"]
    parents = [master_sha]
    print(f"  parent: master@{master_sha[:8]}")

date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
commit_payload = {
    "message": f"deploy: 中证500每日复盘报告 {date_str}",
    "tree": tree_sha,
    "parents": parents,
}
resp = requests.post(api_url("git/commits"), headers=headers, json=commit_payload)
if resp.status_code not in (200, 201):
    print(f"  创建提交失败: {resp.status_code} {resp.text}")
    exit(1)
commit_sha = resp.json()["sha"]
print(f"  提交: {commit_sha[:8]}")

# 5. 更新分支引用
print("[5/6] 更新分支引用...")
ref_payload = {"sha": commit_sha, "force": True}
if parent_sha is None:
    resp = requests.post(api_url("git/refs"), headers=headers, json={"ref": f"refs/heads/{BRANCH}", **ref_payload})
    action = "创建"
else:
    resp = requests.patch(api_url(f"git/refs/heads/{BRANCH}"), headers=headers, json=ref_payload)
    action = "更新"

if resp.status_code in (200, 201):
    print(f"  ✅ {action}成功: gh-pages → {commit_sha[:8]}")
else:
    print(f"  ❌ {action}失败: {resp.status_code} {resp.text}")
    exit(1)

# 6. 也推送 master（通过GitHub API比较麻烦，先只推送关键变更）
# 但master分支的代码变更需要通过git push
# 不过gh-pages已经就绪，报告可访问了
print()
print("="*60)
print(f"  gh-pages 分支推送完成！")
print(f"  报告地址: https://{OWNER}.github.io/{REPO}/report.html")
print("="*60)
print()
print("下一步（在普通终端中执行）:")
print(f"  cd \"{REPO_DIR}\"")
print(f"  git push origin master")
print("  然后在 GitHub 仓库 Settings → Pages 中选择 gh-pages 分支")
