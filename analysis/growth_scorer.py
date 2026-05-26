"""
growth_scorer.py — 每日增长信号计算

指标说明：
- today_heat_score   今日热度分（排名 + 评论数 + 评分），第 1 天即可使用
- growth_score       综合增长分（7日增长趋势），需要 7 天历史数据
- rank_delta_7d      7日排名变化（负=上升）
- reviews_growth_7d  7日评论增长率
- days_to_chart      上架到首次进榜天数
- is_new_game        上架 ≤90 天为新游
"""
import math
from datetime import date, timedelta
from db import get_conn

TODAY = date.today().isoformat()
D7_AGO = (date.today() - timedelta(days=7)).isoformat()


def _heat_score(rank: int | None, reviews: int | None, score: float | None) -> float:
    """今日热度分：即使第 1 天也能计算，范围约 0-1。"""
    # 排名分：Top 1=1.0，Top 500=0，超出为 0
    rank_s = max(0.0, (500 - (rank or 500)) / 500)
    # 评论数分：对数缩放，100 万评论 ≈ 1.0
    review_s = min(1.0, math.log10((reviews or 0) + 1) / 6)
    # 评分分：1-5 → 0-1
    rating_s = max(0.0, ((score or 3.0) - 1) / 4)
    return round(rank_s * 0.5 + review_s * 0.3 + rating_s * 0.2, 4)


def compute_signals() -> None:
    conn = get_conn()
    cur = conn.cursor()

    today_apps = cur.execute("""
        SELECT DISTINCT app_id FROM chart_rankings WHERE snapshot_date = ?
    """, (TODAY,)).fetchall()

    if not today_apps:
        print(f"[growth_scorer] 今日 ({TODAY}) 无榜单数据，跳过。")
        return

    inserted = 0
    for (app_id,) in today_apps:

        # 今日快照
        snap_today = cur.execute("""
            SELECT reviews, score FROM daily_snapshots
            WHERE app_id = ? AND snapshot_date = ?
        """, (app_id, TODAY)).fetchone()

        # 7 天前快照
        snap_7d = cur.execute("""
            SELECT reviews FROM daily_snapshots
            WHERE app_id = ? AND snapshot_date <= ?
            ORDER BY snapshot_date DESC LIMIT 1
        """, (app_id, D7_AGO)).fetchone()

        # 今日最佳排名
        rank_row = cur.execute("""
            SELECT MIN(rank) as best_rank FROM chart_rankings
            WHERE app_id = ? AND snapshot_date = ?
        """, (app_id, TODAY)).fetchone()

        # 7 天前最佳排名
        rank_7d_row = cur.execute("""
            SELECT MIN(rank) as best_rank FROM chart_rankings
            WHERE app_id = ? AND snapshot_date <= ?
        """, (app_id, D7_AGO)).fetchone()

        # 游戏信息
        game_row = cur.execute("""
            SELECT released, first_seen_at FROM games WHERE app_id = ?
        """, (app_id,)).fetchone()

        # 首次进榜日期
        first_chart = cur.execute("""
            SELECT MIN(snapshot_date) as first_date FROM chart_rankings
            WHERE app_id = ?
        """, (app_id,)).fetchone()

        # ── 基础指标 ──
        rank_today = rank_row["best_rank"] if rank_row else None
        rank_7d    = rank_7d_row["best_rank"] if rank_7d_row else None

        reviews_today = snap_today["reviews"] if snap_today else None
        score_today   = snap_today["score"]   if snap_today else None
        reviews_7d    = snap_7d["reviews"]    if snap_7d    else None

        # ── 今日热度分（第 1 天即可使用）──
        today_heat_score = _heat_score(rank_today, reviews_today, score_today)

        # ── 7 日增长指标（需历史数据）──
        rank_delta_7d = None
        if rank_today is not None and rank_7d is not None:
            rank_delta_7d = rank_today - rank_7d   # 负数 = 排名上升

        reviews_growth_7d = None
        if reviews_today and reviews_7d and reviews_7d > 0:
            reviews_growth_7d = (reviews_today - reviews_7d) / reviews_7d * 100

        # ── 新游判定 ──
        is_new_game = 0
        days_since_release = None
        days_to_chart = None

        if game_row and game_row["released"]:
            try:
                rel = date.fromisoformat(game_row["released"][:10])
                days_since_release = (date.today() - rel).days
                is_new_game = 1 if days_since_release <= 90 else 0

                if first_chart and first_chart["first_date"]:
                    days_to_chart = max(
                        0, (date.fromisoformat(first_chart["first_date"]) - rel).days
                    )
            except ValueError:
                pass

        # ── 新游爆发分 ──
        burst_score = None
        if is_new_game and rank_today is not None:
            growth_w  = (reviews_growth_7d or 0) * 0.4
            rank_w    = (-rank_today / 200) * 0.3
            speed_w   = (max(0, (90 - (days_to_chart or 90)) / 90)) * 0.3
            burst_score = round(growth_w + rank_w + speed_w, 4)

        # ── 综合增长分 ──
        # 有 7 天历史时用趋势，没有时退化为今日热度分
        has_history = (reviews_growth_7d is not None or rank_delta_7d is not None)
        if has_history:
            rg = reviews_growth_7d or 0
            rd = (-(rank_delta_7d or 0)) / 200
            bs = burst_score or 0
            growth_score = round(rg * 0.4 + rd * 0.4 + bs * 0.2, 4)
        else:
            growth_score = today_heat_score   # 降级为热度分

        cur.execute("""
            INSERT OR REPLACE INTO growth_signals
              (app_id, signal_date, rank_delta_7d, reviews_growth_7d,
               is_new_game, days_since_release, days_to_chart,
               new_game_burst_score, growth_score, today_heat_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (app_id, TODAY,
              rank_delta_7d, reviews_growth_7d,
              is_new_game, days_since_release, days_to_chart,
              burst_score, growth_score, today_heat_score))
        inserted += 1

    conn.commit()
    conn.close()
    print(f"[growth_scorer] 写入 {inserted} 条增长信号 ({TODAY})")


if __name__ == "__main__":
    compute_signals()
