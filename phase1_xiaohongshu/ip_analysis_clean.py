"""
泡泡玛特 IP 热度分析 — 数据清洗模块
提供日期解析、likes转换、数据加载等公共函数
"""
import sqlite3
import json
import re
import math
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

BASE_DIR = Path(r'C:\Users\lxxxxxx\Desktop\个人项目\popmart')
DB_PATH = BASE_DIR / 'popmart_comments.db'
CHART_DATA_PATH = BASE_DIR / 'chart_data.json'

# 爬虫运行日期，用于反推"N天前"的绝对日期
SCRAPE_DATE = datetime(2026, 3, 25)


# ─── 工具函数 ───────────────────────────────

def parse_likes(s):
    """点赞字符串 → 整数"""
    if not s or str(s) in ('赞', '', 'None'):
        return 0
    s = str(s).strip().replace(',', '')
    if '万' in s:
        return int(float(s.replace('万', '')) * 10000)
    try:
        return int(float(s))
    except Exception:
        return 0


def calc_heat(likes_list):
    """热度指数 = 平均赞 × ln(帖子数+1) × (1 + 最高赞/(平均赞+1)×0.1)"""
    n = len(likes_list)
    if n == 0:
        return 0.0
    avg = sum(likes_list) / n
    mx = max(likes_list)
    return avg * math.log(n + 1) * (1 + mx / (avg + 1) * 0.1)


def heat_level(h):
    if h >= 10000: return '极热'
    if h >= 5000:  return '高热'
    if h >= 2000:  return '中热'
    if h >= 500:   return '低热'
    return '冷门'


def parse_comment_date(raw, scrape_date=None):
    """
    统一三种评论日期格式，返回 (date_str 'YYYY-MM-DD', location_str or '')

    格式1: '2026-02-07 00:13' 或 '2026-02-07' → 直接用
    格式2: '02-08陕西' → 推断年份，提取地区
    格式3: '5天前内蒙古' / '昨天 22:39浙江' → 用scrape_date反推
    """
    if scrape_date is None:
        scrape_date = SCRAPE_DATE
    if not raw or not isinstance(raw, str):
        return None, ''

    raw = raw.strip()

    # 格式1: YYYY-MM-DD ...
    m = re.match(r'^(\d{4}-\d{2}-\d{2})', raw)
    if m:
        return m.group(1), ''  # location在DB的location字段里

    # 格式3: 相对时间 (先于格式2判断，因为格式2的regex更宽)
    # "5天前内蒙古", "昨天 22:39浙江", "1天前云南", "3小时前上海", "N分钟前XX"
    m_rel = re.match(r'^(\d+)天前(.*)$', raw)
    if m_rel:
        days = int(m_rel.group(1))
        loc = m_rel.group(2).strip()
        dt = scrape_date - timedelta(days=days)
        return dt.strftime('%Y-%m-%d'), loc

    m_rel = re.match(r'^昨天\s*\S*(.*)$', raw)
    if m_rel:
        dt = scrape_date - timedelta(days=1)
        loc = re.sub(r'^[\d:]+', '', m_rel.group(1)).strip()
        return dt.strftime('%Y-%m-%d'), loc

    m_rel = re.match(r'^(\d+)小时前(.*)$', raw)
    if m_rel:
        return scrape_date.strftime('%Y-%m-%d'), m_rel.group(2).strip()

    m_rel = re.match(r'^(\d+)分钟前(.*)$', raw)
    if m_rel:
        return scrape_date.strftime('%Y-%m-%d'), m_rel.group(2).strip()

    # 格式2: MM-DD + 地区 (如 "02-08陕西", "03-10上海")
    m2 = re.match(r'^(\d{2})-(\d{2})(.*)$', raw)
    if m2:
        month = int(m2.group(1))
        day = int(m2.group(2))
        loc = m2.group(3).strip()
        # 推断年份：月份 <= scrape_date的月 → 同年，否则去年
        year = scrape_date.year if month <= scrape_date.month else scrape_date.year - 1
        try:
            dt = datetime(year, month, day)
            return dt.strftime('%Y-%m-%d'), loc
        except ValueError:
            return None, loc

    return None, ''


# ─── 数据加载 ───────────────────────────────

