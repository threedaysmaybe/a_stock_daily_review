"""手机端（Streamlit Cloud）数据同步：从 GitHub 拉取最新原始数据。

桌面端「更新数据」/定时任务跑完后会把当日原始数据 push 到 GitHub；
Cloud 打开 app 时先用本模块把最新数据下载到临时目录，并设置
SC_DATA_ROOT 环境变量，所有分析页面就会在这份新数据上实时计算。
"""
import json
import os
import tempfile
import urllib.request
from urllib.parse import quote

GH_BASE = "https://raw.githubusercontent.com/threedaysmaybe/a_stock_daily_review/main"


def _fetch(url: str, timeout: int = 15) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def _repo_data_root() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _repo_latest_date() -> str:
    root = _repo_data_root()
    dates = []
    if os.path.isdir(root):
        for name in os.listdir(root):
            if len(name) == 8 and name.isdigit():
                dates.append(name)
    return max(dates) if dates else ""


def sync() -> bool:
    """GitHub 数据比部署快照新 → 下载并设置 SC_DATA_ROOT；返回是否已切换。"""
    try:
        manifest = json.loads(_fetch(f"{GH_BASE}/data/manifest.json", timeout=10).decode("utf-8"))
    except Exception:
        return False

    gh_date = (manifest.get("result_date") or "").replace("-", "")
    if not gh_date or gh_date <= _repo_latest_date():
        return False

    dest = os.path.join(tempfile.gettempdir(), "sc_data_gh")
    data_root = os.path.join(dest, "data")
    marker = os.path.join(dest, ".synced")

    # 已同步过同一天 → 直接复用
    try:
        if open(marker, encoding="utf-8").read().strip() == gh_date and os.path.isdir(data_root):
            os.environ["SC_DATA_ROOT"] = data_root
            return True
    except Exception:
        pass

    try:
        for rel in manifest.get("files") or []:
            out = os.path.join(dest, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            try:
                with open(out, "wb") as f:
                    f.write(_fetch(f"{GH_BASE}/{quote(rel)}", timeout=20))
            except Exception:
                pass

        if os.path.exists(os.path.join(data_root, gh_date, "_meta.json")):
            with open(marker, "w", encoding="utf-8") as f:
                f.write(gh_date)
            os.environ["SC_DATA_ROOT"] = data_root
            return True
    except Exception:
        pass
    return False


if __name__ == "__main__":
    print("已切换 GitHub 数据" if sync() else "使用部署快照数据")
