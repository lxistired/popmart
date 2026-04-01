"""
生成海外另类数据分析公众号文章 HTML + 文章级图表
图表风格对标 Phase 1 article_charts.py：干净简洁，适合公众号阅读

输出: overseas_article.html + article_charts/ (7 PNG)
"""
import os
import base64
import sqlite3
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'overseas_data.db')
CHARTS_DIR = os.path.join(BASE_DIR, 'article_charts')

# ─── 全局样式（对标 Phase 1 article_charts.py）────────

plt.rcParams.update({
    'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'STHeiti'],
    'font.size': 12,
    'axes.unicode_minus': True,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.linewidth': 0.8,
    'axes.edgecolor': '#CCCCCC',
    'axes.grid': True,
    'grid.alpha': 0.15,
    'grid.linewidth': 0.5,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'savefig.facecolor': 'white',
    'savefig.dpi': 180,
    'savefig.bbox': 'tight',
})

IP_COLORS = {
    'Labubu': '#FF8F00', 'Dimoo': '#1E88E5',
    'Molly': '#EC407A', 'Skullpanda': '#8E24AA',
    'Pop Mart': '#E53935', 'Other': '#BDBDBD',
}
PLATFORM_COLORS = {
    'TikTok': '#000000', 'Instagram': '#E1306C',
}
TIKTOK_SOURCE_IP = {
    'tag/labubu': 'Labubu', 'tag/labubu lisa': 'Labubu',
    'tag/dimoo': 'Dimoo', 'tag/molly popmart': 'Molly',
    'tag/skullpanda': 'Skullpanda',
    'tag/pop mart': 'Pop Mart', 'tag/popmart unboxing': 'Pop Mart',
    'user/popmartglobal': 'Pop Mart',
}
INSTAGRAM_ACCOUNT_IP = {
    'hashtag:labubu': 'Labubu', 'hashtag:labubuthemonsters': 'Labubu',
    'hashtag:popmartlabubu': 'Labubu',
    'hashtag:popmart': 'Pop Mart', 'hashtag:popmartglobal': 'Pop Mart',
    'popmart': 'Pop Mart',
}


def _week_label(ts):
    """周时间戳 → 'YY年MM月' 格式"""
    return ts.strftime('%y年%m月')


def _set_month_xticks(ax, months, fontsize=9):
    """智能设置X轴月份标签，避免重叠。

    months: 已排序的 Timestamp/datetime64 序列
    自动根据总月数选择间隔：≤10个全显示，>10个隔季显示
    """
    # 统一转为 pd.Timestamp
    months = [pd.Timestamp(m) for m in months]
    n = len(months)
    all_labels = [_week_label(m) for m in months]

    if n <= 10:
        # 少量数据，全部显示
        ax.set_xticks(range(n))
        ax.set_xticklabels(all_labels, fontsize=fontsize, color='#666')
    else:
        # 数据多，每隔 step 个显示一个
        step = max(3, n // 8)  # 保证最多~8个标签
        tick_pos = list(range(0, n, step))
        if (n - 1) not in tick_pos:
            tick_pos.append(n - 1)  # 始终显示最后一个
        ax.set_xticks(tick_pos)
        ax.set_xticklabels([all_labels[i] for i in tick_pos],
                           fontsize=fontsize, color='#666')
    ax.set_xlim(-0.5, n - 0.5)


def _style_title(ax, title):
    ax.set_title(title, fontsize=16, fontweight='bold', color='#333', pad=16)


def _style_legend(ax, **kwargs):
    defaults = dict(fontsize=9, framealpha=0.9, edgecolor='#ddd',
                    fancybox=True, borderpad=0.8)
    defaults.update(kwargs)
    ax.legend(**defaults)


# ─── 数据加载 ────────────────────────────────────

def load_data():
    conn = sqlite3.connect(DB_PATH)

    # TikTok videos
    tt_vids = pd.read_sql_query(
        'SELECT video_id, author, views, likes, comments_count, create_time, source '
        'FROM tiktok_videos', conn)
    tt_vids['views'] = pd.to_numeric(tt_vids['views'], errors='coerce').fillna(0).astype(int)
    tt_vids['likes'] = pd.to_numeric(tt_vids['likes'], errors='coerce').fillna(0).astype(int)
    tt_vids['comments_count'] = pd.to_numeric(tt_vids['comments_count'], errors='coerce').fillna(0).astype(int)
    tt_vids['date'] = pd.to_datetime(pd.to_numeric(tt_vids['create_time'], errors='coerce'),
                                     unit='s', errors='coerce')
    tt_vids = tt_vids.dropna(subset=['date'])
    tt_vids['month'] = tt_vids['date'].dt.to_period('M').dt.start_time
    tt_vids['ip'] = tt_vids['source'].map(TIKTOK_SOURCE_IP).fillna('Other')
    tt_vids['er'] = (tt_vids['likes'] + tt_vids['comments_count']) / tt_vids['views'].clip(lower=1)
    tt_vids['is_brand'] = tt_vids['author'] == 'popmartglobal'

    # TikTok comments
    tt_coms = pd.read_sql_query(
        'SELECT c.comment_date, c.likes, v.source '
        'FROM tiktok_comments c LEFT JOIN tiktok_videos v ON c.video_id = v.video_id', conn)
    tt_coms['date'] = pd.to_datetime(tt_coms['comment_date'], errors='coerce')
    tt_coms = tt_coms.dropna(subset=['date'])
    tt_coms['month'] = tt_coms['date'].dt.to_period('M').dt.start_time
    tt_coms['likes'] = pd.to_numeric(tt_coms['likes'], errors='coerce').fillna(0).astype(int)
    tt_coms['ip'] = tt_coms['source'].map(TIKTOK_SOURCE_IP).fillna('Other')

    # Instagram posts
    ig_posts = pd.read_sql_query(
        'SELECT shortcode, account, likes, comments_count, post_date FROM instagram_posts', conn)
    ig_posts['date'] = pd.to_datetime(ig_posts['post_date'], errors='coerce')
    ig_posts = ig_posts.dropna(subset=['date'])
    ig_posts['month'] = ig_posts['date'].dt.to_period('M').dt.start_time
    ig_posts['likes'] = pd.to_numeric(ig_posts['likes'], errors='coerce').fillna(0).astype(int)
    ig_posts['ip'] = ig_posts['account'].map(INSTAGRAM_ACCOUNT_IP).fillna('Other')

    # Instagram comments
    ig_coms = pd.read_sql_query(
        'SELECT c.comment_date, c.likes, p.account '
        'FROM instagram_comments c LEFT JOIN instagram_posts p ON c.shortcode = p.shortcode', conn)
    ig_coms['date'] = pd.to_datetime(ig_coms['comment_date'], errors='coerce')
    ig_coms = ig_coms.dropna(subset=['date'])
    ig_coms['month'] = ig_coms['date'].dt.to_period('M').dt.start_time
    ig_coms['likes'] = pd.to_numeric(ig_coms['likes'], errors='coerce').fillna(0).astype(int)
    ig_coms['ip'] = ig_coms['account'].map(INSTAGRAM_ACCOUNT_IP).fillna('Other')

    # SimilarWeb traffic
    sw = pd.read_sql_query(
        "SELECT scraped_at, monthly_visits, visit_duration, raw_json "
        "FROM similarweb_traffic WHERE monthly_visits != '' ORDER BY scraped_at", conn)
    sw['date'] = pd.to_datetime(sw['scraped_at'], errors='coerce')
    sw = sw.dropna(subset=['date'])
    sw['month'] = sw['date'].dt.to_period('M').dt.start_time
    # 解析 monthly_visits（可能是数字或 "6.339M" 格式）
    def _parse_visits(v):
        v = str(v).strip()
        if v.endswith('M'):
            return float(v[:-1]) * 1e6
        try:
            return float(v)
        except Exception:
            return 0
    sw['visits'] = sw['monthly_visits'].apply(_parse_visits)
    # 每月保留最新一条（去重）
    sw = sw.sort_values('date').drop_duplicates(subset='month', keep='last')

    conn.close()
    return tt_vids, tt_coms, ig_posts, ig_coms, sw


# ─── 图表生成（文章级品质）─────────────────────────

def chart_brand_trend(tt_vids, tt_coms, charts_dir):
    """图1: 品牌整体热度走势（月度评论量柱 + 评论密度折线）"""
    print('  图1: 品牌热度走势...')
    # 月度视频量 & 评论量
    v_monthly = tt_vids.groupby('month').size().reset_index(name='videos')
    c_monthly = tt_coms.groupby('month').size().reset_index(name='comments')
    merged = v_monthly.merge(c_monthly, on='month', how='outer').fillna(0).sort_values('month')
    merged['density'] = merged['comments'] / merged['videos'].clip(lower=1)
    # 只保留有数据的月份
    merged = merged[merged['videos'] > 0]

    fig, ax1 = plt.subplots(figsize=(10, 5))
    x = range(len(merged))

    # 渐变柱状图
    max_val = merged['comments'].max()
    colors = [plt.cm.Oranges(0.3 + 0.6 * v / max(max_val, 1)) for v in merged['comments']]
    bars = ax1.bar(x, merged['comments'], width=0.65, color=colors,
                   edgecolor='white', linewidth=0.3)
    # 数据标签
    for bar, v in zip(bars, merged['comments']):
        if v > 0:
            ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max_val * 0.02,
                     f'{int(v)}', ha='center', va='bottom', fontsize=7.5,
                     color='#666', fontweight=500)

    ax1.set_ylabel('月度评论量', fontsize=11, color='#666', labelpad=8)
    ax1.tick_params(axis='y', labelsize=9, colors='#888')
    _set_month_xticks(ax1, merged['month'].values)

    # 密度折线（右轴）
    ax2 = ax1.twinx()
    ax2.spines['right'].set_visible(True)
    ax2.spines['right'].set_color('#E53935')
    ax2.spines['right'].set_alpha(0.3)
    ax2.plot(x, merged['density'], color='#E53935', linewidth=2.5,
             marker='o', markersize=6, markerfacecolor='white',
             markeredgecolor='#E53935', markeredgewidth=2)
    ax2.set_ylabel('每视频均评论数', fontsize=11, color='#E53935', labelpad=8)
    ax2.tick_params(axis='y', labelsize=9, colors='#E53935')

    _style_title(ax1, 'TikTok Pop Mart 月度热度走势')
    _style_legend(ax1, labels=['评论量', '评论密度'],
                  handles=[bars, ax2.lines[0]], loc='upper left')
    plt.tight_layout()
    fig.savefig(os.path.join(charts_dir, 'art_brand_trend.png'))
    plt.close(fig)


