"""
部署打包脚本 - 为腾讯云函数 (SCF) 生成部署包

用法:
  python deploy_scf.py

将会生成 scf_deploy.zip，然后手动上传到腾讯云函数控制台。

也可一键打包并上传（需先安装 SCF CLI）:
  pip install scf
  python deploy_scf.py --upload
"""
import os
import sys
import zipfile
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime


PROJECT_ROOT = Path(__file__).parent

# 需要打包的 Python 源文件
SOURCE_FILES = [
    "main.py",
    "config.py",
    "data_fetcher.py",
    "valuation_analyzer.py",
    "volume_analyzer.py",
    "fundamental_analyzer.py",
    "scorer.py",
    "reporter.py",
    "visualizer.py",
    "notifier.py",
    "scf_handler.py",
]

# 排除打包的目录/文件
EXCLUDE_DIRS = {
    "venv", ".venv", "__pycache__", ".git",
    "reports", "data", "config",
    ".idea", ".vscode",
}

EXCLUDE_FILES = {
    "deploy_scf.py", "setup_schedule.ps1", "run_daily.bat",
    ".gitignore", "requirements.txt",
}


def build_zip(output_path: str = None) -> str:
    """打包部署包"""
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(PROJECT_ROOT / f"scf_deploy_{ts}.zip")

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. 添加源文件
        for filename in SOURCE_FILES:
            filepath = PROJECT_ROOT / filename
            if filepath.exists():
                zf.write(filepath, filename)
                print(f"  [+] {filename}")
            else:
                print(f"  [-] {filename} 不存在，跳过")

        # 2. 添加 requirements.txt
        req_path = PROJECT_ROOT / "requirements.txt"
        if req_path.exists():
            zf.write(req_path, "requirements.txt")
            print(f"  [+] requirements.txt")

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"\n[OK] 部署包已生成: {output_path}")
    print(f"     大小: {size_mb:.1f} MB")
    return output_path


def install_deps(zip_path: str, target_dir: str = None):
    """将 pip 依赖安装到本地目录并加入 zip"""
    if target_dir is None:
        target_dir = tempfile.mkdtemp(prefix="scf_deps_")

    print(f"\n[依赖] 正在安装 Python 依赖到 {target_dir} ...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "-r", str(PROJECT_ROOT / "requirements.txt"),
        "-t", target_dir,
        "--no-compile",
    ])

    print("[依赖] 正在合并到部署包...")
    with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(target_dir):
            rel_root = os.path.relpath(root, target_dir)
            for f in files:
                filepath = os.path.join(root, f)
                arcname = os.path.join(rel_root, f)
                zf.write(filepath, arcname)

    print("[依赖] 合并完成")
    return zip_path


def upload_to_scf(zip_path: str, function_name: str = "csi500_daily_report"):
    """通过 SCF CLI 上传部署包（需先安装 scf CLI）"""
    print(f"\n[上传] 正在部署到腾讯云函数: {function_name} ...")
    try:
        subprocess.check_call([
            "scf", "deploy",
            "--function-name", function_name,
            "--package", zip_path,
            "--entry-point", "scf_handler.main_handler",
            "--timeout", "600",
            "--memory-size", "512",
        ])
        print("[OK] 部署成功！")
    except FileNotFoundError:
        print("[ERROR] 未找到 SCF CLI，请先安装: pip install scf")
        print("       或手动上传 zip 到腾讯云函数控制台")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 部署失败: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="打包部署到腾讯云函数")
    parser.add_argument("--upload", action="store_true", help="打包并上传到SCF")
    parser.add_argument("--with-deps", action="store_true", help="打包时包含依赖")
    parser.add_argument("--function-name", default="csi500_daily_report", help="云函数名称")
    parser.add_argument("--output", default=None, help="输出zip路径")
    args = parser.parse_args()

    print("=" * 50)
    print("  中证500复盘系统 - SCF 部署打包")
    print("=" * 50)

    zip_path = build_zip(args.output)

    if args.with_deps:
        install_deps(zip_path)

    if args.upload:
        upload_to_scf(zip_path, args.function_name)
    else:
        print(f"\n[完成] 打包完成。如需上传请运行:")
        print(f"  python deploy_scf.py --upload")
        print(f"  或手动上传到 https://console.cloud.tencent.com/scf")
