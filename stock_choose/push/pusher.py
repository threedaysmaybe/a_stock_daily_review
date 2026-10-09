"""推送封装：Server酱（微信）"""
import requests

SERVERCHAN_URL = "https://sctapi.ftqq.com/{sendkey}.send"


def push_serverchan(sendkey: str, title: str, content: str) -> bool:
    """通过 Server酱3 推送到微信。"""
    url = SERVERCHAN_URL.format(sendkey=sendkey)
    try:
        resp = requests.post(url, data={"title": title, "desp": content}, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        return result.get("code") == 0
    except Exception as e:  # noqa: BLE001
        print(f"[推送异常] {e}")
        return False


def _clean(v) -> str:
    """把 NaN/None 转空字符串，其余转 str。"""
    if v is None:
        return ""
    if isinstance(v, float) and v != v:  # NaN 判断（NaN != NaN）
        return ""
    return str(v)


def format_short_message(date: str, top, sentiment: dict) -> str:
    """短期表推送（Markdown 表格）。"""
    up_ratio = sentiment.get("up_ratio")
    up_str = f"{up_ratio:.0%}" if up_ratio is not None else "N/A"

    lines = [
        f"**每日量化选股 · {date}**",
        "",
        f"市场情绪：**{sentiment.get('level', '')}**　上涨占比 {up_str}　操作建议：**{sentiment.get('advice', '')}**",
        "",
        "| 排名 | 名称 | 代码 | 得分 | 信号 |",
        "|:---:|:---|:---|:---:|:---|",
    ]
    for _, row in top.head(20).iterrows():
        sign = "+" if row.get("final_score", 0) >= 0 else ""
        sig = _clean(row.get("pos_tags", ""))
        risk = _clean(row.get("risk_tags", ""))
        if risk:
            sig = f"{sig} 风险:{risk}".strip()
        lines.append(
            f"| {int(row['rank'])} | {row['name']} | {row['code']} | {sign}{row['final_score']:.2f} | {sig} |"
        )

    return "\n".join(lines)


def format_long_message(date: str, top) -> str:
    """长期表推送（纯文本 + 两个空格硬换行）。"""
    lines = [
        f"**每周价值选股 · {date}**",
        "",
        "**长期精选 Top20（估值/质量/成长）：**",
    ]
    for _, row in top.head(20).iterrows():
        sign = "+" if row["total_score"] >= 0 else ""
        lines.append(f"{int(row['rank'])}.{row['name']} {row['code']} {sign}{row['total_score']:.2f}")

    return "\n".join("" if line == "" else line + "  " for line in lines)
