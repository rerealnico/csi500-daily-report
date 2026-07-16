"""
微信推送模块 - 通过 Server酱 推送报告到微信文件助手
使用说明：
  1. 打开 https://sct.ftqq.com 用微信扫码登录
  2. 复制你的 SendKey
  3. 创建 config/notifier_config.json:
     {"sendkey": "你的SendKey", "enabled": true}
"""
import json
import os
import urllib.request
import urllib.parse
from pathlib import Path
from config import PROJECT_ROOT


NOTIFIER_CONFIG_FILE = PROJECT_ROOT / "config" / "notifier_config.json"


def load_config() -> dict:
    """加载推送配置，优先从环境变量读取（云函数模式）"""
    # 环境变量优先（用于云函数 / GitHub Actions）
    sendkey = os.environ.get("SENDKEY", "")
    if sendkey:
        return {"sendkey": sendkey, "enabled": True}
    # 本地配置文件兜底
    if NOTIFIER_CONFIG_FILE.exists():
        try:
            return json.loads(NOTIFIER_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"sendkey": "", "enabled": False}


def save_config(sendkey: str, enabled: bool = True):
    """保存推送配置"""
    NOTIFIER_CONFIG_FILE.parent.mkdir(exist_ok=True)
    NOTIFIER_CONFIG_FILE.write_text(
        json.dumps({"sendkey": sendkey, "enabled": enabled}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[推送] 配置已保存: {NOTIFIER_CONFIG_FILE}")


def push_report(report_text: str, report_date: str = "", chart_paths: list = None, image_urls: list = None) -> bool:
    """
    推送报告到微信

    Parameters
    ----------
    report_text : str
        报告文本
    report_date : str
        报告日期
    chart_paths : list[str], optional
        图表文件路径列表
    image_urls : list[str], optional
        图床图片URL列表（将展示在报告中）

    Returns
    -------
    bool
        推送是否成功
    """
    config = load_config()
    if not config.get("enabled") or not config.get("sendkey"):
        print("[推送] 未配置推送（跳过），运行以下命令设置：")
        print(f"       python -c \"from notifier import save_config; save_config('你的SendKey')\"")
        return False

    sendkey = config["sendkey"]
    title = f"中证500复盘报告 {report_date}"

    # ---- 构建 Markdown 内容 ----
    md_lines = []

    # 1. 图片展示（置顶，美观大气）
    if image_urls:
        md_lines.append("## 📊 大盘面分析")
        for url in image_urls:
            md_lines.append(f"![图表]({url})")
        md_lines.append("---")

    # 2. 精简报告文本
    lines = report_text.split("\n")
    capture = False
    for line in lines:
        if "[推荐关注]" in line or "[风险提示]" in line or "Top" in line:
            capture = True
        if capture:
            md_lines.append(line)
        if "生成时间" in line:
            md_lines.append(line)
            break

    # 3. 底部说明
    md_lines.append("")
    md_lines.append("> 数据来源: baostock | 中证500成分股")
    md_lines.append("> 评分模型: 估值+基本面+量能+动量")

    content = "\n".join(md_lines)

    # 发送请求
    data = urllib.parse.urlencode({
        "title": title,
        "desp": content,
        "tags": "中证500,复盘",
    }).encode("utf-8")

    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("code") == 0:
                print(f"[推送] ✅ 微信推送成功: {title}")
                return True
            else:
                print(f"[推送] ❌ 推送失败: {result.get('message', '未知错误')}")
                return False
    except Exception as e:
        print(f"[推送] ❌ 网络错误: {e}")
        return False


def setup_wizard():
    """配置引导（命令行交互）"""
    print("=" * 50)
    print("  微信推送配置向导")
    print("=" * 50)
    print()
    print("Step 1: 打开 https://sct.ftqq.com 扫码登录")
    print("Step 2: 复制你的 SendKey")
    print()
    sendkey = input("请输入 SendKey: ").strip()
    if sendkey:
        save_config(sendkey)
        print("[OK] 配置完成！运行 python main.py 时会自动推送报告到微信")
    else:
        print("[WARN] 取消配置")


if __name__ == "__main__":
    setup_wizard()
