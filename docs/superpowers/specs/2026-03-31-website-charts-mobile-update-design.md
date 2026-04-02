# 网站图表增强 + 移动端适配 + 更新机制 设计文档

## 目标

将首页从 1 张有问题的周趋势图升级为 5 张月度 ECharts 交互式图表，全站适配移动端，更新机制从哑脚本改为 Claude Code 驱动。

## 范围

三个独立子系统，可串行实现：

1. **数据导出扩展** — `export_json.py` 新增 5 个导出函数
2. **前端图表组件** — 5 个新 Astro + ECharts 组件，替换现有 TrendChart
3. **移动端适配** — 纯 CSS `@media` 断点，不改组件结构
4. **更新机制** — `daily_update.bat` 改为提醒/自动启动 Claude Code

---

## 1. 数据导出扩展

### 新增 JSON 文件

在 `export_json.py` 中新增以下导出函数，输出到 `website/src/data/` 和 `website/public/data/`：

| 文件名 | 内容 | 导出函数 |
|--------|------|----------|
| `brand-trend.json` | 月度评论量 + 视频量 + 评论密度 | `export_brand_trend()` |
| `ip-share-trend.json` | 月度各IP评论份额% | `export_ip_share_trend()` |
| `cross-platform-index.json` | 双平台月度评论密度归一化指数 | `export_cross_platform_index()` |
| `brand-vs-ugc.json` | 品牌官号 vs UGC 四维度对比 | `export_brand_vs_ugc()` |
| `comment-quality.json` | 按点赞数分层的评论质量占比 | `export_comment_quality()` |

### 数据结构

**brand-trend.json:**
```json
[
  {"month": "2025-04", "comments": 120, "videos": 15, "density": 8.0},
  {"month": "2025-05", "comments": 340, "videos": 28, "density": 12.1}
]
```

**ip-share-trend.json:**
```json
[
  {"month": "2025-04", "ip": "Labubu", "share_pct": 45.2, "count": 120},
  {"month": "2025-04", "ip": "Dimoo", "share_pct": 22.1, "count": 59}
]
```

**cross-platform-index.json:**
```json
[
  {"month": "2025-04", "platform": "TikTok", "index": 85.3, "density": 12.1},
  {"month": "2025-04", "platform": "Instagram", "index": 110.5, "density": 28.3}
]
```
- `index` = 该平台月度评论密度 / 该平台全期均值 × 100
- 使用 3 月滚动平均平滑

**brand-vs-ugc.json:**
```json
{
  "brand": {"avg_views": 1200000, "avg_likes": 45000, "avg_er_pct": 3.2, "avg_comments": 280},
  "ugc": {"avg_views": 850000, "avg_likes": 32000, "avg_er_pct": 4.1, "avg_comments": 150}
}
```

**comment-quality.json:**
```json
[
  {"platform": "TikTok", "high_pct": 8.2, "med_pct": 15.3, "low_pct": 76.5, "total": 14099},
  {"platform": "Instagram", "high_pct": 12.1, "med_pct": 18.7, "low_pct": 69.2, "total": 4677}
]
```
- high: likes >= 10, med: 3-9, low: < 3

### 分类逻辑

复用 `export_json.py` 已有的 `classify_ip()` 和 IP_PATTERNS。TikTok 视频的 IP 从 `source` 字段映射（同 `generate_article.py` 的 `TIKTOK_SOURCE_IP`）。品牌判断：`author == 'popmartglobal'`。

### 月度聚合

所有时序图表使用月度粒度（非周度），避免采集策略导致的分布偏差。月份从 TikTok `create_time`（Unix时间戳转日期）和 Instagram `post_date` 提取。

---

## 2. 前端图表组件

### 替换策略

删除现有 `TrendChart.astro`（周评论趋势），替换为 5 个新组件。

### 组件列表

所有组件遵循统一模式：
- frontmatter 中读取 JSON、计算 ECharts option
- `<script define:vars>` 注入数据
- CDN 动态 import ECharts 5
- `window.addEventListener('resize', () => chart.resize())` 响应式
- IP 颜色统一使用 `IP_COLORS` 常量

#### 2.1 BrandTrendChart.astro — 品牌热度走势

- 类型：柱+折线混合，双Y轴
- 左Y轴：月度评论量（渐变橙色柱状图）
- 右Y轴：贴均评论密度（红色折线+圆点标记）
- X轴：月份标签，智能间隔显示（总数>10时隔季）
- Tooltip：显示评论量 + 密度

#### 2.2 IpShareTrendChart.astro — IP评论份额

