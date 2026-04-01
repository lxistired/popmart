"""
泡泡玛特 IP 热度分析 — 微信公众号文章图表生成
Premium Pop Mart brand aesthetic for WeChat article
"""
import sys
import os
import re
import base64
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

# ─── Import data loading ────────────────────────────
from ip_analysis_clean import load_all, BASE_DIR

CHART_DIR = BASE_DIR / 'article_charts'
CHART_DIR.mkdir(exist_ok=True)

# ─── Brand Design System ────────────────────────────
COLORS = {
    '泡泡玛特': '#E53935', 'Labubu': '#FF8F00', 'Dimoo': '#1E88E5',
    'Molly': '#EC407A', 'Skullpanda': '#8E24AA', 'Zsiga': '#43A047',
    '小甜豆': '#FB8C00', '星星人': '#00ACC1', 'Hirono小野': '#6D4C41',
    'Pucky': '#7CB342', 'CryBaby': '#546E7A', '其他': '#BDBDBD',
}

def get_color(ip):
    return COLORS.get(ip, '#BDBDBD')

plt.rcParams.update({
    'font.family': 'Microsoft YaHei',
    'font.size': 12,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.spines.left': True,
    'axes.spines.bottom': True,
    'axes.linewidth': 0.8,
    'axes.edgecolor': '#CCCCCC',
    'axes.grid': True,
    'grid.alpha': 0.15,
    'grid.linewidth': 0.5,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.unicode_minus': False,
    'savefig.facecolor': 'white',
    'savefig.bbox': 'tight',
    'savefig.dpi': 180,
})


def format_month(ym_str):
    """'2025-10' -> '25年10月'"""
    parts = ym_str.split('-')
    if len(parts) == 2:
        return f"{parts[0][2:]}年{int(parts[1])}月"
    return ym_str


# ═══════════════════════════════════════════════════════
#  DATA PREPARATION (reused from ip_analysis_main.py)
# ═══════════════════════════════════════════════════════

print('=' * 50)
print('泡泡玛特 微信文章图表生成')
print('=' * 50)

chart_df, posts_df, comments_df = load_all()

TOP_IPS = chart_df['ip'].value_counts().index.tolist()

# --- comment_pivot: monthly comment count by IP ---
comment_monthly_ip = comments_df.groupby(['ym', 'ip']).agg(
    comment_count=('id', 'size'),
).reset_index()
comment_months = sorted(comments_df['ym'].unique())
comment_pivot = comment_monthly_ip.pivot_table(
    index='ym', columns='ip', values='comment_count', fill_value=0
).reindex(comment_months, fill_value=0)

# Filter to months with >= 20 comments
comment_month_total = comments_df.groupby('ym').size()
valid_comment_months = comment_month_total[comment_month_total >= 20].index
valid_comment_months = sorted(valid_comment_months)

# --- posts with ym for density calc ---
posts_with_ym = posts_df[posts_df['ym'] != ''].copy()
total_comments_monthly = comments_df.groupby('ym').size()
total_posts_monthly = posts_with_ym.groupby('ym').size()

# --- comment density per IP ---
comment_monthly = comments_df.groupby(['ym', 'ip']).size().reset_index(name='cnt')
post_monthly = posts_with_ym.groupby(['ym', 'ip']).size().reset_index(name='post_cnt')
density = comment_monthly.merge(post_monthly, on=['ym', 'ip'], how='left')
density['density'] = density['cnt'] / density['post_cnt'].clip(lower=1)
density_pivot = density.pivot_table(index='ym', columns='ip', values='density', fill_value=0)
valid_density = density_pivot.reindex(valid_comment_months).fillna(0)

# --- decay curves ---
merged = comments_df.merge(
    posts_df[['id', 'post_date_final']].rename(columns={'id': 'post_id'}),
    on='post_id', how='left'
)
merged['post_dt'] = pd.to_datetime(merged['post_date_final'], errors='coerce')
merged['comment_dt'] = pd.to_datetime(merged['clean_date'], errors='coerce')
merged['days_after'] = (merged['comment_dt'] - merged['post_dt']).dt.days
valid_decay = merged[(merged['days_after'] >= 0) & (merged['days_after'] <= 365)].copy()
bins = [0, 7, 14, 21, 30, 60, 90, 180, 366]
decay_labels = ['第1周', '第2周', '第3周', '第4周', '2月', '3月', '4-6月', '6月+']
valid_decay['period'] = pd.cut(valid_decay['days_after'], bins=bins, labels=decay_labels, right=False)
decay_data = valid_decay.groupby(['ip', 'period'], observed=True).size().reset_index(name='count')
decay_pivot = decay_data.pivot_table(index='period', columns='ip', values='count', fill_value=0)
decay_cumsum = decay_pivot.cumsum()
decay_pct = decay_cumsum.div(decay_cumsum.iloc[-1]).fillna(0) * 100