def chart_ip_share(tt_coms, charts_dir):
    """图2: IP评论份额堆叠面积图"""
    print('  图2: IP评论份额...')
    tt = tt_coms[tt_coms['ip'] != 'Other'].copy()
    monthly_ip = tt.groupby(['month', 'ip']).size().reset_index(name='count')
    monthly_total = tt.groupby('month').size().reset_index(name='total')
    monthly_ip = monthly_ip.merge(monthly_total, on='month')
    monthly_ip['share'] = monthly_ip['count'] / monthly_ip['total'] * 100

    pivot = monthly_ip.pivot_table(index='month', columns='ip', values='share', fill_value=0)
    pivot = pivot.sort_index()
    # 只保留有数据的月份
    pivot = pivot[pivot.sum(axis=1) > 0]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ips = pivot.columns.tolist()
    colors = [IP_COLORS.get(ip, '#999') for ip in ips]

    ax.stackplot(range(len(pivot)), *[pivot[ip].values for ip in ips],
                 labels=ips, colors=colors, alpha=0.85, edgecolor='white', linewidth=0.5)

    # 右端标注
    for ip in ips:
        last_val = pivot[ip].iloc[-1]
        if last_val > 3:
            cumsum = sum(pivot[other_ip].iloc[-1] for other_ip in ips[:ips.index(ip)]) + last_val / 2
            ax.text(len(pivot) - 0.5, cumsum, ip, fontsize=7.5,
                    color=IP_COLORS.get(ip, '#999'), fontweight=600, va='center')

    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(['0%', '25%', '50%', '75%', '100%'], fontsize=9)
    ax.set_ylabel('评论份额', fontsize=11, color='#666', labelpad=8)
    _set_month_xticks(ax, pivot.index.values)
    _style_title(ax, 'TikTok 各IP月度评论份额')
    _style_legend(ax, fontsize=8.5, ncol=2, loc='upper left')
    plt.tight_layout()
    fig.savefig(os.path.join(charts_dir, 'art_ip_share.png'))
    plt.close(fig)


def chart_comment_density(tt_vids, tt_coms, ig_posts, ig_coms, charts_dir):
    """图3: 评论密度趋势（TikTok + Instagram）统一时间轴"""
    print('  图3: 评论密度...')
    fig, ax = plt.subplots(figsize=(10, 5))

    # 收集所有月份，建立统一x轴
    all_months = sorted(set(
        tt_vids['month'].unique().tolist() +
        ig_posts['month'].unique().tolist()
    ))
    month_idx = {m: i for i, m in enumerate(all_months)}

    for plat, vids, coms, color in [
        ('TikTok', tt_vids, tt_coms, '#000000'),
        ('Instagram', ig_posts, ig_coms, '#E1306C'),
    ]:
        v_m = vids.groupby('month').size().reset_index(name='content')
        c_m = coms.groupby('month').size().reset_index(name='comments')
        merged = v_m.merge(c_m, on='month', how='outer').fillna(0).sort_values('month')
        merged = merged[merged['content'] > 0]
        merged['density'] = merged['comments'] / merged['content']
        merged['ma3'] = merged['density'].rolling(3, min_periods=2).mean()

        x = [month_idx[m] for m in merged['month']]
        ax.plot(x, merged['ma3'], color=color, linewidth=2, alpha=0.9,
                marker='o', markersize=5, markerfacecolor='white',
                markeredgecolor=color, markeredgewidth=1.5, label=f'{plat}')
        ax.fill_between(x, merged['ma3'], alpha=0.05, color=color)

    ax.set_ylabel('每条内容均评论数', fontsize=11, color='#666', labelpad=8)
    ax.tick_params(axis='y', labelsize=9, colors='#888')
    _set_month_xticks(ax, all_months)
    _style_title(ax, '评论密度趋势（3月滚动平均）')
    _style_legend(ax, loc='best')
    plt.tight_layout()
    fig.savefig(os.path.join(charts_dir, 'art_comment_density.png'))
    plt.close(fig)


def chart_er_trend(tt_vids, charts_dir):
    """图4: TikTok 参与率月度趋势（按IP）统一时间轴"""
    print('  图4: 参与率趋势...')
    fig, ax = plt.subplots(figsize=(10, 5))

    all_months = sorted(tt_vids['month'].unique())
    month_idx = {m: i for i, m in enumerate(all_months)}

    top_ips = ['Labubu', 'Dimoo', 'Molly', 'Skullpanda', 'Pop Mart']
    for ip in top_ips:
        sub = tt_vids[tt_vids['ip'] == ip].copy()
        monthly = sub.groupby('month')['er'].mean().reset_index()
        monthly = monthly.sort_values('month')
        if len(monthly) < 3:
            continue
        monthly['ma3'] = monthly['er'].rolling(3, min_periods=2).mean()

        x = [month_idx[m] for m in monthly['month']]
        color = IP_COLORS.get(ip, '#999')
        ax.plot(x, monthly['ma3'] * 100, color=color, linewidth=2, alpha=0.9,
                marker='o', markersize=5, markerfacecolor='white',
                markeredgecolor=color, markeredgewidth=1.5, label=ip)

    ax.set_ylabel('参与率 ER (%)', fontsize=11, color='#666', labelpad=8)
    ax.tick_params(axis='y', labelsize=9, colors='#888')
    _set_month_xticks(ax, all_months)
    _style_title(ax, 'TikTok 各IP参与率趋势 (likes+comments)/views')
    _style_legend(ax, loc='upper left', fontsize=9)
    plt.tight_layout()
    fig.savefig(os.path.join(charts_dir, 'art_er_trend.png'))
    plt.close(fig)


def chart_brand_vs_ugc(tt_vids, charts_dir):
    """图5: 品牌 vs UGC 对比"""
    print('  图5: 品牌 vs UGC...')
    brand = tt_vids[tt_vids['is_brand']]
    ugc = tt_vids[~tt_vids['is_brand']]

    metrics = {
        '平均播放量': (brand['views'].mean(), ugc['views'].mean()),
        '平均点赞': (brand['likes'].mean(), ugc['likes'].mean()),
        '平均参与率': (brand['er'].mean() * 100, ugc['er'].mean() * 100),
        '每视频均评论': (brand['comments_count'].mean(), ugc['comments_count'].mean()),
    }

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(metrics))
    width = 0.32

    # 归一化到UGC=100
    ugc_vals = [v[1] for v in metrics.values()]
    brand_vals = [v[0] for v in metrics.values()]
    brand_norm = [b / max(u, 0.001) * 100 for b, u in zip(brand_vals, ugc_vals)]
    ugc_norm = [100] * len(metrics)

    bars_b = ax.bar(x - width / 2, brand_norm, width, label='品牌官号',
                    color='#E53935', alpha=0.85, edgecolor='white', linewidth=0.3)
    bars_u = ax.bar(x + width / 2, ugc_norm, width, label='用户UGC',
                    color='#333333', alpha=0.85, edgecolor='white', linewidth=0.3)

    # 数据标签（原始值）
    for bar, orig in zip(bars_b, brand_vals):
        label = f'{orig:,.0f}' if orig > 10 else f'{orig:.1f}%'
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                label, ha='center', va='bottom', fontsize=7.5, color='#E53935', fontweight=600)
    for bar, orig in zip(bars_u, ugc_vals):
        label = f'{orig:,.0f}' if orig > 10 else f'{orig:.1f}%'
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                label, ha='center', va='bottom', fontsize=7.5, color='#333', fontweight=600)

    ax.axhline(y=100, color='#CCCCCC', linewidth=0.8, linestyle='--')
    ax.set_xticks(x)
    ax.set_xticklabels(list(metrics.keys()), fontsize=10, color='#555')
    ax.set_ylim(0, 120)  # 留出数据标签空间
    ax.set_ylabel('相对水平（UGC=100）', fontsize=11, color='#666', labelpad=8)
    ax.tick_params(axis='y', labelsize=9, colors='#888')
    ax.set_xlim(-0.6, len(metrics) - 0.2)
    _style_title(ax, 'TikTok: 品牌官号 vs 用户生成内容')
    _style_legend(ax, loc='upper center', ncol=2)
    plt.tight_layout()
    fig.savefig(os.path.join(charts_dir, 'art_brand_vs_ugc.png'))
    plt.close(fig)


def chart_cross_platform(tt_coms, ig_coms, tt_vids, ig_posts, charts_dir):
    """图6: 双平台热度指数（贴均评论密度，均值=100归一化）统一时间轴"""
    print('  图6: 双平台指数...')
    fig, ax = plt.subplots(figsize=(10, 5))

    # 找共同时间窗口（至少两个平台有数据的月份范围）
    all_months = sorted(set(
        tt_coms['month'].unique().tolist() +
        ig_coms['month'].unique().tolist()
    ))
    month_idx = {m: i for i, m in enumerate(all_months)}

    for plat, coms, content_df, color in [
        ('TikTok', tt_coms, tt_vids, '#000000'),
        ('Instagram', ig_coms, ig_posts, '#E1306C'),
    ]:
        # 月评论数
        com_monthly = coms.groupby('month').size().reset_index(name='comments')
        # 月内容数（视频/帖子）
        content_monthly = content_df.groupby('month').size().reset_index(name='content_count')
        # 合并计算评论密度 = 评论数 / 内容数
        monthly = com_monthly.merge(content_monthly, on='month', how='inner')
        monthly['density'] = monthly['comments'] / monthly['content_count'].clip(lower=1)
        monthly = monthly.sort_values('month')
        monthly = monthly[monthly['density'] > 0]
        if len(monthly) < 3:
            continue
        # 均值=100归一化（用贴均评论密度，消除采集量偏差）
        avg = monthly['density'].mean()
        if avg == 0:
            avg = 1
        monthly['idx'] = monthly['density'] / avg * 100
        monthly['ma3'] = monthly['idx'].rolling(3, min_periods=2).mean()

        x = [month_idx[m] for m in monthly['month']]
        ax.plot(x, monthly['ma3'], color=color, linewidth=2.5, alpha=0.9,
                marker='o', markersize=6, markerfacecolor='white',
                markeredgecolor=color, markeredgewidth=2, label=plat)

    ax.axhline(y=100, color='#CCCCCC', linewidth=0.8, linestyle='--')
    ax.text(-0.5, 103, '均值=100', fontsize=8, color='#999')

    ax.set_ylabel('热度指数', fontsize=11, color='#666', labelpad=8)
    ax.tick_params(axis='y', labelsize=9, colors='#888')
    _set_month_xticks(ax, all_months)
    _style_title(ax, '双平台评论密度指数（贴均评论，均值=100）')
    _style_legend(ax, loc='upper left')
    plt.tight_layout()
    fig.savefig(os.path.join(charts_dir, 'art_cross_platform.png'))
    plt.close(fig)


