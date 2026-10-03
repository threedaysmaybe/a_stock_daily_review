"""每日收盘后自动下载数据 + 推送到 GitHub。

定时任务（schtasks）每天 23:00 调用本脚本：
  1. 下载当天数据到 data/ 目录
  2. git add + commit + push（触发 Streamlit Cloud 重新部署，手机即可看到最新快照）
"""
import os
import subprocess
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    os.chdir(BASE)
    date_str = datetime.now().strftime("%Y%m%d")
    print(f"[{date_str}] 开始每日数据更新...")

    # 1. 下载当天数据
    print("步骤1: 下载当天数据...")
    try:
        sys.path.insert(0, BASE)
        import data_manager as dm
        meta = dm.download_all()
        ok = meta.get("ok", 0) if isinstance(meta, dict) else 0
        fail = meta.get("fail", 0) if isinstance(meta, dict) else 0
        print(f"下载完成: 成功 {ok}, 失败 {fail}")
        # 回补缺失日期（行业/概念排名）
        missing = meta.get("backfill_needed", []) if isinstance(meta, dict) else []
        for date_str_, kind in missing:
            try:
                dm.backfill_one(date_str_, kind)
                print(f"回补 {date_str_} {kind}")
            except Exception as e:
                print(f"回补失败 {date_str_} {kind}: {e}")
    except Exception as e:
        print(f"下载数据出错（继续 push）: {e}")

    # 2. git add + commit + push
    print("步骤2: 提交并推送到 GitHub...")
    subprocess.run(["git", "add", "-A"], check=False)
    r = subprocess.run(
        ["git", "commit", "-m", f"每日数据更新 {date_str}"],
        capture_output=True, text=True,
    )
    if r.returncode == 0:
        print("已提交")
    else:
        print(f"提交失败或无变化: {r.stderr.strip()[-150:] if r.stderr else ''}")

    p = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
    if p.returncode == 0:
        print("推送成功 ✅")
    else:
        print(f"推送失败: {p.stderr.strip()[-200:] if p.stderr else ''}")

    print("完成")


if __name__ == "__main__":
    main()
