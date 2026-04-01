"""
泡泡玛特 IP 热度分析 — 可视化模块 v2
修正采样偏差：用归一化指标 + 月内IP份额 + 评论生命周期
"""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# 中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'STHeiti']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 150

# IP固定配色
COLOR_MAP = {
    '泡泡玛特': '#D32F2F', 'Labubu': '#FF6F00', 'Dimoo': '#1976D2',
    'Molly': '#E91E63', 'Skullpanda': '#7B1FA2', 'Zsiga': '#388E3C',
    '小甜豆': '#F57C00', '星星人': '#0097A7', 'Hirono小野': '#5D4037',
    'Pucky': '#689F38', 'CryBaby': '#455A64',
}

def get_color(ip):
    return COLOR_MAP.get(ip, '#999999')


def generate_all_charts(chart_df, posts_df, comments_df, heat_pivot,
                        posts_pivot, likes_pivot, comment_pivot, decay_pct,
                        loc_ip_pivot, ip_overview, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    top6 = [r['ip'] for r in ip_overview[:6]]
    db_ips = comments_df['ip'].value_counts().index[:6].tolist()

    # 只保留样本量>=5的月份，避免噪声
    MIN_POSTS = 5
    monthly_totals = posts_pivot.sum(axis=1)
    valid_months = monthly_totals[monthly_totals >= MIN_POSTS].index

    # ── Chart 1: 月度评论密度趋势（每帖均评论数，核心指标）──
    print('  图1: 月度评论密度趋势...')
    # 按评论自身的月份×IP统计评论量
    comment_monthly = comments_df.groupby(['ym', 'ip']).size().reset_index(name='cnt')
    # 按帖子发布月份×IP统计帖子数（用DB posts）
    posts_with_ym = posts_df[posts_df['ym'] != ''].copy()
    post_monthly = posts_with_ym.groupby(['ym', 'ip']).size().reset_index(name='post_cnt')
    # 合并算每帖均评论
    density = comment_monthly.merge(post_monthly, on=['ym', 'ip'], how='left')
    density['density'] = density['cnt'] / density['post_cnt'].clip(lower=1)
    density_pivot = density.pivot_table(index='ym', columns='ip', values='density', fill_value=0)
    # 过滤有效月份（评论数>=20的月份）
    comment_month_total = comments_df.groupby('ym').size()
    valid_comment_months = comment_month_total[comment_month_total >= 20].index
    valid_density = density_pivot.reindex(valid_comment_months).fillna(0)

    fig, ax = plt.subplots(figsize=(14, 6))
    for ip in db_ips:
        if ip in valid_density.columns:
            vals = valid_density[ip]
            ax.plot(range(len(vals)), vals, marker='o', markersize=5,
                    label=ip, color=get_color(ip), linewidth=2, alpha=0.85)
    ax.set_xticks(range(len(valid_density.index)))
    ax.set_xticklabels(valid_density.index, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('每帖平均评论数')
    ax.set_title('各IP月度评论密度（每帖均评论，基于评论时间戳）', fontsize=14, fontweight='bold')
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    fig.savefig(output_dir / 'chart1_comment_density.png')
    plt.close(fig)

    # ── Chart 1b: 泡泡玛特整体品牌热度走势（全IP合计月均评论）──
    print('  图1b: 品牌整体热度走势...')
    # 全IP合计：月评论总量 / 月帖子总量 = 整体评论密度
    total_comments_monthly = comments_df.groupby('ym').size()
    total_posts_monthly = posts_with_ym.groupby('ym').size()
    overall_density = (total_comments_monthly / total_posts_monthly.clip(lower=1)).reindex(valid_comment_months).fillna(0)

    fig, ax1 = plt.subplots(figsize=(14, 6))
    # 柱状图：月评论绝对量
    ax1.bar(range(len(valid_comment_months)),
            total_comments_monthly.reindex(valid_comment_months).fillna(0).values,
            color='#E0E0E0', alpha=0.6, label='月评论总量')
    ax1.set_ylabel('月评论总量', color='gray')
    ax1.tick_params(axis='y', labelcolor='gray')

    # 折线图：每帖均评论（右轴）
    ax2 = ax1.twinx()
    ax2.plot(range(len(overall_density)), overall_density.values,
             marker='o', markersize=6, color='#D32F2F', linewidth=2.5,
             label='每帖均评论数')
    ax2.set_ylabel('每帖均评论数', color='#D32F2F')
    ax2.tick_params(axis='y', labelcolor='#D32F2F')

    ax1.set_xticks(range(len(valid_comment_months)))
    ax1.set_xticklabels(valid_comment_months, rotation=45, ha='right', fontsize=8)
    ax1.set_title('泡泡玛特整体品牌热度走势（评论维度）', fontsize=14, fontweight='bold')

    # 合并图例
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc='upper left', fontsize=9)

    plt.tight_layout()
    fig.savefig(output_dir / 'chart1b_brand_trend.png')
    plt.close(fig)

    # ── Chart 2: 月内IP评论份额（基于评论时间戳）──
    print('  图2: 月内IP评论份额...')
    comment_share_pivot = comment_pivot.reindex(valid_comment_months).fillna(0)
    share = comment_share_pivot.div(comment_share_pivot.sum(axis=1), axis=0).fillna(0) * 100
    fig, ax = plt.subplots(figsize=(14, 6))
    bottom = np.zeros(len(share))
    for ip in db_ips:
        if ip in share.columns:
            vals = share[ip].values
            ax.fill_between(range(len(share)), bottom, bottom + vals,
                            label=ip, color=get_color(ip), alpha=0.7)
            bottom += vals
    other_cols = [c for c in share.columns if c not in db_ips]
    if other_cols:
        other_vals = share[other_cols].sum(axis=1).values
        ax.fill_between(range(len(share)), bottom, bottom + other_vals,
                        label='其他', color='#BDBDBD', alpha=0.5)
    ax.set_xticks(range(len(share.index)))
    ax.set_xticklabels(share.index, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('份额 (%)')
    ax.set_ylim(0, 100)
    ax.set_title('月内IP评论份额（基于评论时间戳，消除采样偏差）', fontsize=14, fontweight='bold')
    ax.legend(loc='center left', bbox_to_anchor=(1, 0.5), fontsize=9)
    plt.tight_layout()
    fig.savefig(output_dir / 'chart2_comment_share.png')
    plt.close(fig)

    # ── Chart 3: 评论生命周期衰减曲线（完全不受采样偏差影响）──
    print('  图3: 评论生命周期衰减...')
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # 左：累计百分比
    for ip in db_ips:
        if ip in decay_pct.columns:
            vals = decay_pct[ip].values
            ax1.plot(range(len(vals)), vals, marker='s', markersize=5,
                     label=ip, color=get_color(ip), linewidth=2)
    ax1.set_xticks(range(len(decay_pct.index)))
    ax1.set_xticklabels(decay_pct.index, fontsize=9)
    ax1.set_ylabel('累计评论占比 (%)')
    ax1.set_title('评论累计到达曲线', fontweight='bold')
    ax1.legend(fontsize=8)
    ax1.grid(axis='y', alpha=0.3)
    ax1.set_ylim(0, 105)
    ax1.axhline(y=80, color='gray', linestyle='--', alpha=0.5)
    ax1.annotate('80%线', xy=(0.5, 82), fontsize=8, color='gray')

    # 右：各时段增量占比（柱状图）
    decay_incr = decay_pct.diff().fillna(decay_pct.iloc[0])
    x = np.arange(len(decay_incr.index))
    width = 0.12
    for i, ip in enumerate(db_ips[:5]):
        if ip in decay_incr.columns:
            ax2.bar(x + i * width, decay_incr[ip].values, width,
                    label=ip, color=get_color(ip), alpha=0.85)
    ax2.set_xticks(x + width * 2)
    ax2.set_xticklabels(decay_incr.index, fontsize=8)
    ax2.set_ylabel('评论增量占比 (%)')
    ax2.set_title('各时段评论增量分布', fontweight='bold')
    ax2.legend(fontsize=7)

    plt.suptitle('评论生命周期分析（不受帖子采样偏差影响）',
                 fontsize=14, fontweight='bold')
    plt.tight_layout()
    fig.savefig(output_dir / 'chart3_decay_curves.png')
    plt.close(fig)

    # ── Chart 4: 月内IP评论量排名变化 (Bump Chart) ──
    print('  图4: 评论量排名变化...')
    valid_comments = comment_share_pivot  # 已按valid_comment_months过滤
    comment_rank = valid_comments.rank(axis=1, ascending=False, method='min')
    fig, ax = plt.subplots(figsize=(14, 6))
    for ip in db_ips:
        if ip in comment_rank.columns:
            vals = comment_rank[ip].values
            mask = valid_comments[ip].values > 0
            x = np.arange(len(comment_rank))[mask]
            y = vals[mask]
            ax.plot(x, y, marker='o', markersize=7, label=ip,
                    color=get_color(ip), linewidth=2.5)
            if len(x) > 0:
                ax.annotate(ip, xy=(x[-1] + 0.15, y[-1]), fontsize=8,
                            color=get_color(ip), va='center')
    ax.set_xticks(range(len(comment_rank.index)))
    ax.set_xticklabels(comment_rank.index, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('排名（1=评论最多）')
    ax.set_title('各IP月度评论量排名变化', fontsize=14, fontweight='bold')
    ax.invert_yaxis()
    ax.set_ylim(min(8, len(db_ips) + 1) + 0.5, 0.5)
    ax.legend(loc='center left', bbox_to_anchor=(1, 0.5), fontsize=9)
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    fig.savefig(output_dir / 'chart4_rank_evolution.png')
    plt.close(fig)

    # ── Chart 5: 地域分布 ──
    print('  图5: 地域分布...')
    top15_loc = loc_ip_pivot.head(15).drop(columns=['总计'], errors='ignore')
    fig, ax = plt.subplots(figsize=(12, 7))
    bar_bottom = np.zeros(len(top15_loc))
    for ip in top6:
        if ip in top15_loc.columns:
            vals = top15_loc[ip].values
            ax.barh(range(len(top15_loc)), vals, left=bar_bottom,
                    label=ip, color=get_color(ip), alpha=0.85)
            bar_bottom += vals
    other_cols = [c for c in top15_loc.columns if c not in top6]
    if other_cols:
        other_vals = top15_loc[other_cols].sum(axis=1).values
        ax.barh(range(len(top15_loc)), other_vals, left=bar_bottom,
                label='其他', color='#BDBDBD', alpha=0.5)
    ax.set_yticks(range(len(top15_loc)))
    ax.set_yticklabels(top15_loc.index, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel('评论数')
    ax.set_title('Top15地区评论分布（按IP着色）', fontsize=14, fontweight='bold')
    ax.legend(loc='lower right', fontsize=9)
    plt.tight_layout()
    fig.savefig(output_dir / 'chart5_geo_distribution.png')
    plt.close(fig)

    # ── Chart 6: 点赞 vs 评论散点 ──
    print('  图6: 点赞vs评论散点...')
    scatter_df = posts_df[posts_df['comment_count'] > 0].copy()
    fig, ax = plt.subplots(figsize=(10, 7))
    for ip in top6:
        sub = scatter_df[scatter_df['ip'] == ip]
        if len(sub) > 0:
            ax.scatter(sub['likes'], sub['comment_count'],
                       label=ip, color=get_color(ip), alpha=0.7, s=50, edgecolors='white')
    ax.set_xlabel('帖子点赞数')
    ax.set_ylabel('深挖评论数')
    ax.set_title('帖子点赞 vs 评论数（按IP）', fontsize=14, fontweight='bold')
    ax.legend(fontsize=9)
    ax.grid(alpha=0.2)
    plt.tight_layout()
    fig.savefig(output_dir / 'chart6_likes_vs_comments.png')
    plt.close(fig)

    # ── Chart 7: 综合仪表盘 v2 ──
    print('  图7: 综合仪表盘v2...')
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))

    # 7a: 月内IP评论份额变化（柱状堆叠）
    ax = axes[0, 0]
    bottom = np.zeros(len(share))
    for ip in db_ips:
        if ip in share.columns:
            vals = share[ip].values
            ax.bar(range(len(share)), vals, bottom=bottom,
                   label=ip, color=get_color(ip), alpha=0.8)
            bottom += vals
    step = max(1, len(share) // 6)
    ax.set_xticks(range(0, len(share), step))
    ax.set_xticklabels([share.index[i] for i in range(0, len(share), step)],
                       rotation=45, fontsize=7)
    ax.set_ylabel('%')
    ax.set_title('月内IP评论份额', fontweight='bold')
    ax.legend(fontsize=5, ncol=2)

    # 7b: 月度评论密度折线（每帖均评论数）
    ax = axes[0, 1]
    for ip in db_ips[:4]:
        if ip in valid_density.columns:
            ax.plot(range(len(valid_density)), valid_density[ip].values,
                    label=ip, color=get_color(ip), linewidth=1.5)
    step = max(1, len(valid_density) // 6)
    ax.set_xticks(range(0, len(valid_density), step))
    ax.set_xticklabels([valid_density.index[i] for i in range(0, len(valid_density), step)],
                       rotation=45, fontsize=7)
    ax.set_title('月度评论密度（均评论/帖）', fontweight='bold')
    ax.legend(fontsize=7)

    # 7c: 评论生命周期（衰减曲线缩略）
    ax = axes[0, 2]
    for ip in db_ips[:4]:
        if ip in decay_pct.columns:
            ax.plot(range(len(decay_pct)), decay_pct[ip].values,
                    label=ip, color=get_color(ip), linewidth=1.5)
    ax.set_xticks(range(len(decay_pct.index)))
    ax.set_xticklabels(decay_pct.index, fontsize=6, rotation=30)
    ax.set_title('评论生命周期', fontweight='bold')
    ax.set_ylabel('累计%')
    ax.legend(fontsize=7)
    ax.axhline(y=80, color='gray', linestyle='--', alpha=0.4)

    # 7d: 每帖平均评论数（互动密度）
    ax = axes[1, 0]
    cmt_per_post = {}
    for ip in top6:
        ip_posts_count = len(chart_df[chart_df['ip'] == ip])
        ip_comments = len(comments_df[comments_df['ip'] == ip])
        if ip_posts_count > 0:
            cmt_per_post[ip] = ip_comments / ip_posts_count
    sorted_ips = sorted(cmt_per_post, key=cmt_per_post.get, reverse=True)
    vals = [cmt_per_post[ip] for ip in sorted_ips]
    bars = ax.barh(range(len(sorted_ips)), vals,
                   color=[get_color(ip) for ip in sorted_ips], alpha=0.85)
    ax.set_yticks(range(len(sorted_ips)))
    ax.set_yticklabels(sorted_ips, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel('平均评论/帖')
    ax.set_title('各IP互动密度（评论/帖子）', fontweight='bold')
    for i, v in enumerate(vals):
        ax.text(v + 0.2, i, f'{v:.1f}', va='center', fontsize=8)

    # 7e: 地域Top5饼图
    ax = axes[1, 1]
    top5_loc = loc_ip_pivot.head(5)
    totals = top5_loc.drop(columns=['总计'], errors='ignore').sum(axis=1)
    colors_pie = ['#D32F2F', '#FF6F00', '#1976D2', '#E91E63', '#388E3C']
    ax.pie(totals.values, labels=totals.index, colors=colors_pie,
           autopct='%1.1f%%', textprops={'fontsize': 9})
    ax.set_title('评论来源Top5地区', fontweight='bold')

    # 7f: 采样量分布（让用户看到偏差有多大）
    ax = axes[1, 2]
    monthly_count = chart_df['ym'].value_counts().sort_index()
    valid_idx = [m for m in monthly_count.index if m in valid_months]
    invalid_idx = [m for m in monthly_count.index if m not in valid_months]
    all_idx = monthly_count.index.tolist()
    colors_bar = ['#4CAF50' if m in valid_months else '#EF9A9A' for m in all_idx]
    ax.bar(range(len(all_idx)), monthly_count.values, color=colors_bar, alpha=0.8)
    step = max(1, len(all_idx) // 6)
    ax.set_xticks(range(0, len(all_idx), step))
    ax.set_xticklabels([all_idx[i] for i in range(0, len(all_idx), step)],
                       rotation=45, fontsize=7)
    ax.set_title('月度采样量（绿=纳入分析，红=样本不足）', fontweight='bold')
    ax.set_ylabel('帖子数')

    plt.suptitle('泡泡玛特 IP 热度分析 v2（修正采样偏差）',
                 fontsize=16, fontweight='bold', y=1.01)
    plt.tight_layout()
    fig.savefig(output_dir / 'chart7_dashboard_v2.png', bbox_inches='tight')
    plt.close(fig)

    print(f'  ✅ 7张图表已保存到 {output_dir}/')
