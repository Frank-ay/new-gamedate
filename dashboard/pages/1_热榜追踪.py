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
from genre_map import bilingual, genre_options, parse_genre_filter, CATEGORY_ZH, store_url

st.set_page_config(page_title="热榜追踪", page_icon="📊", layout="wide")
st.title("📊 热榜追踪")

conn = get_conn()

dates = [r["snapshot_date"] for r in conn.execute(
    "SELECT DISTINCT snapshot_date FROM chart_rankings ORDER BY snapshot_date DESC LIMIT 30"
).fetchall()]
if not dates:
    st.warning("暂无数据，请先运行采集脚本：`npm run collect`")
    st.stop()

selected_date = st.selectbox("选择日期", dates)

col1, col2 = st.columns(2)
chart_types = [r["chart_type"] for r in conn.execute(
    "SELECT DISTINCT chart_type FROM chart_rankings ORDER BY chart_type"
).fetchall()]
raw_cats = [r["category"] for r in conn.execute(
    "SELECT DISTINCT category FROM chart_rankings ORDER BY category"
).fetchall()]
cat_options = genre_options(raw_cats, category=True)

with col1:
    selected_chart = st.selectbox("榜单类型", chart_types, index=0)
with col2:
    selected_cat_label = st.selectbox("品类", cat_options, index=0)
    selected_cat = parse_genre_filter(selected_cat_label) or raw_cats[0]

top_n = st.slider("显示 Top N", 10, 100, 50)

df = pd.read_sql_query("""
    SELECT cr.rank, g.title, g.app_id, g.developer, g.genre,
           ds.score, ds.reviews, ds.installs
    FROM chart_rankings cr
    JOIN games g ON g.app_id = cr.app_id
    LEFT JOIN daily_snapshots ds ON ds.app_id = cr.app_id AND ds.snapshot_date = cr.snapshot_date
    WHERE cr.snapshot_date = ? AND cr.chart_type = ? AND cr.category = ?
    ORDER BY cr.rank ASC
    LIMIT ?
""", conn, params=(selected_date, selected_chart, selected_cat, top_n))

if df.empty:
    st.warning("该组合暂无数据")
    st.stop()

# 7 日排名变化
df_7d = pd.read_sql_query("""
    SELECT cr.app_id, cr.rank as rank_7d
    FROM chart_rankings cr
    WHERE cr.chart_type = ? AND cr.category = ?
      AND cr.snapshot_date = (
          SELECT MAX(snapshot_date) FROM chart_rankings
          WHERE snapshot_date < date(?, '-7 days')
      )
""", conn, params=(selected_chart, selected_cat, selected_date))

if not df_7d.empty:
    df = df.merge(df_7d, on="app_id", how="left")
    df["rank_delta"] = df["rank_7d"] - df["rank"]
    df["趋势"] = df["rank_delta"].apply(
        lambda x: f"↑{int(x)}" if pd.notna(x) and x > 0
        else (f"↓{int(-x)}" if pd.notna(x) and x < 0 else "NEW")
    )
else:
    df["趋势"] = "NEW"

# 品类双语列
df["品类"] = df["genre"].apply(bilingual)

st.subheader(f"{selected_chart} / {selected_cat_label}  —  Top {top_n}")
df["商店"] = df["app_id"].apply(store_url)
display_df = df[["rank", "title", "商店", "developer", "品类", "score", "reviews", "installs", "趋势"]].copy()
display_df.columns = ["排名", "游戏名称", "商店", "开发者", "品类", "评分", "评论数", "安装量", "7日变化"]
st.dataframe(
    display_df,
    column_config={"商店": st.column_config.LinkColumn("商店", display_text="🔗")},
    use_container_width=True,
    hide_index=True,
)

# 历史排名折线
st.divider()
st.subheader("历史排名趋势（选择游戏查看）")
selected_apps = st.multiselect("选择游戏", df["title"].tolist(), max_selections=8)

if selected_apps:
    selected_ids = df[df["title"].isin(selected_apps)]["app_id"].tolist()
    hist = pd.read_sql_query("""
        SELECT cr.snapshot_date, cr.rank, g.title
        FROM chart_rankings cr
        JOIN games g ON g.app_id = cr.app_id
        WHERE cr.app_id IN ({}) AND cr.chart_type = ? AND cr.category = ?
        ORDER BY cr.snapshot_date
    """.format(",".join("?" * len(selected_ids))),
    conn, params=selected_ids + [selected_chart, selected_cat])

    if not hist.empty:
        fig = px.line(hist, x="snapshot_date", y="rank", color="title",
                      title="历史排名（数值越小排名越高）",
                      labels={"snapshot_date": "日期", "rank": "排名", "title": "游戏"})
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

conn.close()