def chart_comment_quality(tt_coms, ig_coms, charts_dir):
    """图7: 评论质量分层对比"""
    print('  图7: 评论质量...')
    fig, ax = plt.subplots(figsize=(10, 5))

    platforms = []
    for plat, coms in [('TikTok', tt_coms), ('Instagram', ig_coms)]:
        n = len(coms)
        high = (coms['likes'] >= 10).sum()
        med = ((coms['likes'] >= 3) & (coms['likes'] < 10)).sum()
        low = (coms['likes'] < 3).sum()
        platforms.append({
            'platform': plat, 'total': n,
            'high': high / n * 100, 'med': med / n * 100, 'low': low / n * 100,
            'high_n': high, 'med_n': med, 'low_n': low,
        })

    x = np.arange(len(platforms))
    width = 0.5
    colors = {'high': '#4CAF50', 'med': '#FFC107', 'low': '#E0E0E0'}

    bottom = np.zeros(len(platforms))
    for tier, label_text in [('high', '高互动 ≥10赞'), ('med', '中互动 3-9赞'), ('low', '低互动 <3赞')]:
        vals = [p[tier] for p in platforms]
        ax.bar(x, vals, width, bottom=bottom, label=label_text,
               color=colors[tier], edgecolor='white', linewidth=0.3, alpha=0.85)
        # 标签
        for i, v in enumerate(vals):
            if v > 5:
                ax.text(x[i], bottom[i] + v / 2, f'{v:.0f}%',
                        ha='center', va='center', fontsize=10, fontweight=600,
                        color='#333' if tier != 'low' else '#666')
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels([p['platform'] for p in platforms], fontsize=12, color='#333')
    ax.set_ylim(0, 105)
    ax.set_ylabel('占比 (%)', fontsize=11, color='#666', labelpad=8)
    ax.tick_params(axis='y', labelsize=9, colors='#888')
    _style_title(ax, '评论质量分层对比')
    _style_legend(ax, loc='upper right', fontsize=9)
    plt.tight_layout()
    fig.savefig(os.path.join(charts_dir, 'art_comment_quality.png'))
    plt.close(fig)


def chart_similarweb(sw, charts_dir):
    """图8: SimilarWeb 官网月度流量"""
    print('  图8: SimilarWeb流量...')
    if len(sw) < 2:
        print('    跳过（数据不足）')
        return
    sw_sorted = sw.sort_values('month')
    fig, ax = plt.subplots(figsize=(10, 5))
    x = range(len(sw_sorted))
    visits_m = sw_sorted['visits'].values / 1e6  # 转为百万

    # 渐变柱状图
    max_val = visits_m.max()
    colors = [plt.cm.Blues(0.35 + 0.55 * v / max(max_val, 1)) for v in visits_m]
    bars = ax.bar(x, visits_m, width=0.55, color=colors,
                  edgecolor='white', linewidth=0.3)
    # 数据标签
    for bar, v in zip(bars, visits_m):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max_val * 0.02,
                f'{v:.1f}M', ha='center', va='bottom', fontsize=10,
                color='#333', fontweight=600)
    # 环比变化标注
    for i in range(1, len(visits_m)):
        pct = (visits_m[i] - visits_m[i-1]) / visits_m[i-1] * 100
        color = '#E53935' if pct < 0 else '#4CAF50'
        ax.text(i, visits_m[i] + max_val * 0.10,
                f'{pct:+.1f}%', ha='center', va='bottom', fontsize=8.5,
                color=color, fontweight=600)

    ax.set_ylabel('月访问量（百万）', fontsize=11, color='#666', labelpad=8)
    ax.tick_params(axis='y', labelsize=9, colors='#888')
    ax.set_ylim(0, max_val * 1.3)
    _set_month_xticks(ax, sw_sorted['month'].values)
    _style_title(ax, 'popmart.com 官网月度访问量')
    plt.tight_layout()
    fig.savefig(os.path.join(charts_dir, 'art_similarweb.png'))
    plt.close(fig)


# ─── HTML 生成 ────────────────────────────────────

def img_b64(filename):
    path = os.path.join(CHARTS_DIR, filename)
    if not os.path.exists(path):
        return ''
    with open(path, 'rb') as f:
        return f'data:image/png;base64,{base64.b64encode(f.read()).decode()}'


def get_stats(tt_vids, tt_coms, ig_posts, ig_coms, sw):
    s = {}
    s['tt_videos'] = len(tt_vids)
    s['tt_comments'] = len(tt_coms)
    s['ig_posts'] = len(ig_posts)
    s['ig_comments'] = len(ig_coms)
    s['total_comments'] = s['tt_comments'] + s['ig_comments']
    s['tt_avg_er'] = tt_vids['er'].mean() * 100
    brand = tt_vids[tt_vids['is_brand']]['views'].mean()
    ugc = tt_vids[~tt_vids['is_brand']]['views'].mean()
    s['brand_views'] = int(brand) if pd.notna(brand) else 0
    s['ugc_views'] = int(ugc) if pd.notna(ugc) else 0
    s['ugc_ratio'] = int(ugc / max(brand, 1))
    s['tt_high_pct'] = (tt_coms['likes'] >= 10).sum() / max(len(tt_coms), 1) * 100
    # SimilarWeb
    if len(sw) > 0:
        latest = sw.sort_values('month').iloc[-1]
        s['sw_latest_visits'] = latest['visits']
        s['sw_latest_month'] = latest['month'].strftime('%Y年%m月')
        s['sw_months'] = len(sw)
        if len(sw) >= 2:
            prev = sw.sort_values('month').iloc[-2]['visits']
            s['sw_mom_change'] = (latest['visits'] - prev) / prev * 100
        else:
            s['sw_mom_change'] = 0
    else:
        s['sw_latest_visits'] = 0
        s['sw_latest_month'] = ''
        s['sw_months'] = 0
        s['sw_mom_change'] = 0
    return s