# --- geo distribution ---
loc_df = comments_df[comments_df['location'] != ''].copy()
loc_df['location'] = loc_df['location'].str.strip()
loc_ip = loc_df.groupby(['location', 'ip']).size().reset_index(name='count')
loc_ip_pivot = loc_ip.pivot_table(index='location', columns='ip', values='count', fill_value=0)
loc_ip_pivot['总计'] = loc_ip_pivot.sum(axis=1)
loc_ip_pivot = loc_ip_pivot.sort_values('总计', ascending=False).head(25)

# --- top IP lists ---
db_ips = comments_df['ip'].value_counts().index[:6].tolist()
top6 = db_ips


# ═══════════════════════════════════════════════════════
#  CHART 1: Brand Overall Heat Trend (Dual Axis)
# ═══════════════════════════════════════════════════════

print('\n[1/7] 品牌整体热度趋势 (brand_trend)...')

fig, ax1 = plt.subplots(figsize=(10, 5))

months = valid_comment_months
month_labels = [format_month(m) for m in months]
x = np.arange(len(months))

# Bar data: total comment count per month
bar_vals = total_comments_monthly.reindex(months).fillna(0).values.astype(float)

# Color gradient for bars based on value
vmin, vmax = bar_vals.min(), bar_vals.max()
if vmax == vmin:
    vmax = vmin + 1
norm = plt.Normalize(vmin, vmax)
cmap = mpl.colors.LinearSegmentedColormap.from_list('bar_grad', ['#FFE0B2', '#FF8F00'])
bar_colors = [cmap(norm(v)) for v in bar_vals]

bars = ax1.bar(x, bar_vals, color=bar_colors, width=0.65, zorder=2,
               edgecolor='white', linewidth=0.3)

# Value labels on bars
for i, v in enumerate(bar_vals):
    if v > 0:
        ax1.text(i, v + bar_vals.max() * 0.02, f'{int(v)}',
                 ha='center', va='bottom', fontsize=7.5, color='#666',
                 fontweight='500')

ax1.set_ylabel('月度评论总量', fontsize=11, color='#666', labelpad=8)
ax1.tick_params(axis='y', labelcolor='#888', labelsize=9)

# Right axis: comments per post
ax2 = ax1.twinx()
overall_density = (total_comments_monthly / total_posts_monthly.clip(lower=1)).reindex(months).fillna(0)
ax2.plot(x, overall_density.values, marker='o', markersize=6, color='#E53935',
         linewidth=2.5, zorder=3, markerfacecolor='white', markeredgewidth=2,
         markeredgecolor='#E53935')
ax2.set_ylabel('每帖均评论数', fontsize=11, color='#E53935', labelpad=8)
ax2.tick_params(axis='y', labelcolor='#E53935', labelsize=9)
ax2.spines['right'].set_visible(True)
ax2.spines['right'].set_color('#E53935')
ax2.spines['right'].set_alpha(0.3)

ax1.set_xticks(x)
ax1.set_xticklabels(month_labels, fontsize=9, rotation=0)
ax1.set_title('泡泡玛特小红书评论量与互动密度', fontsize=16, fontweight='bold',
              color='#333', pad=16)

# Legend
legend_elements = [
    Patch(facecolor='#FF8F00', alpha=0.7, label='月度评论总量'),
    Line2D([0], [0], color='#E53935', marker='o', markersize=6,
           markerfacecolor='white', markeredgecolor='#E53935', linewidth=2.5,
           label='每帖均评论数'),
]
legend = ax1.legend(handles=legend_elements, loc='upper left', fontsize=9,
                    framealpha=0.9, edgecolor='#ddd',
                    fancybox=True, borderpad=0.8)
legend.get_frame().set_linewidth(0.5)

ax1.set_xlim(-0.6, len(months) - 0.4)
plt.tight_layout()
fig.savefig(CHART_DIR / 'brand_trend.png')
plt.close(fig)
print('  -> brand_trend.png saved')


