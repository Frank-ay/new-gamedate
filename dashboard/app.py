"""
Dashboard 主入口
运行方式：streamlit run dashboard/app.py
"""
import sys
import os
import subprocess
import time
from pathlib import Path
from datetime import datetime, date

# 路径来源:打包后由 Electron 主进程注入 APP_* 环境变量;dev 时回退到仓库相对路径
APP_ROOT = Path(
    os.environ.get("APP_ROOT", Path(__file__).parent.parent)
)
DATA_DIR = Path(
    os.environ.get("APP_DATA_DIR", APP_ROOT / "data")
)
LOG_DIR = Path(
    os.environ.get("APP_LOG_DIR", APP_ROOT / "logs")
)
PID_FILE = DATA_DIR / "collect.pid"

# 让 analysis 模块可被 import(打包后通过 APP_ROOT 注入正确路径)
sys.path.insert(0, str(APP_ROOT / "analysis"))

import streamlit as st

st.set_page_config(
    page_title="游戏增长监控",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# 快速采集面板（侧边栏）
# ─────────────────────────────────────────────


def _pid_alive(pid: int) -> bool:
    """跨平台探活:用 signal=0 探测进程是否存在。"""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_collecting() -> tuple[bool, int | None]:
    """读取 PID 文件并探活,Windows/macOS 都适用。"""
    if not PID_FILE.exists():
        return False, None
    try:
        pid = int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        PID_FILE.unlink(missing_ok=True)
        return False, None
    if _pid_alive(pid):
        return True, pid
    PID_FILE.unlink(missing_ok=True)
    return False, None


def start_collection() -> None:
    today = date.today().isoformat()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"collect-{today}.log"
    collect_js = APP_ROOT / "collector" / "collect.mjs"

    env = os.environ.copy()
    node_bin = os.environ.get("APP_NODE_BIN")
    if node_bin:
        # 打包后:用 Electron exe + ELECTRON_RUN_AS_NODE 跑 Node 脚本
        env["ELECTRON_RUN_AS_NODE"] = "1"
        cmd = [node_bin, str(collect_js)]
    else:
        # dev:用系统 node
        cmd = ["node", str(collect_js)]

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=open(log_file, "a"),
        stderr=subprocess.STDOUT,
        cwd=str(APP_ROOT),
    )
    PID_FILE.write_text(str(proc.pid))


def get_log_tail(n: int = 35) -> str:
    candidates = sorted(LOG_DIR.glob("collect-*.log"), reverse=True)
    if not candidates:
        candidates = sorted(LOG_DIR.glob("run_*.log"), reverse=True)
    if not candidates:
        return ""
    lines = candidates[0].read_text(errors="replace").splitlines()
    return "\n".join(lines[-n:])


def get_last_run_time() -> datetime | None:
    candidates = sorted(LOG_DIR.glob("collect-*.log"), reverse=True)
    if not candidates:
        candidates = sorted(LOG_DIR.glob("run_*.log"), reverse=True)
    if not candidates:
        return None
    return datetime.fromtimestamp(candidates[0].stat().st_mtime)


with st.sidebar:
    st.markdown("## ⚡ 快速采集")

    running, pid = is_collecting()
    last_run     = get_last_run_time()

    if running:
        st.warning(f"🔄 采集进行中…（PID {pid}）")
        if st.button("⏹ 停止采集", key="stop_collect"):
            try:
                os.kill(pid, 15)   # SIGTERM
            except OSError:
                pass
            PID_FILE.unlink(missing_ok=True)
            st.rerun()
    else:
        if last_run:
            delta = datetime.now() - last_run
            secs  = delta.total_seconds()
            if secs < 3600:
                time_str = f"{int(secs / 60)} 分钟前"
            elif secs < 86400:
                time_str = f"{int(secs / 3600)} 小时前"
            else:
                time_str = last_run.strftime("%m-%d %H:%M")
            st.success(f"✅ 空闲 — 上次：{time_str}")
        else:
            st.info("💤 尚无采集记录")

        if st.button("🚀 立即采集", type="primary", key="start_collect"):
            start_collection()
            st.rerun()

    with st.expander("📋 实时日志", expanded=running):
        log_text = get_log_tail(35)
        if log_text:
            st.code(log_text, language=None)
        else:
            st.caption("暂无日志")

    # 采集中每 3 秒自动刷新
    if running:
        time.sleep(3)
        st.rerun()

    st.divider()
    st.caption("点击「立即采集」手动触发一次数据更新")

# ─────────────────────────────────────────────
# 主页内容
# ─────────────────────────────────────────────
st.title("🎮 Google Play 美国市场增长游戏监控")
st.caption("数据来源：Google Play 美国区公开数据，点击侧边栏「立即采集」手动更新")

from db import get_conn
conn  = get_conn()
stats = {}
for tbl in ["games", "daily_snapshots", "chart_rankings", "growth_signals"]:
    stats[tbl] = conn.execute(f"SELECT count(*) as c FROM {tbl}").fetchone()["c"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("收录游戏",     f"{stats['games']:,}")
col2.metric("每日快照记录", f"{stats['daily_snapshots']:,}")
col3.metric("榜单排名记录", f"{stats['chart_rankings']:,}")
col4.metric("增长信号记录", f"{stats['growth_signals']:,}")

latest_date = conn.execute(
    "SELECT MAX(snapshot_date) as d FROM chart_rankings"
).fetchone()["d"]
st.info(f"最新数据日期：{latest_date or '暂无数据，请先运行采集脚本'}")

st.divider()
st.markdown("""
### 使用说明
- **热榜追踪** — 查看今日榜单及 7 日排名变化趋势
- **增长游戏** — 按综合增长分排行，发现正在上升的游戏
- **新游雷达** — 上架 90 天内的快速增长新游
- **游戏详情** — 查看单款游戏的历史数据与截图
- **品类趋势** — 哪个品类新游最多、进榜最快

左侧菜单切换页面；侧边栏顶部可手动触发一次采集。
""")
conn.close()