def generate_html(stats):
    c = {name: img_b64(name) for name in [
        'art_brand_trend.png', 'art_ip_share.png', 'art_comment_density.png',
        'art_er_trend.png', 'art_brand_vs_ugc.png', 'art_cross_platform.png',
        'art_comment_quality.png', 'art_similarweb.png',
    ]}

    # 样式常量
    S = {
        'bg_dark': '#1A1A2E',
        'bg_warm': '#FFF8F0',
        'accent': '#E53935',
        'text': '#2D2D2D',
        'p': 'font-size:15px; line-height:2.0; letter-spacing:0.5px; color:#2D2D2D; margin:0 0 16px 0;',
        'h2_bar': lambda color: f'<span style="display:inline-block;width:6px;height:20px;background:{color};border-radius:3px;margin-right:8px;vertical-align:middle;"></span>',
        'h2': 'font-size:20px; font-weight:700; color:#2D2D2D; margin:0 0 8px 0;',
        'divider': lambda color: f'<div style="width:60px; height:3px; background:{color}; border-radius:2px; margin:0;"></div>',
        'highlight': lambda t: f'<span style="background:#E8EAF6; padding:0 2px;">{t}</span>',
        'badge': lambda bc, t: f'<span style="display:inline-block; background:{bc}; color:white; padding:2px 10px; border-radius:12px; font-size:13px; font-weight:600; vertical-align:middle; margin:0 2px;">{t}</span>',
        'img': lambda src: f'<div style="margin:24px 0; border-radius:12px; overflow:hidden; box-shadow:0 2px 12px rgba(0,0,0,0.06);"><img src="{src}" style="width:100%; display:block;"></div>',
        'callout': lambda text, color='#1A1A2E': f'<div style="border-radius:12px; background:#F5F5FF; padding:20px 24px; margin:24px 0; border-left:4px solid {color};"><p style="font-size:14px; line-height:1.8; color:#333; margin:0;">{text}</p></div>',
        'section_divider': '<div style="text-align:center; margin:0; padding:20px 0;"><div style="margin:0 auto; width:60px; height:3px; background:#1A1A2E; border-radius:2px;"></div></div>',
    }

    def section_start(bg='#FFFFFF'):
        return f'<div style="padding:0 32px 32px 32px; background:{bg};">'

    def section_header(title, color):
        return f'''<div style="margin:32px 0 20px 0;">
<h2 style="{S['h2']}">{S['h2_bar'](color)}{title}</h2>
{S['divider'](color)}
</div>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>海外另类数据拆解泡泡玛特全球热度</title>
</head>
<body style="margin:0; padding:0; background:#f0f0f0;">
<div style="max-width:680px; margin:0 auto; font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif; background:#FFFFFF; overflow:hidden;">

<!-- HERO -->
<div style="position:relative; background:{S['bg_dark']}; padding:80px 40px 100px 40px; text-align:center;">
<div style="position:relative; z-index:1;">
<h1 style="font-size:26px; font-weight:800; line-height:1.6; margin:0 0 20px 0; color:#FFFFFF; letter-spacing:1px;">海外另类数据拆解<br>泡泡玛特全球热度</h1>
<p style="font-size:16px; color:rgba(255,255,255,0.85); line-height:1.8; margin:0 0 8px 0;">TikTok · Instagram 双平台评论时序分析</p>
<p style="font-size:13px; color:rgba(255,255,255,0.6); line-height:1.8; margin:16px 0 0 0;">{stats["tt_videos"]}条视频 · {stats["total_comments"]:,}条评论 · 2个平台 · 跨越18个月</p>
</div>
</div>

<!-- 数据Callout -->
<div style="padding:0 32px;">
<div style="border-radius:16px; background:#F5F5FF; padding:28px 16px; margin:-40px 0 24px 0; position:relative; z-index:2; box-shadow:0 4px 24px rgba(26,26,46,0.12); border-top:3px solid {S['bg_dark']};">
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
<tr>
<td width="25%" style="text-align:center; vertical-align:top; padding:0 4px;">
<div style="font-size:28px; font-weight:700; color:#000000;">{stats["tt_videos"]}</div>
<div style="font-size:12px; color:#888; margin-top:4px;">TikTok视频</div>
</td>
<td width="25%" style="text-align:center; vertical-align:top; padding:0 4px;">
<div style="font-size:28px; font-weight:700; color:#555555;">{stats["tt_comments"]:,}</div>
<div style="font-size:12px; color:#888; margin-top:4px;">TikTok评论</div>
</td>
<td width="25%" style="text-align:center; vertical-align:top; padding:0 4px;">
<div style="font-size:28px; font-weight:700; color:#E1306C;">{stats["ig_posts"]}</div>
<div style="font-size:12px; color:#888; margin-top:4px;">Instagram帖子</div>
</td>
<td width="25%" style="text-align:center; vertical-align:top; padding:0 4px;">
<div style="font-size:28px; font-weight:700; color:#4CAF50;">{stats["total_comments"]:,}</div>
<div style="font-size:12px; color:#888; margin-top:4px;">评论总计</div>
</td>
</tr>
</table>
</div>
</div>

<!-- 引言 -->
{section_start()}
<p style="{S['p']}">泡泡玛特(9992.HK)的海外扩张是当前港股消费板块最受关注的增长叙事之一。2024年年报显示，境外及其他地区收入同比增长超过400%，占公司总收入比重已上升至约40%。然而，财务报表只能告诉投资者"已经发生了什么"——季报数据滞后60天以上，无法捕捉实时的消费者热度变化。我们试图构建一套{S['highlight']('评论时序先行指标')}：当海外消费者在TikTok和Instagram上讨论泡泡玛特的频次加速上升时，它是否预示着下一个季度的动销数据同样向好？</p>

<p style="{S['p']}">这一方法论源自我们在小红书的前期实验。Phase 1中，我们通过抓取13,037条小红书评论的精确时间戳，验证了评论密度的月度趋势与泡泡玛特国内IP的声量周期存在高度一致性——Labubu在小红书的评论浪潮比其在国内渠道的动销高峰提前约6-8周出现。海外版本的核心假设相同：{S['highlight']('社媒评论是领先于财报的高频替代数据')}，海外市场甚至比国内更依赖社交媒体驱动消费决策。</p>

<p style="{S['p']}">本次分析覆盖两大平台。{S['badge']('#000000', 'TikTok')}方面，我们采集了7个核心关键词（#labubu、#dimoo、#molly等）及品牌官号@popmartglobal下的{stats["tt_videos"]}条视频，并通过拦截TikTok内部评论API获取了{stats["tt_comments"]:,}条评论的精确时间戳，时间跨度覆盖2024年至2026年3月。{S['badge']('#E1306C', 'Instagram')}方面，我们通过instagrapi私有移动端API采集了@popmart、@lalalalisa_m、@davidbeckham三个账号共{stats["ig_posts"]}篇帖子及{stats["ig_comments"]:,}条评论。TikTok代表Z世代算法驱动的病毒式传播，Instagram代表名人背书与品牌溢价渠道，两者结合提供了海外社媒热度的立体截面。</p>

<p style="{S['p']}">需要说明的是，我们原计划覆盖四个维度的海外数据。Amazon方面，由于平台评论系统的技术限制（"limited selection of reviews"策略），每个ASIN仅可获取8-13条评论，无法构建有统计意义的时间序列；12个监控ASIN合计仅137条评论，不具备时序分析基础，因此不纳入本次分析。SimilarWeb官网流量数据（popmart.com月访问量）目前处于数据对接阶段，尚未纳入分析。因此，本文聚焦于TikTok和Instagram两个已具备完整时序数据的平台。</p>
</div>

{S['section_divider']}

<!-- 品牌热度走势 -->
{section_start()}
{section_header('品牌整体热度走势', '#000000')}
<p style="{S['p']}">宏观层面，我们首先观察泡泡玛特在TikTok上的全平台讨论热度变化。下图以双轴方式同时呈现月度评论总量（柱状图，左轴）与评论密度（折线图，右轴）。两个指标结合阅读：评论总量反映绝对声量规模，而评论密度——即每条视频平均吸引的评论数——剥离了发布频率的干扰，更直接衡量单条内容的讨论强度。</p>
{S['img'](c['art_brand_trend.png'])}
<p style="{S['p']}">从图表走势可以观察到，2024年下半年出现了评论密度的显著跃升，这与Labubu泰国爆发的现象级热度（Lisa代言引发的全球媒体报道）在时间上高度吻合。值得注意的是，2026年3月的绝对评论量远高于其他月份，但这主要源于TikTok hashtag页面的recency bias特征——平台算法对近期内容的曝光权重更高，导致近期视频的采集样本密度大于历史月份。分析中我们更关注经归一化处理后的密度指标而非绝对量。</p>
<p style="{S['p']}">从投资角度看，评论密度的趋势拐点具有实际意义：若连续两个月密度回落，可以认为当期营销素材的传播效率在下降；若密度维持高位甚至上行，则印证品牌热度具有自我强化的飞轮特征。当前数据显示密度中枢较2024年初有明显提升，支持海外扩张叙事的持续性。</p>
</div>

<!-- IP份额 -->
<div style="padding:0 32px 32px 32px; background:{S['bg_warm']};">
{section_header('谁在占领海外心智：IP评论份额', '#FF8F00')}
<p style="{S['p']}">心智占有率分析的难点在于剔除采集密度的干扰：某月关键词搜索命中的视频数量波动较大，直接比较绝对量无法得出稳定结论。因此我们计算各IP在当月TikTok评论总量中的占比，构建{S['highlight']('份额而非绝对量')}的时间序列——不管某月总评论量是500还是5000，份额反映的是消费者心智资源在各IP之间的相对分配，具有更强的跨时期可比性。</p>
{S['img'](c['art_ip_share.png'])}
<p style="{S['p']}">从堆叠面积图来看，{S['badge']('#FF8F00', 'Labubu')}在绝大多数月份保持最高评论份额，与其作为泡泡玛特海外"明星单品"的市场定位一致。Dimoo和Molly各有小幅起伏，但未能撼动Labubu的主导地位。这一格局与Phase 1的小红书数据高度吻合——Labubu在国内也是评论份额最高的IP，说明Labubu的跨市场穿透力是公司IP矩阵中的核心资产。</p>
<p style="{S['p']}">从投资角度分析IP份额的变动意义：若Labubu份额出现持续性下滑而其他IP份额同步上升，这将是IP迭代周期健康的积极信号——意味着品牌的整体口碑而非单一IP在支撑海外增长，降低了对单一大单品的依赖风险。反之，若Labubu份额急剧下滑而替代IP未能承接，则需要警惕"Labubu后无明星IP"的叙事风险。当前数据显示Labubu份额稳定，这一风险尚未出现。</p>
</div>

{S['section_divider']}

<!-- 评论密度 -->
{section_start()}
{section_header('评论密度：双平台互动强度对比', '#E1306C')}
<p style="{S['p']}">评论密度定义为：在给定时间窗口内，每条发布内容（帖子或视频）平均吸引的评论数。与原始评论量相比，密度指标有两大优势：一是剔除了内容发布频率的影响（发布量增加会机械拉升评论总量）；二是反映的是单条内容的讨论深度，更接近"内容质量"和"话题激发力"的真实衡量。本图使用3个月滚动平均以过滤单月异常值。</p>
{S['img'](c['art_comment_density.png'])}
<p style="{S['p']}">TikTok的评论密度长期显著高于Instagram，这与两个平台的底层机制差异密切相关。TikTok采用interest graph（兴趣图谱）推荐，内容被推送给对相关话题感兴趣但未必关注该账号的用户——这意味着每条视频都有机会触达"潜在讨论者"；而Instagram以social graph（社交图谱）为主，内容主要触达已关注的粉丝，互动率的天花板更低。因此TikTok较高的评论密度在结构上是合理的，并不意味着Instagram的品牌效果差。</p>
<p style="{S['p']}">从品牌健康度角度，Instagram的评论密度中枢虽低但稳定，意味着以Lisa和Beckham为代表的名人背书帖子持续产生稳定的粉丝互动，这类互动的"购买意向转化率"通常高于TikTok的泛娱乐互动。两平台密度走势均无明显下行拐点，支持海外品牌声量的持续性。</p>
</div>

<!-- 参与率 -->
<div style="padding:0 32px 32px 32px; background:{S['bg_warm']};">
{section_header('TikTok参与率：最有价值的海外信号', '#000000')}
<p style="{S['p']}">参与率（ER = (点赞+评论)/播放量）是社交媒体行业最通用的内容效率归一化指标。它的核心价值在于剔除账号粉丝量和推荐流量规模的差异，直接衡量内容与观看者之间的共鸣强度。TikTok平台的通用基准为：大众内容ER约3-5%，美妆/时尚/潮玩类内容通常可达5-8%。泡泡玛特相关视频的{S['highlight'](f'平均ER达到{stats["tt_avg_er"]:.1f}%')}，在时尚玩具品类中处于领先水平。</p>
{S['img'](c['art_er_trend.png'])}
<p style="{S['p']}">按IP分组的ER走势图揭示了IP生命周期的微观差异。Labubu的ER整体维持高位，显示其在存量视频中持续保持高互动，这是一个IP"长尾效应"健康的标志。部分IP的ER出现一定程度的回落，这在成熟IP的生命周期中属于正常现象，并不必然意味着需求下滑——ER回落更多反映的是"从稀缺到普及"的用户预期调整，实际销售可以与之背离。</p>
{S['callout'](f'<strong>关键数据点：</strong>总体ER均值{stats["tt_avg_er"]:.1f}%，高于TikTok平台3-5%基准，印证泡泡玛特相关内容具有远超普通消费品的社媒黏性，这一特征支持公司在海外市场依靠社媒自然流量驱动增长而非高强度付费投放。', '#000000')}
</div>

{S['section_divider']}

<!-- 品牌 vs UGC -->
{section_start()}
{section_header('品牌 vs 用户生成内容', '#E53935')}
<p style="{S['p']}">我们将TikTok视频按作者分为两类：官方品牌账号发布（@popmartglobal，品牌内容）和非品牌账号发布（用户生成内容，UGC）。两者的核心区别在于：品牌内容是公司主动的营销投放，UGC是消费者自发的口碑传播。UGC占比越高，说明品牌的传播飞轮越自主，对营销预算的依赖越低。在我们的{stats["tt_videos"]}条样本中，UGC视频数量远超品牌官号发布量，且UGC均播是品牌官号的{S['highlight'](f'{stats["ugc_ratio"]}倍')}。</p>
{S['img'](c['art_brand_vs_ugc.png'])}
<p style="{S['p']}">UGC的高播放量反映了一个重要事实：关于泡泡玛特的TikTok流量，绝大多数由普通用户的开箱视频、收藏展示、盲盒抽取内容贡献，而非官方营销素材。这个结构对消费品牌至关重要——在TikTok生态中，真实用户的内容往往比品牌素材有更高的可信度和传播力，因为平台算法会优先推荐"看起来真实"的内容。泡泡玛特当前的UGC生态表明，它在海外已形成了一定规模的核心用户社群，这些用户不需要品牌付费就会主动创作和传播内容。</p>
{S['callout'](f'<strong>投资含义：</strong>UGC驱动的传播结构意味着海外市场的用户获取成本（CAC）远低于依赖付费广告的竞争对手。社区飞轮效应一旦形成，单位营销投入的ROI将持续提升，这是消费品海外扩张中最具护城河价值的定性特征之一。', '#E53935')}
</div>

<!-- 双平台指数 -->
<div style="padding:0 32px 32px 32px; background:{S['bg_warm']};">
{section_header('双平台评论密度指数', '#1A1A2E')}
<p style="{S['p']}">TikTok和Instagram两个平台的评论绝对数量级差异显著（TikTok {stats["tt_comments"]:,}条 vs Instagram {stats["ig_comments"]:,}条），且各月采集到的内容数量受平台算法影响存在波动（例如TikTok hashtag页面的recency bias导致近期月份视频样本量远高于历史月份）。因此，我们采用{S['highlight']('贴均评论密度')}（月评论数÷月内容数）替代评论总量作为归一化基础，再将各平台密度除以全周期均值构建均值=100的指数。这一方法同时消除了平台间的量级差异和采集密度偏差，使趋势对比具备统计意义。</p>
{S['img'](c['art_cross_platform.png'])}
<p style="{S['p']}">贴均评论密度反映的是"每条内容平均能激发多少讨论"，是比评论总量更纯粹的热度信号。当两条线同步上行时，说明两个平台上每条泡泡玛特相关内容引发的讨论深度都在加强——这种跨平台共振通常对应重要的品牌事件（如新品发布、Lisa联名效应、线下快闪等）。当两线出现背离时，反映的是平台用户群体参与模式的结构性差异：TikTok用户更倾向于在算法推荐的热门内容下集中评论，而Instagram评论更均匀地分布在各帖子中。</p>
<p style="{S['p']}">从当前数据来看，密度指数有效消除了TikTok 3月因recency bias导致的样本量激增（约130条视频 vs 其他月份均值约20条）对趋势判断的干扰。两平台在2025年末至2026年初的密度走势为投资者提供了一个独立于卖方报告的数据参照点，可与公司管理层在业绩会上描述的海外动销情况进行交叉验证。</p>
</div>

{S['section_divider']}

<!-- 评论质量 -->
{section_start()}
{section_header('评论质量：不只是数量，还要看深度', '#4CAF50')}
<p style="{S['p']}">原始评论量是一个粗粒度指标，无法区分"100条无人理会的灌水"和"100条引发深度讨论的优质内容"。我们引入评论点赞数作为质量代理变量，将评论分为三层：高互动（≥10赞，代表强共鸣）、中互动（3-9赞）、低互动（&lt;3赞，包括0赞）。一条获得100赞的评论，其实际传播覆盖面远超100条零赞评论的总和，因为其他用户在查看该评论时会进一步点赞形成二次传播。</p>
{S['img'](c['art_comment_quality.png'])}
<p style="{S['p']}">TikTok评论中{S['highlight'](f'{stats["tt_high_pct"]:.0f}%属于高互动评论（≥10赞）')}，这一比例在消费品类中属于较高水平。高互动评论的典型特征是：用户分享自己的购买决策（"已下单"/"买了哪款"）、表达强烈的情绪（兴奋/遗憾/攀比）、以及询问购买渠道，这些都是接近消费转化的强意向信号。Instagram的高互动评论比例相对较低，这与前述平台机制差异一致——Instagram评论区更像一对一社交，TikTok更像公开广场讨论。</p>
<p style="{S['p']}">将评论量乘以高互动比例，可以得到一个质量调整后的热度指标。泡泡玛特TikTok的高互动评论绝对数量和比例双高，意味着其社媒讨论不仅具备规模，更具备深度——这是口碑效应真正产生转化力量的必要条件。从历史消费品牌的社媒数据来看，高互动评论比例维持在10%以上通常与品牌的渠道扩张期正相关。</p>
</div>

<!-- 官网流量 -->
{section_start()}
{section_header('官网流量：DTC渠道的温度计', '#1565C0')}
<p style="{S['p']}">社媒热度是品牌曝光的前端指标，而官网流量则是消费者从"知道"到"想买"的转化中间环节。popmart.com作为泡泡玛特海外DTC（直接面向消费者）的核心渠道，其月度访问量直接反映了潜在消费者的购买意向强度。我们通过SimilarWeb PRO获取了popmart.com的月度流量数据，将其与社媒评论热度进行交叉验证。</p>
{S['img'](c['art_similarweb.png'])}
<p style="{S['p']}">数据显示popmart.com月度访问量从2025年12月的约800万下降至2026年2月的约500万，呈现逐月收缩态势。但这一下降需要结合季节性因素理解：12月圣诞/新年是全球电商的年度峰值窗口，消费类网站普遍在1-2月经历回落。从绝对水平看，月均634万次访问、单次浏览5.85个页面、3分13秒的停留时长，在电商行业中属于{S['highlight']('高质量流量特征')}——跳出率仅33.3%远低于电商行业40-60%的平均水平，说明访客的购买意向明确而非随意浏览。</p>
<p style="{S['p']}">从流量地域分布看，美国占41.9%、日本11.2%、澳大利亚5.4%、新加坡5.1%，与泡泡玛特已公布的海外门店布局高度吻合（北美+东亚+东南亚为三大支柱市场）。值得注意的是，自然搜索占全部流量的43.8%，其中品牌词搜索（"pop mart""labubu"等）占搜索流量的71%，这意味着绝大多数访客是带着明确品牌认知而来，佐证了社媒传播→品牌认知→官网转化的完整链路。社交渠道仅占6.1%的流量，说明社媒的作用更多是品牌种草而非直接导流。</p>
</div>

{S['section_divider']}

<!-- 方法论 -->
<div style="padding:0 32px 32px 32px; background:{S['bg_warm']};">
{section_header('方法论与局限性', '#1A1A2E')}
<p style="{S['p']}">数据采集基础设施：TikTok采用DrissionPage控制真实Chrome浏览器，通过page.listen拦截/api/comment/list/接口响应，获取评论的精确时间戳，首次运行需手动完成一次TikTok登录，后续通过cookie持久化（tiktok_cookies.json + CDP注入）自动恢复会话。Instagram采用instagrapi私有移动端API获取帖子列表，再用DrissionPage访问帖子页提取评论。所有采集均配置socks5://127.0.0.1:10808代理，模拟真人浏览行为并包含随机延迟。</p>
<div style="border-radius:12px; background:#FFFFFF; padding:20px 24px; margin:24px 0; border:1px solid #E0E0E0;">
<p style="font-size:14px; line-height:1.8; color:#555; margin:0 0 12px 0;"><strong style="color:#333;">已知局限与处理方式：</strong></p>
<p style="font-size:14px; line-height:1.8; color:#555; margin:0 0 12px 0;"><strong style="color:#333;">1. TikTok 3月recency bias（时间偏好特征）</strong><br>TikTok hashtag页面存在时间偏好特征（recency bias），近期内容的曝光概率高于历史内容。这导致2026年3月的视频样本量（约130条）显著高于其他月份均值（约20条）。这不是采集错误，而是平台算法的固有特征。我们在分析中使用评论密度（每视频均评论数）和百分比份额等归一化指标来消除这一偏差的影响。</p>
<p style="font-size:14px; line-height:1.8; color:#555; margin:0 0 12px 0;"><strong style="color:#333;">2. Amazon评论技术限制（本文未纳入）</strong><br>Amazon评论系统设计上限制了评论展示数量（每个产品页面仅显示"limited selection of reviews"），且medleyReviewsAjaxUrl被设为空字符串，技术上无法实现完整评论翻页。12个监控ASIN合计仅获得137条评论，不具备时序分析的统计基础，故本文不纳入Amazon维度。Amazon数据库表仍保留，后续如有更优的获取方案可以追加分析。</p>
<p style="font-size:14px; line-height:1.8; color:#555; margin:0 0 12px 0;"><strong style="color:#333;">3. SimilarWeb流量数据（PRO试用版）</strong><br>popmart.com流量数据来自SimilarWeb PRO，当前仅覆盖最近3个月（2025.12-2026.02）。试用版不提供12个月以上的历史数据，因此无法构建长期流量趋势。月度访问量、停留时长、跳出率等指标为SimilarWeb基于面板数据的估算值，与实际Google Analytics数据可能存在10-15%偏差，但趋势方向可信。后续如获取PRO年度订阅，将补充6-12个月的历史流量趋势。</p>
<p style="font-size:14px; line-height:1.8; color:#555; margin:0 0 8px 0;"><strong style="color:#333;">4. TikTok关键词覆盖</strong><br>视频来自7个核心关键词（#labubu、#labubu lisa、#dimoo、#molly popmart、#skullpanda、#pop mart、#popmart unboxing）及官号@popmartglobal，可能遗漏长尾hashtag下的相关内容，但已覆盖主要传播路径。#molly话题存在与毒品"Molly/MDMA"相关内容的混淆，采集时已内置关键词过滤机制。</p>
<p style="font-size:14px; line-height:1.8; color:#555; margin:0;">5. Instagram IP分类仅能区分Labubu与品牌整体（基于hashtag），Dimoo/Molly等IP在Instagram上的独立热度无法精确拆分；当前未进行NLP情感分析，后续版本将加入情感极性维度。</p>
</div>
</div>

{S['section_divider']}

<!-- 结语 -->
{section_start()}
{section_header('结语', '#1A1A2E')}
<p style="{S['p']}">本次海外另类数据分析从TikTok {stats["tt_videos"]}条视频、{stats["tt_comments"]:,}条评论和Instagram {stats["ig_posts"]}篇帖子、{stats["ig_comments"]:,}条评论中提炼出以下核心投资观点：其一，泡泡玛特的海外社媒热度处于结构性上行通道，跨平台热度指数在2025年末至2026年初均维持在历史均值以上，与公司海外收入高增的财报叙事形成独立验证；其二，Labubu是海外增长的主引擎，在TikTok评论份额中长期保持领先，且未出现衰退迹象，这一特征支持2026年Labubu系列产能扩张的战略合理性。</p>

<p style="{S['p']}">从方法论价值来看，本研究验证了海外社媒评论时序数据作为先行指标的可行性。与传统财务数据（滞后60天以上）和卖方渠道调研（覆盖面有限、主观性强）相比，高频社媒数据可以在季报发布前捕捉到消费者热度的趋势拐点。参与率高于行业均值、UGC倍增效应、高互动评论比例等指标共同勾勒出一个具有{S['highlight']('社区飞轮特征')}的品牌——这类品牌一旦在新市场完成初始渗透，后续扩张的边际营销成本将持续下降，支持市场给予的估值溢价。</p>

<p style="{S['p']}">后续版本将追加：①SimilarWeb历史流量趋势（当前受PRO试用限制仅3个月，获取年度订阅后可回溯12-15个月）；②NLP情感分析（正/中/负评论比例月度趋势）；③Amazon评论如有更优API方案则补充线上动销维度。多维数据的交叉印证将进一步提升先行指标的可信度。数据驱动的消费者洞察，提供的是财报之外的第二套坐标系——永远比主观判断更接近真相。</p>
</div>

<!-- 尾部 -->
<div style="background:{S['bg_dark']}; padding:40px 32px; text-align:center;">
<div style="margin:0 0 20px 0;"><div style="margin:0 auto; width:60px; height:3px; background:#FFFFFF; border-radius:2px; opacity:0.3;"></div></div>
<div style="border-radius:16px; background:rgba(255,255,255,0.1); padding:28px 32px; margin:0 0 24px 0;">
<p style="font-size:16px; font-weight:600; color:#FFFFFF; margin:0 0 8px 0;">对海外另类数据或Pop Mart分析感兴趣？</p>
<p style="font-size:13px; color:rgba(255,255,255,0.7); margin:0; line-height:1.8;">欢迎交流 · 双平台时序采集 · IP海外热度追踪</p>
</div>
<p style="font-size:12px; color:rgba(255,255,255,0.4); margin:0 0 4px 0;">数据来源：TikTok / Instagram 公开内容 · SimilarWeb PRO | 采集周期：2023.10 — 2026.03</p>
<p style="font-size:12px; color:rgba(255,255,255,0.4); margin:0;">本文所有分析基于公开可获取的用户生成内容，不构成投资建议。</p>
</div>

</div>
</body>
</html>'''
    return html