# ═══════════════════════════════════════════════════════
#  CHART 2: Monthly IP Comment Share (Stacked Area)
# ═══════════════════════════════════════════════════════

print('[2/7] 月度评论份额 (comment_share)...')

fig, ax = plt.subplots(figsize=(10, 5.5))

comment_share_pivot = comment_pivot.reindex(valid_comment_months).fillna(0)
share = comment_share_pivot.div(comment_share_pivot.sum(axis=1), axis=0).fillna(0) * 100

# Top 6 IPs + others
top6_share = db_ips[:6]
other_cols = [c for c in share.columns if c not in top6_share]

x_area = np.arange(len(share))
bottom = np.zeros(len(share))

# Stack areas
for ip in top6_share:
    if ip in share.columns:
        vals = share[ip].values
        ax.fill_between(x_area, bottom, bottom + vals,
                        label=ip, color=get_color(ip), alpha=0.85,
                        linewidth=0.5, edgecolor='white')
        # Right-edge label
        mid_y = bottom[-1] + vals[-1] / 2
        if vals[-1] > 3:
            ax.text(len(share) - 0.8, mid_y, ip, fontsize=7.5,
                    va='center', color=get_color(ip), fontweight='600')
        bottom += vals

if other_cols:
    other_vals = share[other_cols].sum(axis=1).values
    ax.fill_between(x_area, bottom, bottom + other_vals,
                    label='其他', color='#BDBDBD', alpha=0.6,
                    linewidth=0.5, edgecolor='white')
    mid_y = bottom[-1] + other_vals[-1] / 2
    if other_vals[-1] > 3:
        ax.text(len(share) - 0.8, mid_y, '其他', fontsize=7.5,
                va='center', color='#999')

month_labels_share = [format_month(m) for m in share.index]
ax.set_xticks(x_area)
ax.set_xticklabels(month_labels_share, fontsize=9, rotation=0)
ax.set_ylabel('份额 (%)', fontsize=11, color='#666')
ax.set_ylim(0, 100)
ax.set_yticks([0, 25, 50, 75, 100])
ax.set_yticklabels(['0%', '25%', '50%', '75%', '100%'], fontsize=9)
ax.set_title('各IP月度评论份额分布', fontsize=16, fontweight='bold', color='#333', pad=16)

legend = ax.legend(loc='upper left', fontsize=8.5, framealpha=0.9,
                   edgecolor='#ddd', fancybox=True, borderpad=0.8, ncol=2)
legend.get_frame().set_linewidth(0.5)

ax.set_xlim(-0.5, len(share) - 0.5)
plt.tight_layout()
fig.savefig(CHART_DIR / 'comment_share.png')
plt.close(fig)
print('  -> comment_share.png saved')


# ═══════════════════════════════════════════════════════
#  CHART 3: IP Monthly Ranking Bump Chart
# ═══════════════════════════════════════════════════════

print('[3/7] IP排名演变 (rank_evolution)...')

fig, ax = plt.subplots(figsize=(10, 5.5))

valid_comments = comment_share_pivot
comment_rank = valid_comments.rank(axis=1, ascending=False, method='min')

month_labels_rank = [format_month(m) for m in comment_rank.index]

for ip in db_ips:
    if ip in comment_rank.columns:
        vals = comment_rank[ip].values
        mask = valid_comments[ip].values > 0
        x_r = np.arange(len(comment_rank))[mask]
        y_r = vals[mask]
        ax.plot(x_r, y_r, marker='o', markersize=8, label=ip,
                color=get_color(ip), linewidth=3, alpha=0.9,
                markerfacecolor='white', markeredgewidth=2.5,
                markeredgecolor=get_color(ip), zorder=3)
        # Labels at left and right endpoints
        if len(x_r) > 0:
            ax.text(x_r[0] - 0.25, y_r[0], ip, fontsize=8,
                    color=get_color(ip), va='center', ha='right', fontweight='600')
            ax.text(x_r[-1] + 0.25, y_r[-1], ip, fontsize=8,
                    color=get_color(ip), va='center', ha='left', fontweight='600')

ax.set_xticks(range(len(comment_rank.index)))
ax.set_xticklabels(month_labels_rank, fontsize=9, rotation=0)

