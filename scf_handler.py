"""
腾讯云函数 (SCF) 入口
部署到腾讯云函数后，每日 15:00 自动触发运行

使用方法：
  1. 在 SCF 控制台创建函数（Python 3.10）
  2. 环境变量添加 SENDKEY
  3. 设置定时触发器：cron 表达式 "0 7 * * 1-5"（每天 15:00 北京时间）
  4. 执行方法: scf_handler.main_handler
"""
import json
import sys
import io
import traceback

# SCF 云函数环境编码修复
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def main_handler(event, context):
    """
    腾讯云函数入口

    Parameters
    ----------
    event : dict
        触发事件（定时器触发时包含时间信息）
    context : SCFContext
        运行上下文

    Returns
    -------
    dict
        {"code": 0, "message": "...", "data": {...}}
    """
    print(f"[SCF] 中证500复盘分析启动 | 事件: {json.dumps(event, ensure_ascii=False)}")

    try:
        from main import run_pipeline

        final_scores = run_pipeline(cloud_mode=True)

        print(f"[SCF] 分析完成: {len(final_scores)} 只股票")
        return {
            "code": 0,
            "message": "分析完成",
            "data": {
                "count": len(final_scores),
                "top_score": round(float(final_scores["total_score"].iloc[0]), 1),
                "top_stock": str(final_scores.iloc[0].get("stock_name", "")),
            },
        }

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        traceback.print_exc()
        print(f"[SCF] 执行失败: {error_msg}")

        # 尝试推送错误信息
        try:
            from notifier import push_report
            push_report(
                f"[SCF 执行失败]\n{error_msg}\n\n{traceback.format_exc()}",
                report_date="",
            )
        except Exception:
            pass

        return {
            "code": -1,
            "message": error_msg,
        }
