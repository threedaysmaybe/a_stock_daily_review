"""把选股结果数据提交并推送到 GitHub（桌面端跑完选股后调用）。

更新逻辑：
1. git add stock_choose/output
2. git commit（若无变化会自动跳过）
3. git push（优先走代理，失败再试直连）
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


def main():
    _run(["git", "add", "stock_choose/output"])
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