max_rank = min(8, len(db_ips) + 2)
ax.invert_yaxis()
ax.set_ylim(max_rank + 0.5, 0.5)
ax.set_yticks(range(1, max_rank + 1))
rank_labels = ['1st', '2nd', '3rd'] + [f'{i}th' for i in range(4, max_rank + 1)]
ax.set_yticklabels(rank_labels[:max_rank], fontsize=9)
ax.set_ylabel('评论量排名', fontsize=11, color='#666')
ax.set_title('IP月度评论量排名演变', fontsize=16, fontweight='bold', color='#333', pad=16)

# No legend needed since labels are at endpoints
ax.set_xlim(-1.5, len(comment_rank) + 0.5)
plt.tight_layout()
fig.savefig(CHART_DIR / 'rank_evolution.png')
plt.close(fig)
print('  -> rank_evolution.png saved')


# ═══════════════════════════════════════════════════════
#  CHART 4: Monthly Comments Per Post by IP
# ═══════════════════════════════════════════════════════

print('[4/7] 评论密度趋势 (comment_density)...')

fig, ax = plt.subplots(figsize=(10, 5))

# Show top 5 IPs only
top5_density = db_ips[:5]
month_labels_den = [format_month(m) for m in valid_density.index]

for ip in top5_density:
    if ip in valid_density.columns:
        vals = valid_density[ip].values
        x_d = np.arange(len(valid_density))
        ax.plot(x_d, vals, marker='o', markersize=5, label=ip,
                color=get_color(ip), linewidth=2, alpha=0.9,
                markerfacecolor='white', markeredgewidth=1.5,
                markeredgecolor=get_color(ip))
        # Subtle fill
        ax.fill_between(x_d, vals, alpha=0.05, color=get_color(ip))

ax.set_xticks(range(len(valid_density.index)))
ax.set_xticklabels(month_labels_den, fontsize=9, rotation=0)
ax.set_ylabel('每帖均评论数', fontsize=11, color='#666')
ax.set_title('各IP月度评论密度对比', fontsize=16, fontweight='bold', color='#333', pad=16)

legend = ax.legend(loc='best', fontsize=9, framealpha=0.9,
                   edgecolor='#ddd', fancybox=True, borderpad=0.8)
legend.get_frame().set_linewidth(0.5)

plt.tight_layout()
fig.savefig(CHART_DIR / 'comment_density.png')
plt.close(fig)
print('  -> comment_density.png saved')


# ═══════════════════════════════════════════════════════
#  CHART 5: Comment Lifecycle (Single Clean Panel)
# ═══════════════════════════════════════════════════════

print('[5/7] 评论生命周期 (decay_curves)...')

fig, ax = plt.subplots(figsize=(10, 5))

top5_decay = db_ips[:5]

# 50% and 80% reference lines
ax.axhline(y=50, color='#CCCCCC', linestyle='--', linewidth=0.8, zorder=1)
ax.axhline(y=80, color='#CCCCCC', linestyle='--', linewidth=0.8, zorder=1)
ax.text(-0.3, 51, '50%', fontsize=8, color='#999', va='bottom')
ax.text(-0.3, 81, '80%', fontsize=8, color='#999', va='bottom')

for ip in top5_decay:
    if ip in decay_pct.columns:
        vals = decay_pct[ip].values
        x_dc = np.arange(len(vals))
        ax.plot(x_dc, vals, marker='o', markersize=7, label=ip,
                color=get_color(ip), linewidth=2.5, alpha=0.9,
                markerfacecolor=get_color(ip), markeredgewidth=1,
                markeredgecolor='white', zorder=3)

        # Find 80% milestone and annotate
        for j in range(len(vals)):
            if vals[j] >= 80:
                ax.annotate(f'{vals[j]:.0f}%',
                            xy=(x_dc[j], vals[j]),
                            xytext=(x_dc[j] + 0.3, vals[j] - 5),
                            fontsize=7, color=get_color(ip), fontweight='600',
                            arrowprops=dict(arrowstyle='->', color=get_color(ip),
                                            lw=0.8, connectionstyle='arc3,rad=0.2'))
                break

ax.set_xticks(range(len(decay_labels)))
ax.set_xticklabels(decay_labels, fontsize=9)
ax.set_ylabel('累计评论占比 (%)', fontsize=11, color='#666')
ax.set_ylim(0, 105)
ax.set_title('各IP评论累计到达曲线', fontsize=16, fontweight='bold', color='#333', pad=16)

