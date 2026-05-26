"""
genre_map.py — Google Play 游戏品类英中映射

覆盖两种格式：
  • games.genre         → "Action", "Puzzle" （普通英文）
  • chart_rankings.category → "GAME_ACTION", "GAME_PUZZLE" （API category 格式）

所有 Dashboard 页面统一 import 此模块。
"""

# ── games.genre 映射（普通英文）──
GENRE_ZH: dict[str, str] = {
    "Action":       "动作",
    "Adventure":    "冒险",
    "Arcade":       "街机",
    "Board":        "棋盘",
    "Card":         "卡牌",
    "Casino":       "赌场",
    "Casual":       "休闲",
    "Educational":  "教育",
    "Music":        "音乐",
    "Puzzle":       "益智",
    "Racing":       "竞速",
    "Role Playing": "角色扮演",
    "Simulation":   "模拟",
    "Sports":       "体育",
    "Strategy":     "策略",
    "Trivia":       "问答",
    "Word":         "文字",
}

# ── chart_rankings.category 映射（API 格式）──
CATEGORY_ZH: dict[str, str] = {
    "GAME":               "全品类",
    "GAME_ACTION":        "动作",
    "GAME_ADVENTURE":     "冒险",
    "GAME_ARCADE":        "街机",
    "GAME_BOARD":         "棋盘",
    "GAME_CARD":          "卡牌",
    "GAME_CASINO":        "赌场",
    "GAME_CASUAL":        "休闲",
    "GAME_EDUCATIONAL":   "教育",
    "GAME_MUSIC":         "音乐",
    "GAME_PUZZLE":        "益智",
    "GAME_RACING":        "竞速",
    "GAME_ROLE_PLAYING":  "角色扮演",
    "GAME_SIMULATION":    "模拟",
    "GAME_SPORTS":        "体育",
    "GAME_STRATEGY":      "策略",
    "GAME_TRIVIA":        "问答",
    "GAME_WORD":          "文字",
}


# ── 通用函数 ──

def zh(genre: str | None, *, category: bool = False) -> str:
    """返回中文名；未知品类原样返回。
    category=True 时按 CATEGORY_ZH 映射（GAME_ACTION 格式）。
    """
    if not genre:
        return "未知"
    mapping = CATEGORY_ZH if category else GENRE_ZH
    return mapping.get(genre, genre)


def bilingual(genre: str | None, *, category: bool = False) -> str:
    """返回 'Action（动作）' 或 'GAME_ACTION（动作）' 格式。"""
    if not genre:
        return "未知"
    cn = zh(genre, category=category)
    return f"{genre}（{cn}）" if cn != genre else genre


def add_zh_column(df, src_col: str = "genre", dst_col: str = "品类",
                  *, category: bool = False) -> None:
    """原地在 DataFrame 添加双语品类列。"""
    df[dst_col] = df[src_col].apply(lambda g: bilingual(g, category=category))


def genre_options(raw_genres: list[str], *, category: bool = False) -> list[str]:
    """生成下拉框选项列表（双语格式，前置「全部」）。"""
    return ["全部"] + [bilingual(g, category=category) for g in sorted(raw_genres)]


def store_url(app_id: str) -> str:
    """生成 Google Play 商店链接。"""
    return f"https://play.google.com/store/apps/details?id={app_id}"


def parse_genre_filter(selected: str) -> str | None:
    """从双语选项解析回英文原始值，用于 SQL WHERE。"""
    if selected == "全部":
        return None
    return selected.split("（")[0].strip()