def load_chart_data():
    """加载 chart_data.json → DataFrame (ip, date, likes, ym)"""
    with open(CHART_DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    df = pd.DataFrame(data['posts'])
    df['likes'] = df['likes'].astype(int)
    df['ym'] = df['date'].str[:7]
    return df


def load_db_data():
    """
    加载SQLite数据并清洗，返回 (posts_df, comments_df)

    posts_df 列: id, title, ip, likes(int), post_date, note_id, comment_count
    comments_df 列: id, post_id, ip, comment_date(clean), comment_likes(int),
                    comment_text, location(merged), ym
    """
    conn = sqlite3.connect(str(DB_PATH))

    # 帖子
    posts_df = pd.read_sql_query(
        'SELECT id, title, ip, likes, post_date, note_id FROM posts', conn
    )
    posts_df['likes'] = posts_df['likes'].apply(parse_likes)

    # 每帖实际评论数
    comment_counts = pd.read_sql_query(
        'SELECT post_id, COUNT(*) as comment_count FROM comments GROUP BY post_id', conn
    )
    posts_df = posts_df.merge(comment_counts, left_on='id', right_on='post_id', how='left')
    posts_df['comment_count'] = posts_df['comment_count'].fillna(0).astype(int)
    posts_df.drop(columns=['post_id'], inplace=True, errors='ignore')

    # 评论
    comments_df = pd.read_sql_query('''
        SELECT c.id, c.post_id, c.comment_date, c.comment_likes,
               c.comment_text, c.location as db_location, p.ip
        FROM comments c
        JOIN posts p ON c.post_id = p.id
    ''', conn)
    conn.close()

    # 清洗评论日期并合并location
    clean_dates = []
    clean_locs = []
    for _, row in comments_df.iterrows():
        dt, loc = parse_comment_date(row['comment_date'])
        clean_dates.append(dt)
        # 优先用DB的location字段，其次用从日期字符串提取的
        final_loc = row['db_location'] if row['db_location'] else loc
        clean_locs.append(final_loc if final_loc else '')

    comments_df['clean_date'] = clean_dates
    comments_df['location'] = clean_locs
    comments_df['comment_likes'] = comments_df['comment_likes'].apply(parse_likes)

    # 去掉无法解析日期的行
    before = len(comments_df)
    comments_df = comments_df.dropna(subset=['clean_date']).copy()
    dropped = before - len(comments_df)
    if dropped > 0:
        print(f'  [清洗] 丢弃 {dropped} 条无法解析日期的评论')

    comments_df['ym'] = comments_df['clean_date'].str[:7]

    # 补全 posts 的 post_date（用最早评论日期推算）
    earliest_comment = comments_df.groupby('post_id')['clean_date'].min().reset_index()
    earliest_comment.columns = ['id', 'inferred_date']
    posts_df = posts_df.merge(earliest_comment, on='id', how='left')
    posts_df['post_date_final'] = posts_df['post_date'].fillna(posts_df['inferred_date'])
    posts_df['ym'] = posts_df['post_date_final'].apply(
        lambda x: str(x)[:7] if pd.notna(x) and str(x) >= '2024' else ''
    )

    return posts_df, comments_df


def load_all():
    """加载全部数据，返回 (chart_df, posts_df, comments_df)"""
    print('加载 chart_data.json ...')
    chart_df = load_chart_data()
    print(f'  {len(chart_df)} 条帖子, {chart_df["ym"].nunique()} 个月')

    print('加载并清洗 SQLite 数据 ...')
    posts_df, comments_df = load_db_data()
    print(f'  {len(posts_df)} 帖子, {len(comments_df)} 条评论')
    print(f'  评论日期范围: {comments_df["clean_date"].min()} ~ {comments_df["clean_date"].max()}')

    return chart_df, posts_df, comments_df


if __name__ == '__main__':
    chart_df, posts_df, comments_df = load_all()
    print('\n--- chart_data IP分布 ---')
    print(chart_df['ip'].value_counts().to_string())
    print('\n--- DB评论 IP分布 ---')
    print(comments_df['ip'].value_counts().to_string())
    print('\n--- 评论月度分布 ---')
    print(comments_df['ym'].value_counts().sort_index().to_string())