- 类型：堆叠面积图
- 5个IP各一个系列，使用 IP_COLORS
- Y轴：0-100%
- Tooltip：显示各IP占比%和绝对数量
- 图例带IP头像（同现有 TrendChart 风格）

#### 2.3 CrossPlatformChart.astro — 双平台热度指数

- 类型：折线图
- 两条线：TikTok（黑色）、Instagram（#E1306C）
- 基准线：y=100 虚线，标注"均值=100"
- 3月滚动平均已在数据导出时计算
- Tooltip：显示指数值和原始密度

#### 2.4 BrandVsUgcChart.astro — 品牌 vs UGC

- 类型：分组柱状图
- 4 个维度：平均播放量、平均点赞、平均参与率、每视频均评论
- 归一化到 UGC=100，品牌显示相对值
- 数据标签显示原始数值
- 颜色：品牌红 #E53935，UGC 深灰 #333

#### 2.5 CommentQualityChart.astro — 评论质量分层

- 类型：堆叠柱状图（水平或垂直）
- 两个柱：TikTok、Instagram
- 三层：高互动 ≥10赞（绿）、中互动 3-9赞（黄）、低互动 <3赞（灰）
- 数据标签显示百分比

### 首页布局顺序

```
Hero
StatCards
BrandTrendChart      — 品牌热度走势
IpShareTrendChart    — IP评论份额
CrossPlatformChart   — 双平台热度指数
BrandVsUgcChart      — 品牌 vs UGC
CommentQualityChart  — 评论质量分层
IpShareCards         — IP声量份额卡片（已有）
LatestPosts          — 最新热门（已有）
Footer
```

---

## 3. 移动端适配

### 断点

- `≤ 768px`：手机竖屏
- `769px - 1024px`：平板（可选，低优先）

### 全局 CSS 改动（global.css）

```css
@media (max-width: 768px) {
  .section { margin: 24px auto; padding: 0 16px; }
  .section-header h2 { font-size: 20px; }
}
```

### 各组件适配

| 组件 | 桌面 | 手机 (≤768px) |
|------|------|---------------|
| **Nav** | 水平链接栏 | Logo + 精简 3 链接（首页/TikTok/IG），缩小padding |
| **Hero** | 480px高，4个浮动角色 | 320px高，隐藏角色或只保留2个，标题缩小 |
| **StatCards** | 4列网格 | 2列网格 |
| **图表** | height: 400px | height: 260px |
| **IpShareCards** | 5列网格 | 横向滚动或2+3网格 |
| **LatestPosts** | 2列网格 | 单列 |
| **DataTable** | 全宽表格 | overflow-x: auto 横向滚动 |
| **Footer** | flex两端对齐 | 垂直堆叠 |

### 实现方式

纯 CSS `@media` 查询加在各组件的 `<style>` 块内。图表高度通过 CSS 控制容器高度，ECharts 的 `resize()` 已绑定 window resize 事件会自动适配。

---

## 4. 更新机制

### 现状

`scripts/daily_update.bat` 运行 `export_json.py` + `git push`。无采集能力。

### 改为

`scripts/daily_update.bat` 改为启动 Claude Code CLI，让 Claude Code 执行完整流水线：

```batch
@echo off
REM 启动 Claude Code 执行每日更新
cd /d "C:\Users\lxxxxxx\Desktop\个人项目\popmart"
claude --dangerously-skip-permissions -p "执行每日海外数据更新：1) 运行 tiktok_browser.py 采集新视频和评论 2) 运行 instagram_browser.py 检查新帖子 3) 运行 export_json.py 导出网站数据 4) git add + commit + push 触发部署。每步完成后报告结果。"
```

### Windows 任务计划程序

保持现有的每日定时触发（如每天 9:00），但执行的是 Claude Code 而非哑脚本。

### 备选方案

如果不想全自动，改为 **通知提醒**：

```batch
@echo off
powershell -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('该更新 Pop Mart 海外数据了！请启动 Claude Code 运行每日更新。', '泡泡玛特.md 数据更新', 'OK', 'Information')"
```

用户决定用哪种方式时再最终确定。

---

## 不在范围内

- 新增数据采集源（Amazon、SimilarWeb PRO）
- 图表数据回测/历史修正
- 用户认证/登录
- 服务端渲染（保持纯静态 SSG）

## 技术栈

- Astro 5 SSG（已有）
- ECharts 5 CDN（已有）
- CSS @media queries（新增）
- Claude Code CLI（更新机制）
- export_json.py 扩展（Python）
