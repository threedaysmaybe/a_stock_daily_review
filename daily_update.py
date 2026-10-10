"""每日收盘后自动下载数据 + 推送到 GitHub。

定时任务（schtasks）每天 23:00 调用本脚本：
  1. 休市（周末/节假日）直接跳过
  2. 下载当天数据到 data/ 目录
  3. 更新 data/manifest.json（手机端据此判断数据新不新）
  4. git add + commit + push（优先走代理，失败自动直连）
"""
import os
import subprocess
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))


def _run(args):
    return subprocess.run(
        args, cwd=BASE, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def _push():
    last = None
    for extra in ([], ["-c", "http.proxy=", "-c", "https.proxy="]):
        last = _run(["git"] + extra + ["push", "origin", "main"])
        if last.returncode == 0:
            print("推送成功 ✅")
            return
    print("推送失败：" + (last.stderr.strip()[-200:] if last and last.stderr else ""))


def main():
    os.chdir(BASE)
    date_str = datetime.now().strftime("%Y%m%d")
    print(f"[{date_str}] 开始每日数据更新...")

    # 0. 休市跳过
    try:
        sys.path.insert(0, BASE)
        from stock_choose import main as sc_main
        if not sc_main.is_trading_day(datetime.now().strftime("%Y-%m-%d")):
            print("今天休市（周末/节假日），跳过数据下载与推送")
            return
    except Exception as e:  # noqa: BLE001
        print(f"交易日判断失败（继续执行）: {e}")

    # 1. 下载当天数据
    print("步骤1: 下载当天数据...")
    try:
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
            except Exception as e:  # noqa: BLE001
                print(f"回补失败 {date_str_} {kind}: {e}")
    except Exception as e:  # noqa: BLE001
        print(f"下载数据出错（继续 push）: {e}")

    # 2. 更新 data/manifest.json（手机端 github_sync 依据）
    print("步骤2: 更新 data/manifest.json...")
    try:
        import push_output
        push_output._write_data_manifest()
    except Exception as e:  # noqa: BLE001
        print(f"manifest 更新失败: {e}")

    # 3. git add + commit + push
    print("步骤3: 提交并推送到 GitHub...")
    _run(["git", "add", "-A"])
    r = _run(["git", "commit", "-m", f"每日数据更新 {date_str}"])
    if r.returncode == 0:
        print("已提交")
    else:
        print("提交失败或无变化（正常，若没有新数据）")
    _push()
    print("完成")


if __name__ == "__main__":
    main()
