import os
import sys
from pathlib import Path
APP_ROOT = Path(os.environ.get("APP_ROOT", Path(__file__).parent.parent.parent))
sys.path.insert(0, str(APP_ROOT / "analysis"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from db import get_conn
from genre_map import bilingual, genre_options, parse_genre_filter, store_url

st.set_page_config(page_title="增长游戏", page_icon="📈", layout="wide")
st.title("📈 增长游戏榜")

conn = get_conn()

dates = [r["signal_date"] for r in conn.execute(
    "SELECT DISTINCT signal_date FROM growth_signals ORDER BY signal_date DESC LIMIT 30"
).fetchall()]
if not dates:
    st.warning("暂无数据，请先运行采集脚本：`npm run collect`")
    st.stop()

col_d, col_g, col_n = st.columns(3)
with col_d:
    selected_date = st.selectbox("日期", dates)
with col_g:
    raw_genres = [r["genre"] for r in conn.execute(
        "SELECT DISTINCT genre FROM games WHERE genre IS NOT NULL ORDER BY genre"
    ).fetchall()]
    g_options = genre_options(raw_genres)
    selected_genre_label = st.selectbox("品类", g_options)
    selected_genre = parse_genre_filter(selected_genre_label)
with col_n:
    top_n = st.slider("显示 Top N", 10, 200, 50)

genre_filter = "" if not selected_genre else f"AND g.genre = '{selected_genre}'"

# 数据模式判断
has_growth = conn.execute("""
    SELECT count(*) FROM growth_signals
    WHERE signal_date = ? AND reviews_growth_7d IS NOT NULL
""", (selected_date,)).fetchone()[0]

if has_growth:
    mode, sort_col = "growth", "gs.growth_score"
    mode_label = "综合增长分（7日趋势）"
    mode_tip = "评论增长 40% + 排名上升 40% + 新游爆发 20%"
else:
    mode, sort_col = "heat", "gs.today_heat_score"
    mode_label = "今日热度分（排名+评论数+评分）"
    mode_tip = "数据积累不足 7 天，暂用今日热度作为排序依据。连续采集 7 天后自动切换为增长趋势分。"

if mode == "heat":
    st.info(f"ℹ️ **当前模式：今日热度榜** — {mode_tip}", icon="📊")
else:
    st.success(f"✅ **当前模式：增长趋势榜** — {mode_tip}", icon="📈")

df = pd.read_sql_query(f"""
    SELECT
        gs.growth_score, gs.today_heat_score,
        gs.rank_delta_7d, gs.reviews_growth_7d,
        gs.is_new_game, gs.new_game_burst_score,
        gs.days_since_release, gs.days_to_chart,
        g.title, g.app_id, g.developer, g.genre, g.released, g.icon_url,
        ds.score, ds.reviews, ds.installs,
        cr.best_rank
    FROM growth_signals gs
    JOIN games g ON g.app_id = gs.app_id
    LEFT JOIN daily_snapshots ds
           ON ds.app_id = gs.app_id AND ds.snapshot_date = gs.signal_date
    LEFT JOIN (
        SELECT app_id, MIN(rank) AS best_rank
        FROM chart_rankings WHERE snapshot_date = ?
        GROUP BY app_id
    ) cr ON cr.app_id = g.app_id
    WHERE gs.signal_date = ? {genre_filter}
    ORDER BY {sort_col} DESC
    LIMIT ?
""", conn, params=(selected_date, selected_date, top_n))

if df.empty:
    st.warning("该条件下暂无数据")
    st.stop()

# 顶部指标卡
m1, m2, m3, m4 = st.columns(4)
m1.metric("游戏总数", f"{len(df):,}")
m2.metric("最高热度分", f"{df['today_heat_score'].max():.3f}")
top_reviews = df.nlargest(1, "reviews").iloc[0] if df["reviews"].notna().any() else None
m3.metric("最多评论",
          f"{int(top_reviews['reviews']):,}" if top_reviews is not None and pd.notna(top_reviews['reviews']) else "—",
          help=top_reviews["title"] if top_reviews is not None else "")
m4.metric("其中新游(≤90天)", int(df["is_new_game"].sum()))

st.divider()

# 格式化
df["rank_delta_7d"] = df["rank_delta_7d"].fillna(0).astype(int)
df["7日排名变化"] = df["rank_delta_7d"].apply(
    lambda x: f"↑{-x}" if x < 0 else (f"↓{x}" if x > 0 else "NEW")
)
df["reviews_growth_7d"] = df["reviews_growth_7d"].fillna(0)
df["7日评论增长"] = df["reviews_growth_7d"].apply(
    lambda x: f"+{x:.1f}%" if x > 0 else (f"{x:.1f}%" if x < 0 else "—")
)
df["新游"] = df["is_new_game"].apply(lambda x: "🆕" if x else "")
df["主排序分"] = df[sort_col.split(".")[-1]].round(4)
df["品类"] = df["genre"].apply(bilingual)
df["商店"] = df["app_id"].apply(store_url)

display_df = df[["title", "商店", "developer", "品类", "score", "reviews", "installs",
                 "best_rank", "7日排名变化", "7日评论增长", "新游", "主排序分"]].copy()
display_df.columns = [
    "游戏名称", "商店", "开发者", "品类", "评分", "评论数", "安装量",
    "榜单最佳排名", "7日排名变化", "7日评论增长", "新游", mode_label
]
st.dataframe(
    display_df,
    column_config={"商店": st.column_config.LinkColumn("商店", display_text="🔗")},
    use_container_width=True,
    hide_index=True,
)

# 图表
st.divider()
tab1, tab2 = st.tabs(["📊 品类分布", "🔵 增长散点"])

with tab1:
    genre_stats = df.copy()
    genre_stats["品类双语"] = genre_stats["genre"].apply(bilingual)
    stats = genre_stats.groupby("品类双语").agg(
        数量=("app_id", "count"),
        平均分=(sort_col.split(".")[-1], "mean")
    ).reset_index().sort_values("平均分", ascending=False)
    if not stats.empty:
        fig = px.bar(stats, x="品类双语", y="数量",
                     color="平均分", color_continuous_scale="Blues",
                     labels={"品类双语": "品类", "数量": "游戏数量"},
                     title=f"各品类游戏数量（颜色深=平均{mode_label}高）")
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    if mode == "growth" and df["reviews_growth_7d"].abs().sum() > 0:
        scatter_df = df[df["reviews_growth_7d"].abs() > 0].copy()
        fig2 = px.scatter(
            scatter_df, x="reviews_growth_7d", y="rank_delta_7d",
            size="growth_score", color="品类",
            hover_name="title", hover_data=["developer", "score", "reviews"],
            labels={"reviews_growth_7d": "7日评论增长(%)",
                    "rank_delta_7d": "7日排名变化（负=上升）", "品类": "品类"},
            title="增长分布（气泡大小=综合增长分）"
        )
        fig2.update_yaxes(autorange="reversed")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        scatter_df = df.dropna(subset=["score", "reviews"])
        if not scatter_df.empty:
            fig2 = px.scatter(
                scatter_df, x="reviews", y="score",
                size="today_heat_score", color="品类",
                hover_name="title", hover_data=["developer", "best_rank"],
                log_x=True,
                labels={"reviews": "评论数（对数）", "score": "评分", "品类": "品类"},
                title="今日热度分布（气泡大小=热度分，X轴对数）"
            )
            st.plotly_chart(fig2, use_container_width=True)

conn.close()