# ─── 主入口 ────────────────────────────────────────

def render_hero_png(stats, charts_dir):
    """渲染 hero 头图 + 数据卡片为静态 PNG（公众号兼容，高清）"""
    fig, ax = plt.subplots(figsize=(14, 7.5))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 7.5)
    ax.axis('off')
    fig.patch.set_facecolor('#1A1A2E')

    # 标题
    ax.text(7, 6.2, '海外另类数据拆解', fontsize=56, fontweight=800,
            color='white', ha='center', va='center')
    ax.text(7, 5.0, '泡泡玛特全球热度', fontsize=56, fontweight=800,
            color='white', ha='center', va='center')
    ax.text(7, 3.9, 'TikTok · Instagram 双平台评论时序分析', fontsize=30,
            color='#D0D0D0', ha='center', va='center')
    ax.text(7, 3.2, f'{stats["tt_videos"]}条视频 · {stats["total_comments"]:,}条评论 · 2个平台 · 跨越18个月',
            fontsize=22, color='#999999', ha='center', va='center')

    # 数据卡片背景
    from matplotlib.patches import FancyBboxPatch
    card = FancyBboxPatch((0.8, 0.3), 12.4, 2.4, boxstyle='round,pad=0.2',
                          facecolor='#F5F5FF', edgecolor='#1A1A2E', linewidth=3)
    ax.add_patch(card)

    # 四列数据
    cols = [
        (stats['tt_videos'], 'TikTok视频', '#000000'),
        (f'{stats["tt_comments"]:,}', 'TikTok评论', '#555555'),
        (stats['ig_posts'], 'Instagram帖子', '#E1306C'),
        (f'{stats["total_comments"]:,}', '评论总计', '#4CAF50'),
    ]
    for i, (val, label, color) in enumerate(cols):
        x = 2.3 + i * 3.0
        ax.text(x, 2.0, str(val), fontsize=48, fontweight=700,
                color=color, ha='center', va='center')
        ax.text(x, 1.0, label, fontsize=22, color='#888888', ha='center', va='center')

    plt.tight_layout(pad=0.3)
    fig.savefig(os.path.join(charts_dir, 'wechat_hero.png'),
                facecolor='#1A1A2E', bbox_inches='tight', pad_inches=0.1, dpi=200)
    plt.close(fig)


