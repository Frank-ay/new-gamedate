import os
import sys
from pathlib import Path
APP_ROOT = Path(os.environ.get("APP_ROOT", Path(__file__).parent.parent.parent))
sys.path.insert(0, str(APP_ROOT / "analysis"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from db import get_conn
from genre_map import bilingual, genre_options, parse_genre_filter, store_url

st.set_page_config(page_title="新游雷达", page_icon="🆕", layout="wide")
st.title("🆕 新游雷达")
st.caption("追踪快速崛起的新游：进榜速度 · 评论增速 · 品类热度 · 开发者背景")

conn = get_conn()

# 顶部核心指标卡片
latest = conn.execute(
    "SELECT MAX(snapshot_date) as d FROM chart_rankings"
).fetchone()["d"]

if not latest:
    st.warning("暂无数据，请先运行采集脚本：`npm run collect`")
    st.stop()

col1, col2, col3, col4 = st.columns(4)
cutoffs = {"≤30天": 30, "≤60天": 60, "≤90天": 90}
for (label, days), col in zip(cutoffs.items(), [col1, col2, col3]):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    cnt = conn.execute("""
        SELECT count(DISTINCT g.app_id) FROM games g
        JOIN chart_rankings cr ON cr.app_id = g.app_id
        WHERE g.released >= ? AND cr.snapshot_date = ?
    """, (cutoff, latest)).fetchone()[0]
    col.metric(f"新游({label})", cnt, help="今日在榜的新游数量")

top_speed = conn.execute("""
    SELECT g.title, gs.days_to_chart
    FROM growth_signals gs JOIN games g ON g.app_id = gs.app_id
    WHERE gs.signal_date = ? AND gs.days_to_chart IS NOT NULL
      AND gs.days_to_chart >= 0 AND gs.is_new_game = 1
    ORDER BY gs.days_to_chart ASC LIMIT 1
""", (latest,)).fetchone()
col4.metric("最快进榜", f"{top_speed['days_to_chart']}天" if top_speed else "—",
            help=top_speed["title"] if top_speed else "")

st.divider()

# --- 主体 Tabs：三个梯队 ---
tab30, tab60, tab90 = st.tabs(["🔥 极新（≤30天）", "⚡ 新游（≤60天）", "🌱 次新（≤90天）"])

def build_new_game_df(max_days, conn, latest_date):
    cutoff = (date.today() - timedelta(days=max_days)).isoformat()
    df = pd.read_sql_query("""
        SELECT
            g.app_id, g.title, g.developer, g.genre, g.released,
            ds.score, ds.reviews, ds.installs,
            gs.reviews_growth_7d, gs.rank_delta_7d,
            gs.days_since_release, gs.days_to_chart,
            gs.new_game_burst_score, gs.growth_score,
            cr.rank AS best_rank
        FROM games g
        LEFT JOIN daily_snapshots ds
               ON ds.app_id = g.app_id AND ds.snapshot_date = ?
        LEFT JOIN growth_signals gs
               ON gs.app_id = g.app_id AND gs.signal_date = ?
        LEFT JOIN (
            SELECT app_id, MIN(rank) AS rank
            FROM chart_rankings WHERE snapshot_date = ?
            GROUP BY app_id
        ) cr ON cr.app_id = g.app_id
        WHERE g.released >= ?
          AND cr.rank IS NOT NULL
        ORDER BY gs.new_game_burst_score DESC NULLS LAST,
                 gs.days_to_chart ASC NULLS LAST
    """, conn, params=(latest_date, latest_date, latest_date, cutoff))

    if df.empty:
        return df

    # 开发者背景判断：同一 developer 旗下游戏总数
    dev_counts = pd.read_sql_query("""
        SELECT developer, count(*) as total_games FROM games
        GROUP BY developer
    """, conn)
    df = df.merge(dev_counts, on="developer", how="left")
    df["开发者类型"] = df["total_games"].apply(
        lambda x: "🏢 大厂" if x and x >= 5 else "🧑‍💻 独立"
    )

    df["上架天数"] = df["days_since_release"].fillna(0).astype(int)
    df["进榜速度"] = df["days_to_chart"].apply(
        lambda x: f"{int(x)}天进榜" if pd.notna(x) and x >= 0 else "首次在榜"
    )
    df["评论增长"] = df["reviews_growth_7d"].fillna(0).apply(
        lambda x: f"+{x:.1f}%" if x > 0 else (f"{x:.1f}%" if x < 0 else "—")
    )
    df["排名变化"] = df["rank_delta_7d"].fillna(0).astype(int).apply(
        lambda x: f"↑{-x}" if x < 0 else (f"↓{x}" if x > 0 else "NEW")
    )
    df["爆发分"] = df["new_game_burst_score"].fillna(0).round(3)
    return df


def render_tab(max_days, tab, conn, latest):
    with tab:
        df = build_new_game_df(max_days, conn, latest)
        if df.empty:
            st.info("暂无数据（运行采集后才会有真实数据）")
            return

        top_n = st.slider(f"显示 Top N", 10, 100, 30, key=f"top_{max_days}")
        raw_genres = sorted(df["genre"].dropna().unique().tolist())
        g_opts = genre_options(raw_genres)
        dev_opts = ["全部", "🏢 大厂", "🧑‍💻 独立"]

        fc1, fc2 = st.columns(2)
        sel_genre_label = fc1.selectbox("品类筛选", g_opts, key=f"genre_{max_days}")
        sel_genre = parse_genre_filter(sel_genre_label)
        sel_dev = fc2.selectbox("开发者类型", dev_opts, key=f"dev_{max_days}")

        view = df.copy()
        view["品类"] = view["genre"].apply(bilingual)   # ← 双语列
        if sel_genre:
            view = view[view["genre"] == sel_genre]
        if sel_dev != "全部":
            view = view[view["开发者类型"] == sel_dev]
        view = view.head(top_n)

        view["商店"] = view["app_id"].apply(store_url)
        display = view[[
            "title", "商店", "品类", "开发者类型", "developer",
            "上架天数", "released", "best_rank",
            "进榜速度", "评论增长", "排名变化",
            "score", "reviews", "installs", "爆发分"
        ]].copy()
        display.columns = [
            "游戏名称", "商店", "品类", "开发者类型", "开发者",
            "上架天数", "上架日期", "最佳排名",
            "进榜速度", "7日评论增长", "7日排名变化",
            "评分", "评论数", "安装量", "爆发分"
        ]
        st.dataframe(
            display,
            column_config={"商店": st.column_config.LinkColumn("商店", display_text="🔗")},
            use_container_width=True,
            hide_index=True,
        )

        # 进榜速度 vs 评论增长 散点
        st.subheader("进榜速度 vs 评论增长速度")
        scatter_df = view.dropna(subset=["days_to_chart", "reviews_growth_7d"])
        if not scatter_df.empty:
            fig = px.scatter(
                scatter_df,
                x="days_to_chart", y="reviews_growth_7d",
                size="爆发分", color="品类",
                hover_name="title",
                hover_data=["developer", "上架天数", "best_rank"],
                labels={
                    "days_to_chart": "进榜速度（天，越小越快）",
                    "reviews_growth_7d": "7日评论增长(%)",
                    "品类": "品类"
                },
                title=f"上架 ≤{max_days}天的新游（气泡大小=爆发分）"
            )
            st.plotly_chart(fig, use_container_width=True, key=f"scatter_{max_days}")

        # 大厂 vs 独立对比
        st.subheader("大厂 vs 独立：平均进榜速度对比")
        cmp = view.dropna(subset=["days_to_chart"]).groupby("开发者类型").agg(
            平均进榜天数=("days_to_chart", "mean"),
            平均评论增长=("reviews_growth_7d", "mean"),
            数量=("app_id", "count")
        ).reset_index()
        if not cmp.empty:
            fig2 = px.bar(cmp, x="开发者类型", y="平均进榜天数",
                          color="开发者类型", text="数量",
                          title="大厂 vs 独立开发者平均进榜天数")
            st.plotly_chart(fig2, use_container_width=True, key=f"bar_{max_days}")


render_tab(30, tab30, conn, latest)
render_tab(60, tab60, conn, latest)
render_tab(90, tab90, conn, latest)

conn.close()
