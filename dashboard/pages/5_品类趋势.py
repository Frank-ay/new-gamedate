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
from db import get_conn
from genre_map import bilingual, genre_options, parse_genre_filter, store_url

st.set_page_config(page_title="品类趋势", page_icon="📊", layout="wide")
st.title("📊 新游品类趋势")
st.caption("哪个品类正在冒出最多新游？哪个品类进榜最快？帮你判断赛道机会")

conn = get_conn()

latest = conn.execute(
    "SELECT MAX(snapshot_date) as d FROM chart_rankings"
).fetchone()["d"]

if not latest:
    st.warning("暂无数据")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    new_days = st.selectbox("新游定义（上架天数 ≤）", [30, 60, 90], index=1)
with col2:
    chart_type = st.selectbox("榜单类型", ["全部"] + [r["chart_type"] for r in conn.execute(
        "SELECT DISTINCT chart_type FROM chart_rankings"
    ).fetchall()])

from datetime import date, timedelta
cutoff = (date.today() - timedelta(days=new_days)).isoformat()

chart_filter = "" if chart_type == "全部" else f"AND cr.chart_type = '{chart_type}'"

# ---- 1. 各品类新游数量 ----
st.divider()
st.subheader("① 各品类新游数量（今日在榜）")

genre_count = pd.read_sql_query(f"""
    SELECT g.genre, count(DISTINCT g.app_id) as new_game_count
    FROM games g
    JOIN chart_rankings cr ON cr.app_id = g.app_id
    WHERE g.released >= ? AND cr.snapshot_date = ? AND g.genre IS NOT NULL
          {chart_filter}
    GROUP BY g.genre
    ORDER BY new_game_count DESC
""", conn, params=(cutoff, latest))

if not genre_count.empty:
    genre_count["品类"] = genre_count["genre"].apply(bilingual)
    fig1 = px.bar(
        genre_count, x="品类", y="new_game_count",
        color="new_game_count", color_continuous_scale="Blues",
        labels={"品类": "品类", "new_game_count": "新游数量"},
        title=f"今日在榜的上架≤{new_days}天新游（各品类）"
    )
    fig1.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig1, use_container_width=True)

# ---- 2. 各品类平均进榜速度 ----
st.divider()
st.subheader("② 各品类平均进榜速度")
st.caption("越小说明该品类新游越容易快速进榜，赛道竞争激烈程度参考")

speed_df = pd.read_sql_query(f"""
    SELECT g.genre,
           round(avg(gs.days_to_chart), 1) as avg_days_to_chart,
           count(DISTINCT g.app_id) as count
    FROM games g
    JOIN growth_signals gs ON gs.app_id = g.app_id
    JOIN chart_rankings cr ON cr.app_id = g.app_id AND cr.snapshot_date = gs.signal_date
    WHERE g.released >= ? AND gs.signal_date = ?
      AND gs.days_to_chart IS NOT NULL AND gs.days_to_chart >= 0
      AND g.genre IS NOT NULL {chart_filter}
    GROUP BY g.genre
    HAVING count >= 2
    ORDER BY avg_days_to_chart ASC
""", conn, params=(cutoff, latest))

if not speed_df.empty:
    speed_df["品类"] = speed_df["genre"].apply(bilingual)
    fig2 = px.bar(
        speed_df, x="品类", y="avg_days_to_chart",
        text="count",
        color="avg_days_to_chart", color_continuous_scale="RdYlGn_r",
        labels={"品类": "品类", "avg_days_to_chart": "平均进榜天数", "count": "样本数"},
        title="各品类平均进榜速度（天）"
    )
    fig2.update_traces(texttemplate="%{text}款", textposition="outside")
    fig2.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig2, use_container_width=True)

# ---- 3. 各品类 7 日评论增长率对比 ----
st.divider()
st.subheader("③ 各品类新游平均评论增长速度")
st.caption("哪个品类的玩家最活跃、反馈最快")

growth_df = pd.read_sql_query(f"""
    SELECT g.genre,
           round(avg(gs.reviews_growth_7d), 2) as avg_review_growth,
           count(DISTINCT g.app_id) as count
    FROM games g
    JOIN growth_signals gs ON gs.app_id = g.app_id
    JOIN chart_rankings cr ON cr.app_id = g.app_id AND cr.snapshot_date = gs.signal_date
    WHERE g.released >= ? AND gs.signal_date = ?
      AND gs.reviews_growth_7d IS NOT NULL
      AND g.genre IS NOT NULL {chart_filter}
    GROUP BY g.genre
    HAVING count >= 2
    ORDER BY avg_review_growth DESC
""", conn, params=(cutoff, latest))