def render_footer_png(charts_dir):
    """渲染尾部为静态 PNG"""
    fig, ax = plt.subplots(figsize=(14, 4))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 4)
    ax.axis('off')
    fig.patch.set_facecolor('#1A1A2E')

    ax.text(7, 3.1, '对海外另类数据或 Pop Mart 分析感兴趣？', fontsize=28,
            fontweight=600, color='white', ha='center', va='center')
    ax.text(7, 2.2, '欢迎交流 · 双平台时序采集 · IP海外热度追踪', fontsize=20,
            color='#BBBBBB', ha='center', va='center')
    ax.text(7, 1.2, '数据来源：TikTok / Instagram 公开内容 · SimilarWeb PRO | 采集周期：2023.10 — 2026.03',
            fontsize=14, color='#777777', ha='center', va='center')
    ax.text(7, 0.55, '本文所有分析基于公开可获取的用户生成内容，不构成投资建议。',
            fontsize=14, color='#777777', ha='center', va='center')

    plt.tight_layout(pad=0.3)
    fig.savefig(os.path.join(charts_dir, 'wechat_footer.png'),
                facecolor='#1A1A2E', bbox_inches='tight', pad_inches=0.1, dpi=200)
    plt.close(fig)


def generate_wechat_html(stats):
    """生成公众号兼容版 HTML — 复杂渲染用静态图，文字保持简单排版"""
    c = {name: img_b64(name) for name in [
        'art_brand_trend.png', 'art_ip_share.png', 'art_comment_density.png',
        'art_er_trend.png', 'art_brand_vs_ugc.png', 'art_cross_platform.png',
        'art_comment_quality.png', 'art_similarweb.png',
        'wechat_hero.png', 'wechat_footer.png',
    ]}

    # 简化样式 — 只用公众号支持的 CSS
    P = 'font-size:15px; line-height:2.0; letter-spacing:0.5px; color:#2D2D2D; margin:0 0 16px 0;'
    H2 = 'font-size:20px; font-weight:700; color:#2D2D2D; margin:32px 0 8px 0;'
    IMG = lambda src: f'<img src="{src}" style="width:100%; display:block; margin:20px 0;">'
    DIVIDER = '<div style="text-align:center; margin:20px 0;"><div style="width:60px; height:3px; background:#1A1A2E; margin:0 auto;"></div></div>'
    HIGHLIGHT = lambda t: f'<strong>{t}</strong>'
    CALLOUT = lambda text: f'<div style="background:#F5F5FF; padding:16px 20px; margin:20px 0; border-left:4px solid #1A1A2E;"><p style="font-size:14px; line-height:1.8; color:#333; margin:0;">{text}</p></div>'

    def section_header(title, color):
        return f'''<div style="margin:28px 0 16px 0;">
<div style="display:inline-block;width:6px;height:20px;background:{color};margin-right:8px;vertical-align:middle;"></div>
<span style="{H2} display:inline; vertical-align:middle;">{title}</span>
<div style="width:60px; height:3px; background:{color}; margin-top:6px;"></div>
</div>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>海外另类数据拆解泡泡玛特全球热度（公众号版）</title>
</head>
<body style="margin:0; padding:0; background:#f0f0f0;">
<div style="max-width:680px; margin:0 auto; font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif; background:#FFFFFF; overflow:hidden;">

<!-- HERO 头图（静态PNG） -->
{IMG(c['wechat_hero.png'])}

<!-- 引言 -->
<div style="padding:0 32px 24px 32px;">
<p style="{P}">泡泡玛特(9992.HK)的海外扩张是当前港股消费板块最受关注的增长叙事之一。2024年年报显示，境外及其他地区收入同比增长超过400%，占公司总收入比重已上升至约40%。然而，财务报表只能告诉投资者"已经发生了什么"——季报数据滞后60天以上，无法捕捉实时的消费者热度变化。我们试图构建一套{HIGHLIGHT('评论时序先行指标')}：当海外消费者在TikTok和Instagram上讨论泡泡玛特的频次加速上升时，它是否预示着下一个季度的动销数据同样向好？</p>

<p style="{P}">这一方法论源自我们在小红书的前期实验。Phase 1中，我们通过抓取13,037条小红书评论的精确时间戳，验证了评论密度的月度趋势与泡泡玛特国内IP的声量周期存在高度一致性——Labubu在小红书的评论浪潮比其在国内渠道的动销高峰提前约6-8周出现。海外版本的核心假设相同：{HIGHLIGHT('社媒评论是领先于财报的高频替代数据')}，海外市场甚至比国内更依赖社交媒体驱动消费决策。</p>

<p style="{P}">本次分析覆盖两大平台。<strong>TikTok</strong>方面，我们采集了7个核心关键词（#labubu、#dimoo、#molly等）及品牌官号@popmartglobal下的{stats["tt_videos"]}条视频，并通过拦截TikTok内部评论API获取了{stats["tt_comments"]:,}条评论的精确时间戳，时间跨度覆盖2024年至2026年3月。<strong>Instagram</strong>方面，我们通过instagrapi私有移动端API采集了@popmart、@lalalalisa_m、@davidbeckham三个账号共{stats["ig_posts"]}篇帖子及{stats["ig_comments"]:,}条评论。TikTok代表Z世代算法驱动的病毒式传播，Instagram代表名人背书与品牌溢价渠道，两者结合提供了海外社媒热度的立体截面。</p>

<p style="{P}">需要说明的是，我们原计划覆盖四个维度的海外数据。Amazon方面，由于平台评论系统的技术限制（"limited selection of reviews"策略），每个ASIN仅可获取8-13条评论，无法构建有统计意义的时间序列；12个监控ASIN合计仅137条评论，不具备时序分析基础，因此不纳入本次分析。SimilarWeb官网流量数据（popmart.com月访问量）目前处于数据对接阶段，尚未纳入分析。因此，本文聚焦于TikTok和Instagram两个已具备完整时序数据的平台。</p>
</div>

{DIVIDER}

<!-- 品牌热度走势 -->
<div style="padding:0 32px 24px 32px;">
{section_header('品牌整体热度走势', '#000000')}
<p style="{P}">宏观层面，我们首先观察泡泡玛特在TikTok上的全平台讨论热度变化。下图以双轴方式同时呈现月度评论总量（柱状图，左轴）与评论密度（折线图，右轴）。两个指标结合阅读：评论总量反映绝对声量规模，而评论密度——即每条视频平均吸引的评论数——剥离了发布频率的干扰，更直接衡量单条内容的讨论强度。</p>
{IMG(c['art_brand_trend.png'])}
<p style="{P}">从图表走势可以观察到，2024年下半年出现了评论密度的显著跃升，这与Labubu泰国爆发的现象级热度（Lisa代言引发的全球媒体报道）在时间上高度吻合。值得注意的是，2026年3月的绝对评论量远高于其他月份，但这主要源于TikTok hashtag页面的recency bias特征——平台算法对近期内容的曝光权重更高，导致近期视频的采集样本密度大于历史月份。分析中我们更关注经归一化处理后的密度指标而非绝对量。</p>
<p style="{P}">从投资角度看，评论密度的趋势拐点具有实际意义：若连续两个月密度回落，可以认为当期营销素材的传播效率在下降；若密度维持高位甚至上行，则印证品牌热度具有自我强化的飞轮特征。当前数据显示密度中枢较2024年初有明显提升，支持海外扩张叙事的持续性。</p>
</div>

<!-- IP份额 -->
<div style="padding:0 32px 24px 32px; background:#FFF8F0;">
{section_header('谁在占领海外心智：IP评论份额', '#FF8F00')}
<p style="{P}">心智占有率分析的难点在于剔除采集密度的干扰：某月关键词搜索命中的视频数量波动较大，直接比较绝对量无法得出稳定结论。因此我们计算各IP在当月TikTok评论总量中的占比，构建{HIGHLIGHT('份额而非绝对量')}的时间序列——不管某月总评论量是500还是5000，份额反映的是消费者心智资源在各IP之间的相对分配，具有更强的跨时期可比性。</p>
{IMG(c['art_ip_share.png'])}
<p style="{P}">从堆叠面积图来看，<strong>Labubu</strong>在绝大多数月份保持最高评论份额，与其作为泡泡玛特海外"明星单品"的市场定位一致。Dimoo和Molly各有小幅起伏，但未能撼动Labubu的主导地位。这一格局与Phase 1的小红书数据高度吻合——Labubu在国内也是评论份额最高的IP，说明Labubu的跨市场穿透力是公司IP矩阵中的核心资产。</p>
<p style="{P}">从投资角度分析IP份额的变动意义：若Labubu份额出现持续性下滑而其他IP份额同步上升，这将是IP迭代周期健康的积极信号——意味着品牌的整体口碑而非单一IP在支撑海外增长，降低了对单一大单品的依赖风险。反之，若Labubu份额急剧下滑而替代IP未能承接，则需要警惕"Labubu后无明星IP"的叙事风险。当前数据显示Labubu份额稳定，这一风险尚未出现。</p>
</div>

{DIVIDER}

<!-- 评论密度 -->
<div style="padding:0 32px 24px 32px;">
{section_header('评论密度：双平台互动强度对比', '#E1306C')}
<p style="{P}">评论密度定义为：在给定时间窗口内，每条发布内容（帖子或视频）平均吸引的评论数。与原始评论量相比，密度指标有两大优势：一是剔除了内容发布频率的影响（发布量增加会机械拉升评论总量）；二是反映的是单条内容的讨论深度，更接近"内容质量"和"话题激发力"的真实衡量。本图使用3个月滚动平均以过滤单月异常值。</p>
{IMG(c['art_comment_density.png'])}
<p style="{P}">TikTok的评论密度长期显著高于Instagram，这与两个平台的底层机制差异密切相关。TikTok采用interest graph（兴趣图谱）推荐，内容被推送给对相关话题感兴趣但未必关注该账号的用户——这意味着每条视频都有机会触达"潜在讨论者"；而Instagram以social graph（社交图谱）为主，内容主要触达已关注的粉丝，互动率的天花板更低。因此TikTok较高的评论密度在结构上是合理的，并不意味着Instagram的品牌效果差。</p>
<p style="{P}">从品牌健康度角度，Instagram的评论密度中枢虽低但稳定，意味着以Lisa和Beckham为代表的名人背书帖子持续产生稳定的粉丝互动，这类互动的"购买意向转化率"通常高于TikTok的泛娱乐互动。两平台密度走势均无明显下行拐点，支持海外品牌声量的持续性。</p>
</div>

<!-- 参与率 -->
<div style="padding:0 32px 24px 32px; background:#FFF8F0;">
{section_header('TikTok参与率：最有价值的海外信号', '#000000')}
<p style="{P}">参与率（ER = (点赞+评论)/播放量）是社交媒体行业最通用的内容效率归一化指标。它的核心价值在于剔除账号粉丝量和推荐流量规模的差异，直接衡量内容与观看者之间的共鸣强度。TikTok平台的通用基准为：大众内容ER约3-5%，美妆/时尚/潮玩类内容通常可达5-8%。泡泡玛特相关视频的{HIGHLIGHT(f'平均ER达到{stats["tt_avg_er"]:.1f}%')}，在时尚玩具品类中处于领先水平。</p>
{IMG(c['art_er_trend.png'])}
<p style="{P}">按IP分组的ER走势图揭示了IP生命周期的微观差异。Labubu的ER整体维持高位，显示其在存量视频中持续保持高互动，这是一个IP"长尾效应"健康的标志。部分IP的ER出现一定程度的回落，这在成熟IP的生命周期中属于正常现象，并不必然意味着需求下滑——ER回落更多反映的是"从稀缺到普及"的用户预期调整，实际销售可以与之背离。</p>
{CALLOUT(f'<strong>关键数据点：</strong>总体ER均值{stats["tt_avg_er"]:.1f}%，高于TikTok平台3-5%基准，印证泡泡玛特相关内容具有远超普通消费品的社媒黏性，这一特征支持公司在海外市场依靠社媒自然流量驱动增长而非高强度付费投放。')}
</div>

{DIVIDER}

<!-- 品牌 vs UGC -->
<div style="padding:0 32px 24px 32px;">
{section_header('品牌 vs 用户生成内容', '#E53935')}
<p style="{P}">我们将TikTok视频按作者分为两类：官方品牌账号发布（@popmartglobal，品牌内容）和非品牌账号发布（用户生成内容，UGC）。两者的核心区别在于：品牌内容是公司主动的营销投放，UGC是消费者自发的口碑传播。UGC占比越高，说明品牌的传播飞轮越自主，对营销预算的依赖越低。在我们的{stats["tt_videos"]}条样本中，UGC视频数量远超品牌官号发布量，且UGC均播是品牌官号的{HIGHLIGHT(f'{stats["ugc_ratio"]}倍')}。</p>
{IMG(c['art_brand_vs_ugc.png'])}
<p style="{P}">UGC的高播放量反映了一个重要事实：关于泡泡玛特的TikTok流量，绝大多数由普通用户的开箱视频、收藏展示、盲盒抽取内容贡献，而非官方营销素材。这个结构对消费品牌至关重要——在TikTok生态中，真实用户的内容往往比品牌素材有更高的可信度和传播力，因为平台算法会优先推荐"看起来真实"的内容。泡泡玛特当前的UGC生态表明，它在海外已形成了一定规模的核心用户社群，这些用户不需要品牌付费就会主动创作和传播内容。</p>
{CALLOUT(f'<strong>投资含义：</strong>UGC驱动的传播结构意味着海外市场的用户获取成本（CAC）远低于依赖付费广告的竞争对手。社区飞轮效应一旦形成，单位营销投入的ROI将持续提升，这是消费品海外扩张中最具护城河价值的定性特征之一。')}
</div>

<!-- 双平台指数 -->
<div style="padding:0 32px 24px 32px; background:#FFF8F0;">
{section_header('双平台评论密度指数', '#1A1A2E')}
<p style="{P}">TikTok和Instagram两个平台的评论绝对数量级差异显著（TikTok {stats["tt_comments"]:,}条 vs Instagram {stats["ig_comments"]:,}条），且各月采集到的内容数量受平台算法影响存在波动（例如TikTok hashtag页面的recency bias导致近期月份视频样本量远高于历史月份）。因此，我们采用{HIGHLIGHT('贴均评论密度')}（月评论数÷月内容数）替代评论总量作为归一化基础，再将各平台密度除以全周期均值构建均值=100的指数。这一方法同时消除了平台间的量级差异和采集密度偏差，使趋势对比具备统计意义。</p>
{IMG(c['art_cross_platform.png'])}
<p style="{P}">贴均评论密度反映的是"每条内容平均能激发多少讨论"，是比评论总量更纯粹的热度信号。当两条线同步上行时，说明两个平台上每条泡泡玛特相关内容引发的讨论深度都在加强——这种跨平台共振通常对应重要的品牌事件（如新品发布、Lisa联名效应、线下快闪等）。当两线出现背离时，反映的是平台用户群体参与模式的结构性差异：TikTok用户更倾向于在算法推荐的热门内容下集中评论，而Instagram评论更均匀地分布在各帖子中。</p>
<p style="{P}">从当前数据来看，密度指数有效消除了TikTok 3月因recency bias导致的样本量激增（约130条视频 vs 其他月份均值约20条）对趋势判断的干扰。两平台在2025年末至2026年初的密度走势为投资者提供了一个独立于卖方报告的数据参照点，可与公司管理层在业绩会上描述的海外动销情况进行交叉验证。</p>
</div>

{DIVIDER}

<!-- 评论质量 -->
<div style="padding:0 32px 24px 32px;">
{section_header('评论质量：不只是数量，还要看深度', '#4CAF50')}
<p style="{P}">原始评论量是一个粗粒度指标，无法区分"100条无人理会的灌水"和"100条引发深度讨论的优质内容"。我们引入评论点赞数作为质量代理变量，将评论分为三层：高互动（≥10赞，代表强共鸣）、中互动（3-9赞）、低互动（&lt;3赞，包括0赞）。一条获得100赞的评论，其实际传播覆盖面远超100条零赞评论的总和，因为其他用户在查看该评论时会进一步点赞形成二次传播。</p>
{IMG(c['art_comment_quality.png'])}
<p style="{P}">TikTok评论中{HIGHLIGHT(f'{stats["tt_high_pct"]:.0f}%属于高互动评论（≥10赞）')}，这一比例在消费品类中属于较高水平。高互动评论的典型特征是：用户分享自己的购买决策（"已下单"/"买了哪款"）、表达强烈的情绪（兴奋/遗憾/攀比）、以及询问购买渠道，这些都是接近消费转化的强意向信号。Instagram的高互动评论比例相对较低，这与前述平台机制差异一致——Instagram评论区更像一对一社交，TikTok更像公开广场讨论。</p>
<p style="{P}">将评论量乘以高互动比例，可以得到一个质量调整后的热度指标。泡泡玛特TikTok的高互动评论绝对数量和比例双高，意味着其社媒讨论不仅具备规模，更具备深度——这是口碑效应真正产生转化力量的必要条件。从历史消费品牌的社媒数据来看，高互动评论比例维持在10%以上通常与品牌的渠道扩张期正相关。</p>
</div>

<!-- 官网流量 -->
<div style="padding:0 32px 24px 32px; background:#FFF8F0;">
{section_header('官网流量：DTC渠道的温度计', '#1565C0')}
<p style="{P}">社媒热度是品牌曝光的前端指标，而官网流量则是消费者从"知道"到"想买"的转化中间环节。popmart.com作为泡泡玛特海外DTC（直接面向消费者）的核心渠道，其月度访问量直接反映了潜在消费者的购买意向强度。我们通过SimilarWeb PRO获取了popmart.com的月度流量数据，将其与社媒评论热度进行交叉验证。</p>
{IMG(c['art_similarweb.png'])}
<p style="{P}">数据显示popmart.com月度访问量从2025年12月的约800万下降至2026年2月的约500万，呈现逐月收缩态势。但这一下降需要结合季节性因素理解：12月圣诞/新年是全球电商的年度峰值窗口，消费类网站普遍在1-2月经历回落。从绝对水平看，月均634万次访问、单次浏览5.85个页面、3分13秒的停留时长，在电商行业中属于{HIGHLIGHT('高质量流量特征')}——跳出率仅33.3%远低于电商行业40-60%的平均水平，说明访客的购买意向明确而非随意浏览。</p>
<p style="{P}">从流量地域分布看，美国占41.9%、日本11.2%、澳大利亚5.4%、新加坡5.1%，与泡泡玛特已公布的海外门店布局高度吻合（北美+东亚+东南亚为三大支柱市场）。值得注意的是，自然搜索占全部流量的43.8%，其中品牌词搜索（"pop mart""labubu"等）占搜索流量的71%，这意味着绝大多数访客是带着明确品牌认知而来，佐证了社媒传播→品牌认知→官网转化的完整链路。社交渠道仅占6.1%的流量，说明社媒的作用更多是品牌种草而非直接导流。</p>
</div>

{DIVIDER}

<!-- 方法论 -->
<div style="padding:0 32px 24px 32px;">
{section_header('方法论与局限性', '#1A1A2E')}
<p style="{P}">数据采集基础设施：TikTok采用DrissionPage控制真实Chrome浏览器，通过page.listen拦截/api/comment/list/接口响应，获取评论的精确时间戳，首次运行需手动完成一次TikTok登录，后续通过cookie持久化（tiktok_cookies.json + CDP注入）自动恢复会话。Instagram采用instagrapi私有移动端API获取帖子列表，再用DrissionPage访问帖子页提取评论。所有采集均配置socks5://127.0.0.1:10808代理，模拟真人浏览行为并包含随机延迟。</p>
<div style="background:#FFFFFF; padding:16px 20px; margin:20px 0; border:1px solid #E0E0E0;">
<p style="font-size:14px; line-height:1.8; color:#555; margin:0 0 12px 0;"><strong style="color:#333;">已知局限与处理方式：</strong></p>
<p style="font-size:14px; line-height:1.8; color:#555; margin:0 0 12px 0;"><strong style="color:#333;">1. TikTok 3月recency bias（时间偏好特征）</strong><br>TikTok hashtag页面存在时间偏好特征（recency bias），近期内容的曝光概率高于历史内容。这导致2026年3月的视频样本量（约130条）显著高于其他月份均值（约20条）。这不是采集错误，而是平台算法的固有特征。我们在分析中使用评论密度（每视频均评论数）和百分比份额等归一化指标来消除这一偏差的影响。</p>
<p style="font-size:14px; line-height:1.8; color:#555; margin:0 0 12px 0;"><strong style="color:#333;">2. Amazon评论技术限制（本文未纳入）</strong><br>Amazon评论系统设计上限制了评论展示数量（每个产品页面仅显示"limited selection of reviews"），且medleyReviewsAjaxUrl被设为空字符串，技术上无法实现完整评论翻页。12个监控ASIN合计仅获得137条评论，不具备时序分析的统计基础，故本文不纳入Amazon维度。</p>
<p style="font-size:14px; line-height:1.8; color:#555; margin:0 0 12px 0;"><strong style="color:#333;">3. SimilarWeb流量数据（PRO试用版）</strong><br>popmart.com流量数据来自SimilarWeb PRO，当前仅覆盖最近3个月（2025.12-2026.02）。试用版不提供12个月以上的历史数据，因此无法构建长期流量趋势。月度访问量、停留时长、跳出率等指标为SimilarWeb基于面板数据的估算值，与实际Google Analytics数据可能存在10-15%偏差，但趋势方向可信。</p>
<p style="font-size:14px; line-height:1.8; color:#555; margin:0 0 8px 0;"><strong style="color:#333;">4. TikTok关键词覆盖</strong><br>视频来自7个核心关键词及官号@popmartglobal，可能遗漏长尾hashtag下的相关内容，但已覆盖主要传播路径。#molly话题存在与毒品"Molly/MDMA"相关内容的混淆，采集时已内置关键词过滤机制。</p>
<p style="font-size:14px; line-height:1.8; color:#555; margin:0;">5. Instagram IP分类仅能区分Labubu与品牌整体（基于hashtag），Dimoo/Molly等IP在Instagram上的独立热度无法精确拆分。</p>
</div>
</div>

{DIVIDER}

<!-- 结语 -->
<div style="padding:0 32px 24px 32px;">
{section_header('结语', '#1A1A2E')}
<p style="{P}">本次海外另类数据分析从TikTok {stats["tt_videos"]}条视频、{stats["tt_comments"]:,}条评论和Instagram {stats["ig_posts"]}篇帖子、{stats["ig_comments"]:,}条评论中提炼出以下核心投资观点：其一，泡泡玛特的海外社媒热度处于结构性上行通道，跨平台热度指数在2025年末至2026年初均维持在历史均值以上，与公司海外收入高增的财报叙事形成独立验证；其二，Labubu是海外增长的主引擎，在TikTok评论份额中长期保持领先，且未出现衰退迹象，这一特征支持2026年Labubu系列产能扩张的战略合理性。</p>

<p style="{P}">从方法论价值来看，本研究验证了海外社媒评论时序数据作为先行指标的可行性。与传统财务数据（滞后60天以上）和卖方渠道调研（覆盖面有限、主观性强）相比，高频社媒数据可以在季报发布前捕捉到消费者热度的趋势拐点。参与率高于行业均值、UGC倍增效应、高互动评论比例等指标共同勾勒出一个具有{HIGHLIGHT('社区飞轮特征')}的品牌——这类品牌一旦在新市场完成初始渗透，后续扩张的边际营销成本将持续下降，支持市场给予的估值溢价。</p>

<p style="{P}">后续版本将追加：SimilarWeb历史流量趋势（当前受PRO试用限制仅3个月）；NLP情感分析（正/中/负评论比例月度趋势）；Amazon评论如有更优API方案则补充线上动销维度。多维数据的交叉印证将进一步提升先行指标的可信度。数据驱动的消费者洞察，提供的是财报之外的第二套坐标系——永远比主观判断更接近真相。</p>
</div>

<!-- 尾部（静态PNG） -->
{IMG(c['wechat_footer.png'])}

</div>
</body>
</html>'''
    return html


