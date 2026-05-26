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
from genre_map import store_url, bilingual

st.set_page_config(page_title="游戏详情", page_icon="🔍", layout="wide")
st.title("🔍 游戏详情")

conn = get_conn()

# 搜索框
search = st.text_input("搜索游戏名称或 App ID", placeholder="例：Block Blast 或 com.abc.game")

if not search:
    st.info("请输入游戏名称或 App ID 进行搜索")
    st.stop()

matches = pd.read_sql_query("""
    SELECT app_id, title, developer, genre, released, icon_url
    FROM games
    WHERE title LIKE ? OR app_id LIKE ?
    LIMIT 20
""", conn, params=(f"%{search}%", f"%{search}%"))

if matches.empty:
    st.warning("未找到匹配的游戏")
    st.stop()

# 选择游戏
options = {f"{r['title']} ({r['app_id']})": r['app_id'] for _, r in matches.iterrows()}
selected_label = st.selectbox("选择游戏", list(options.keys()))
app_id = options[selected_label]

# 游戏基本信息
g = conn.execute("SELECT * FROM games WHERE app_id = ?", (app_id,)).fetchone()
st.subheader(g["title"])

col1, col2, col3 = st.columns([1, 2, 2])
with col1:
    if g["icon_url"]:
        st.image(g["icon_url"], width=120)
with col2:
    genre_label = bilingual(g["genre"]) if g["genre"] else "—"
    st.markdown(f"""
    **开发者**：{g["developer"] or "—"}
    **品类**：{genre_label}
    **上架日期**：{g["released"] or "—"}
    **App ID**：`{g["app_id"]}`
    """)
    st.link_button("🔗 在 Google Play 查看", store_url(g["app_id"]))
with col3:
    latest = conn.execute("""
        SELECT score, ratings, reviews, installs
        FROM daily_snapshots WHERE app_id = ?
        ORDER BY snapshot_date DESC LIMIT 1
    """, (app_id,)).fetchone()
    if latest:
        st.metric("评分", f"{latest['score']:.2f}" if latest["score"] else "—")
        st.metric("评论数", f"{latest['reviews']:,}" if latest["reviews"] else "—")
        st.metric("安装量", latest["installs"] or "—")

# 历史快照
st.divider()
st.subheader("数据历史")
history = pd.read_sql_query("""
    SELECT snapshot_date, score, ratings, reviews, installs
    FROM daily_snapshots WHERE app_id = ?
    ORDER BY snapshot_date ASC
""", conn, params=(app_id,))

if not history.empty:
    tab1, tab2 = st.tabs(["评论/评分趋势", "原始数据"])
    with tab1:
        fig = px.line(history, x="snapshot_date", y=["score", "reviews"],
                      labels={"snapshot_date": "日期", "value": "数值", "variable": "指标"},
                      title="评分 & 评论数趋势")
        st.plotly_chart(fig, use_container_width=True)
    with tab2:
        st.dataframe(history, use_container_width=True, hide_index=True)

# 榜单历史
st.divider()
st.subheader("榜单排名历史")
rank_hist = pd.read_sql_query("""
    SELECT snapshot_date, chart_type, category, rank
    FROM chart_rankings WHERE app_id = ?
    ORDER BY snapshot_date DESC
    LIMIT 200
""", conn, params=(app_id,))

if not rank_hist.empty:
    fig2 = px.line(rank_hist, x="snapshot_date", y="rank",
                   color="chart_type", line_dash="category",
                   labels={"snapshot_date": "日期", "rank": "排名"},
                   title="各榜单排名变化（越低越好）")
    fig2.update_yaxes(autorange="reversed")
    st.plotly_chart(fig2, use_container_width=True)

# 截图
screenshots = conn.execute(
    "SELECT url FROM screenshots WHERE app_id = ?", (app_id,)
).fetchall()
if screenshots:
    st.divider()
    st.subheader("游戏截图")
    cols = st.columns(min(len(screenshots), 4))
    for i, row in enumerate(screenshots[:8]):
        cols[i % 4].image(row["url"])

conn.close()