legend = ax.legend(loc='lower right', fontsize=9, framealpha=0.9,
                   edgecolor='#ddd', fancybox=True, borderpad=0.8)
legend.get_frame().set_linewidth(0.5)

plt.tight_layout()
fig.savefig(CHART_DIR / 'decay_curves.png')
plt.close(fig)
print('  -> decay_curves.png saved')


# ═══════════════════════════════════════════════════════
#  CHART 6: Top 15 Geographic Distribution
# ═══════════════════════════════════════════════════════

print('[6/7] 地域分布 (geo_distribution)...')

fig, ax = plt.subplots(figsize=(10, 6))

top15_loc = loc_ip_pivot.head(15).copy()
totals_geo = top15_loc['总计'].values
top15_data = top15_loc.drop(columns=['总计'], errors='ignore')

# Reverse order for horizontal bar (top province at top)
provinces = top15_data.index.tolist()[::-1]
top15_reversed = top15_data.loc[provinces]
totals_reversed = totals_geo[::-1]

y_pos = np.arange(len(provinces))
bar_bottom = np.zeros(len(provinces))

for ip in top6:
    if ip in top15_reversed.columns:
        vals = top15_reversed[ip].values
        ax.barh(y_pos, vals, left=bar_bottom, label=ip,
                color=get_color(ip), alpha=0.85, height=0.7,
                edgecolor='white', linewidth=0.3)
        bar_bottom += vals

# Other IPs
other_cols_geo = [c for c in top15_reversed.columns if c not in top6]
if other_cols_geo:
    other_vals_geo = top15_reversed[other_cols_geo].sum(axis=1).values
    ax.barh(y_pos, other_vals_geo, left=bar_bottom, label='其他',
            color='#BDBDBD', alpha=0.5, height=0.7,
            edgecolor='white', linewidth=0.3)

# Value labels at end of bars
for i, total in enumerate(totals_reversed):
    ax.text(total + totals_reversed.max() * 0.02, i, f'{int(total)}',
            va='center', fontsize=8.5, color='#555', fontweight='500')

ax.set_yticks(y_pos)
ax.set_yticklabels(provinces, fontsize=10)
ax.set_xlabel('评论数', fontsize=11, color='#666')
ax.set_title('评论者地域分布Top15', fontsize=16, fontweight='bold', color='#333', pad=16)

legend = ax.legend(loc='lower right', fontsize=8.5, framealpha=0.9,
                   edgecolor='#ddd', fancybox=True, borderpad=0.8, ncol=2)
legend.get_frame().set_linewidth(0.5)

ax.set_xlim(0, totals_reversed.max() * 1.15)
plt.tight_layout()
fig.savefig(CHART_DIR / 'geo_distribution.png')
plt.close(fig)
print('  -> geo_distribution.png saved')


# ═══════════════════════════════════════════════════════
#  CHART 7: Scatter Plot — Likes vs Comments
# ═══════════════════════════════════════════════════════

print('[7/7] 点赞vs评论散点 (likes_vs_comments)...')

fig, ax = plt.subplots(figsize=(9, 6))

scatter_df = posts_df[posts_df['comment_count'] > 0].copy()
scatter_top6 = top6[:6]

# Compute medians for quadrant lines
med_likes = scatter_df['likes'].median()
med_comments = scatter_df['comment_count'].median()

# Quadrant dividers
ax.axvline(x=med_likes, color='#E0E0E0', linestyle='-', linewidth=1, zorder=1)
ax.axhline(y=med_comments, color='#E0E0E0', linestyle='-', linewidth=1, zorder=1)

# Quadrant labels
x_max = scatter_df['likes'].quantile(0.98)
y_max = scatter_df['comment_count'].quantile(0.98)

ax.text(x_max * 0.85, y_max * 0.9, '高赞高评', fontsize=10, color='#999',
        ha='center', va='center', fontweight='500', alpha=0.7)
ax.text(x_max * 0.15, y_max * 0.9, '低赞高评', fontsize=10, color='#999',
        ha='center', va='center', fontweight='500', alpha=0.7)
ax.text(x_max * 0.85, y_max * 0.1, '高赞低评', fontsize=10, color='#999',
        ha='center', va='center', fontweight='500', alpha=0.7)
ax.text(x_max * 0.15, y_max * 0.1, '低赞低评', fontsize=10, color='#999',
        ha='center', va='center', fontweight='500', alpha=0.7)

