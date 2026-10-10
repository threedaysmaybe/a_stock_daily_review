"""统一数据目录。

桌面端：04 根目录下的 data/；
手机端（Streamlit Cloud）：SC_DATA_ROOT 环境变量指向 GitHub 同步下来的临时目录。
"""
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    return os.environ.get("SC_DATA_ROOT") or os.path.join(_ROOT, "data")