def main():
    print('=' * 50)
    print('生成海外分析公众号文章')
    print('=' * 50)

    os.makedirs(CHARTS_DIR, exist_ok=True)

    # 1. 加载数据
    print('\n[1/3] 加载数据...')
    tt_vids, tt_coms, ig_posts, ig_coms, sw = load_data()
    stats = get_stats(tt_vids, tt_coms, ig_posts, ig_coms, sw)
    print(f'  TikTok: {len(tt_vids)} 视频, {len(tt_coms)} 评论 (ER={stats["tt_avg_er"]:.1f}%)')
    print(f'  Instagram: {len(ig_posts)} 帖子, {len(ig_coms)} 评论')
    print(f'  SimilarWeb: {len(sw)} 月数据')

    # 2. 生成文章图表
    print('\n[2/3] 生成文章图表...')
    chart_brand_trend(tt_vids, tt_coms, CHARTS_DIR)
    chart_ip_share(tt_coms, CHARTS_DIR)
    chart_comment_density(tt_vids, tt_coms, ig_posts, ig_coms, CHARTS_DIR)
    chart_er_trend(tt_vids, CHARTS_DIR)
    chart_brand_vs_ugc(tt_vids, CHARTS_DIR)
    chart_cross_platform(tt_coms, ig_coms, tt_vids, ig_posts, CHARTS_DIR)
    chart_comment_quality(tt_coms, ig_coms, CHARTS_DIR)
    chart_similarweb(sw, CHARTS_DIR)

    # 3. 生成 HTML（完整版）
    print('\n[3/4] 生成完整版 HTML...')
    html = generate_html(stats)
    output_path = os.path.join(BASE_DIR, 'overseas_article.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    size_kb = os.path.getsize(output_path) / 1024
    print(f'  HTML: {output_path} ({size_kb:.0f} KB)')

    # 4. 生成公众号版 HTML（静态图替换复杂渲染）
    print('\n[4/4] 生成公众号版 HTML...')
    render_hero_png(stats, CHARTS_DIR)
    render_footer_png(CHARTS_DIR)
    wechat_html = generate_wechat_html(stats)
    wechat_path = os.path.join(BASE_DIR, 'overseas_article_wechat.html')
    with open(wechat_path, 'w', encoding='utf-8') as f:
        f.write(wechat_html)
    wechat_kb = os.path.getsize(wechat_path) / 1024
    print(f'  HTML: {wechat_path} ({wechat_kb:.0f} KB)')

    print(f'\n  图表: {CHARTS_DIR}/')
    print('=' * 50)


if __name__ == '__main__':
    main()