for ip in scatter_top6:
    sub = scatter_df[scatter_df['ip'] == ip]
    if len(sub) > 0:
        ax.scatter(sub['likes'], sub['comment_count'],
                   label=ip, color=get_color(ip), alpha=0.6, s=60,
                   edgecolors='white', linewidths=0.5, zorder=2)

ax.set_xlabel('帖子点赞数', fontsize=11, color='#666')
ax.set_ylabel('深挖评论数', fontsize=11, color='#666')
ax.set_title('帖子点赞 vs 评论数', fontsize=16, fontweight='bold', color='#333', pad=16)

# Limit axis to reasonable range
ax.set_xlim(0, x_max)
ax.set_ylim(0, y_max)

legend = ax.legend(loc='upper right', fontsize=9, framealpha=0.9,
                   edgecolor='#ddd', fancybox=True, borderpad=0.8)
legend.get_frame().set_linewidth(0.5)

plt.tight_layout()
fig.savefig(CHART_DIR / 'likes_vs_comments.png')
plt.close(fig)
print('  -> likes_vs_comments.png saved')


# ═══════════════════════════════════════════════════════
#  VERIFY OUTPUT
# ═══════════════════════════════════════════════════════

print('\n' + '=' * 50)
print('图表文件检查:')
chart_files = [
    'brand_trend.png', 'comment_share.png', 'rank_evolution.png',
    'comment_density.png', 'decay_curves.png', 'geo_distribution.png',
    'likes_vs_comments.png',
]
all_ok = True
for fname in chart_files:
    fpath = CHART_DIR / fname
    if fpath.exists():
        size_kb = fpath.stat().st_size / 1024
        print(f'  {fname}: {size_kb:.0f} KB')
    else:
        print(f'  {fname}: MISSING!')
        all_ok = False

if not all_ok:
    print('\nERROR: Some chart files are missing!')
    sys.exit(1)


# ═══════════════════════════════════════════════════════
#  UPDATE HTML WITH NEW CHARTS
# ═══════════════════════════════════════════════════════

print('\n' + '=' * 50)
print('更新 popmart_article_v2.html ...')

html_path = BASE_DIR / 'popmart_article_v2.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html_content = f.read()

# Chart mapping: HTML comment identifier -> chart filename
chart_mapping = {
    'brand_trend': 'brand_trend.png',
    'comment_share': 'comment_share.png',
    'rank_evolution': 'rank_evolution.png',
    'comment_density': 'comment_density.png',
    'decay_curves': 'decay_curves.png',
    'geo_distribution': 'geo_distribution.png',
    'likes_vs_comments': 'likes_vs_comments.png',
}

# Strategy: find each <!-- Chart: xxx --> comment, then replace the next
# data:image/png;base64,... in the <img> tag that follows

replacements = 0
for chart_id, chart_file in chart_mapping.items():
    chart_path = CHART_DIR / chart_file
    if not chart_path.exists():
        print(f'  WARNING: {chart_file} not found, skipping')
        continue

    # Read chart and encode to base64
    with open(chart_path, 'rb') as f:
        chart_b64 = base64.b64encode(f.read()).decode('ascii')

    # Find the marker comment and the img tag that follows
    marker = f'<!-- Chart: {chart_id} -->'
    marker_pos = html_content.find(marker)
    if marker_pos < 0:
        print(f'  WARNING: marker "{marker}" not found in HTML')
        continue

    # Find the next <img src="data:image/png;base64,..." after the marker
    # The img tags have style attrs and end with />
    search_start = marker_pos
    img_pattern = re.compile(
        r'(<img\s+src="data:image/png;base64,)[A-Za-z0-9+/=\s]+("\s*[^>]*/>)',
        re.DOTALL
    )
    match = img_pattern.search(html_content, search_start)
    if match:
        old_start = match.start()
        old_end = match.end()
        new_img = match.group(1) + chart_b64 + match.group(2)
        html_content = html_content[:old_start] + new_img + html_content[old_end:]
        replacements += 1
        print(f'  Replaced: {chart_id} ({len(chart_b64) // 1024}KB base64)')
    else:
        print(f'  WARNING: No img tag found after marker "{marker}"')

print(f'\nTotal replacements: {replacements}/7')

# Save updated HTML
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f'HTML updated: {html_path}')
new_size = html_path.stat().st_size
print(f'New file size: {new_size / 1024:.0f} KB')

print('\n' + '=' * 50)
print('DONE!')
