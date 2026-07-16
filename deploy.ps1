param(
    [switch]$Help,
    [switch]$PushOnly
)

# ============================================================
#  中证500每日复盘 - 一键部署脚本
#  功能: 推送到 GitHub + 创建 gh-pages 分支(首次)
# ============================================================

$REPO_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $REPO_DIR

if ($Help) {
    Write-Host "使用方法:" -ForegroundColor Cyan
    Write-Host "  .\deploy.ps1             首次部署(推送 master + gh-pages)" -ForegroundColor White
    Write-Host "  .\deploy.ps1 -PushOnly    仅推送已有变更" -ForegroundColor White
    Write-Host ""
    Write-Host "首次部署后，在 GitHub 仓库 Settings → Pages 中:" -ForegroundColor Yellow
    Write-Host "  Source → gh-pages branch → / (root) → Save" -ForegroundColor Yellow
    exit
}

# 检查 git 状态
$status = git status --porcelain
if ($status) {
    Write-Host ">>> 存在未提交的变更，先提交..." -ForegroundColor Yellow
    git add -A
    git commit -m "chore: auto commit before deploy $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
}

Write-Host ">>> 推送 master 分支..." -ForegroundColor Green
git push origin master
if ($LASTEXITCODE -ne 0) {
    Write-Host "    [ERROR] master 推送失败! 检查网络或 token 是否有效" -ForegroundColor Red
    exit 1
}

# 检查 gh-pages 分支是否存在
$hasGhPages = git rev-parse --verify gh-pages 2>$null
if (-not $hasGhPages) {
    Write-Host ">>> 创建 gh-pages 分支..." -ForegroundColor Yellow
    
    # 保存当前分支
    $currentBranch = git rev-parse --abbrev-ref HEAD
    
    # 创建 orphan 分支
    git checkout --orphan gh-pages
    
    # 删除所有文件
    git rm -rf --quiet .
    
    # 只保留报告文件
    if (Test-Path "reports\report.html") {
        Copy-Item "reports\*" . -Recurse
        git add report.html dashboard.png score_distribution.png top_stocks.png -ErrorAction SilentlyContinue
        git add report*.txt -ErrorAction SilentlyContinue
    }
    
    git commit -m "deploy: 中证500每日复盘报告 $(Get-Date -Format 'yyyy-MM-dd')"
    
    # 切回原分支
    git checkout $currentBranch
}

Write-Host ">>> 推送 gh-pages 分支..." -ForegroundColor Green
git push origin gh-pages
if ($LASTEXITCODE -ne 0) {
    Write-Host "    [ERROR] gh-pages 推送失败!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  ✅ 部署完成!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步: 在 GitHub 仓库开启 Pages" -ForegroundColor White
Write-Host "  1. 打开 https://github.com/rerealnico/csi500-daily-report/settings/pages" -ForegroundColor Cyan
Write-Host "  2. Source → gh-pages branch → / (root) → Save" -ForegroundColor Cyan
Write-Host ""
Write-Host "报告地址:" -ForegroundColor White
Write-Host "  https://rerealnico.github.io/csi500-daily-report/report.html" -ForegroundColor Cyan
Write-Host ""
