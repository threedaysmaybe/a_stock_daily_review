"""把每日数据提交并推送到 GitHub（桌面端跑完后调用）。

推送内容：
1. data/<最新交易日>/ 的全部文件 + data 根散文件（portfolio/stock_list/thresholds/hot_money_order）
2. stock_choose/output 的选股结果
3. 生成 data/manifest.json（手机端据此判断数据新不新、下载哪些文件）

git push 优先走代理，失败自动试直连。
"""
import json
import os
import subprocess
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(BASE, "data")
LOOSE_FILES = ["portfolio.json", "stock_list.csv", "thresholds.json", "hot_money_order.json"]


def _run(args):
    return subprocess.run(
        args, cwd=BASE, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def _write_data_manifest():
    """生成 data/manifest.json：最新日期 + 需要下载的文件相对路径。"""
    if not os.path.isdir(DATA_ROOT):
        return
    dates = sorted(
        d for d in os.listdir(DATA_ROOT)
        if len(d) == 8 and d.isdigit() and os.path.isdir(os.path.join(DATA_ROOT, d))
    )
    # 跳过空目录（可能有下载失败留下的空日期目录）
    dates = [d for d in dates if os.listdir(os.path.join(DATA_ROOT, d))]
    if not dates:
        return
    latest = dates[-1]
    files = []
    latest_dir = os.path.join(DATA_ROOT, latest)
    for name in sorted(os.listdir(latest_dir)):
        if os.path.isfile(os.path.join(latest_dir, name)):
            files.append(f"data/{latest}/{name}")
    for name in LOOSE_FILES:
        p = os.path.join(DATA_ROOT, name)
        if os.path.isfile(p):
            files.append(f"data/{name}")
    manifest = {
        "result_date": f"{latest[:4]}-{latest[4:6]}-{latest[6:]}",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files": files,
    }
    with open(os.path.join(DATA_ROOT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def main():
    _write_data_manifest()
    _run(["git", "add", "data", "stock_choose/output"])
    _run(["git", "commit", "-m", "数据更新 " + datetime.now().strftime("%Y-%m-%d %H:%M")])

    last = None
    for extra in ([], ["-c", "http.proxy=", "-c", "https.proxy="]):
        last = _run(["git"] + extra + ["push", "origin", "main"])
        if last.returncode == 0:
            print("已推送到 GitHub")
            return 0
    print("推送失败：" + (last.stderr or last.stdout or ""))
    return 1


if __name__ == "__main__":
    sys.exit(main())