if not growth_df.empty:
    growth_df["品类"] = growth_df["genre"].apply(bilingual)
    fig3 = px.bar(
        growth_df, x="品类", y="avg_review_growth",
        text="count",
        color="avg_review_growth", color_continuous_scale="Greens",
        labels={"品类": "品类", "avg_review_growth": "平均7日评论增长(%)", "count": "样本数"},
        title="各品类新游平均7日评论增长率"
    )
    fig3.update_traces(texttemplate="%{text}款", textposition="outside")
    fig3.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig3, use_container_width=True)

# ---- 4. 大厂 vs 独立：品类渗透对比 ----
st.divider()
st.subheader("④ 大厂 vs 独立开发者：各品类占比")

dev_genre = pd.read_sql_query("""
    SELECT g.genre,
           CASE WHEN dev.total >= 5 THEN '大厂' ELSE '独立' END AS dev_type,
           count(DISTINCT g.app_id) as cnt
    FROM games g
    JOIN chart_rankings cr ON cr.app_id = g.app_id AND cr.snapshot_date = ?
    JOIN (
        SELECT developer, count(*) as total FROM games GROUP BY developer
    ) dev ON dev.developer = g.developer
    WHERE g.released >= ? AND g.genre IS NOT NULL
    GROUP BY g.genre, dev_type
""", conn, params=(latest, cutoff))

if not dev_genre.empty:
    dev_genre["品类"] = dev_genre["genre"].apply(bilingual)
    fig4 = px.bar(
        dev_genre, x="品类", y="cnt", color="dev_type",
        barmode="group",
        labels={"品类": "品类", "cnt": "新游数量", "dev_type": "开发者类型"},
        title="各品类新游中大厂 vs 独立开发者分布",
        color_discrete_map={"大厂": "#636EFA", "独立": "#EF553B"}
    )
    st.plotly_chart(fig4, use_container_width=True)
    st.caption("大厂扎堆的品类竞争激烈；独立开发者为主的品类可能存在未被满足的用户需求。")

# ---- 5. 进榜最快 Top 10 ----
st.divider()
st.subheader("⑤ 进榜最快的新游 Top 10")

fastest = pd.read_sql_query(f"""
    SELECT g.app_id, g.title, g.developer, g.genre, g.released,
           gs.days_to_chart, gs.days_since_release,
           gs.reviews_growth_7d, cr.rank as best_rank,
           CASE WHEN dev.total >= 5 THEN '🏢 大厂' ELSE '🧑‍💻 独立' END AS dev_type
    FROM games g
    JOIN growth_signals gs ON gs.app_id = g.app_id AND gs.signal_date = ?
    JOIN (
        SELECT app_id, MIN(rank) as rank FROM chart_rankings
        WHERE snapshot_date = ? GROUP BY app_id
    ) cr ON cr.app_id = g.app_id
    JOIN (
        SELECT developer, count(*) as total FROM games GROUP BY developer
    ) dev ON dev.developer = g.developer
    WHERE g.released >= ?
      AND gs.days_to_chart IS NOT NULL AND gs.days_to_chart >= 0
      AND g.genre IS NOT NULL {chart_filter}
    ORDER BY gs.days_to_chart ASC
    LIMIT 10
""", conn, params=(latest, latest, cutoff))

if not fastest.empty:
    fastest["7日评论增长"] = fastest["reviews_growth_7d"].fillna(0).apply(
        lambda x: f"+{x:.1f}%"
    )
    fastest["商店"] = fastest["app_id"].apply(store_url)
    fastest["品类双语"] = fastest["genre"].apply(bilingual)
    disp = fastest[[
        "title", "商店", "dev_type", "developer", "品类双语",
        "released", "days_since_release", "days_to_chart",
        "best_rank", "7日评论增长"
    ]].copy()
    disp.columns = [
        "游戏名称", "商店", "类型", "开发者", "品类",
        "上架日期", "上架天数", "进榜天数",
        "当前最佳排名", "7日评论增长"
    ]
    st.dataframe(
        disp,
        column_config={"商店": st.column_config.LinkColumn("商店", display_text="🔗")},
        use_container_width=True,
        hide_index=True,
    )

conn.close()
