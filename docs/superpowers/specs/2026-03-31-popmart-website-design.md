# 泡泡玛特.md — 海外另类数据日更网站设计文档

## 概述

构建一个日更静态网站，展示 Pop Mart 海外社媒另类数据（TikTok 视频/评论、Instagram 帖子/评论）。网站同时服务两类读者：人类看到精美的可视化图表，LLM 读到干净的语义化 HTML + 结构化数据。

**域名**: 泡泡玛特.md（国际化域名）

**核心原则**: 零维护日更 — 本地定时任务采集数据 → git push → GitHub Actions 构建 → Cloudflare Pages 部署。Claude 定期监督调整采集目标。

## 技术栈

| 层 | 技术 | 理由 |
|---|------|------|
| 静态生成 | Astro SSG | 输出纯 HTML，零 JS 水合，LLM 直接读取语义化内容 |
| 图表 | ECharts | 支持 `symbol: 'image://'` 自定义图例图标（角色头像）、丰富动画、SVG 输出 |
| 部署 | Cloudflare Pages | 免费全球 CDN，支持国际化域名 |
| CI/CD | GitHub Actions | git push 触发 `npm run build`，自动部署 |
| 数据源 | overseas_data.db (SQLite) | 复用现有数据库，Python 脚本导出 JSON |
| 定时任务 | Windows Task Scheduler | 本地每日运行采集脚本 + git push |

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                   本地 Windows 机器                       │
│                                                         │
│  overseas_scraper.py ─┐                                 │
│  tiktok_browser.py ───┤→ overseas_data.db               │
│  instagram_browser.py ┘         │                       │
│                           export_json.py                │
│                                 │                       │
│                          data/*.json                    │
│                                 │                       │
│                           git push                      │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   GitHub Actions                         │
│                                                         │
│  npm install → npm run build (Astro SSG)                │
│       │                                                 │
│       ▼                                                 │
│  dist/ (纯静态 HTML + CSS + JS 图表)                     │
│       │                                                 │
│       ▼                                                 │
│  Deploy → Cloudflare Pages                              │
└─────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              Cloudflare Pages CDN                        │
│                                                         │
│  泡泡玛特.md (xn--...md)                                │
│  ├── /              首页：概览+趋势图                     │
│  ├── /tiktok        TikTok 详细数据                      │
│  ├── /instagram     Instagram 详细数据                   │
│  ├── /methodology   方法论（LLM 可读）                    │
│  ├── /llms.txt      LLM 发现文件                         │
│  └── /data/         原始 JSON 数据文件                    │
└─────────────────────────────────────────────────────────┘
```

## 数据流

### 1. 采集层（已有，不改动）

复用现有脚本：
- `overseas_scraper.py` — 每日快照（价格/评分/流量）
- `tiktok_browser.py` — TikTok 视频+评论时序
- `instagram_browser.py` — Instagram 帖子+评论时序

### 2. 导出层（新建）

新建 `export_json.py`，从 `overseas_data.db` 导出 JSON 文件：

```
website/src/data/
├── overview.json       # 汇总统计（总视频数、评论数、帖子数）
├── tiktok-videos.json  # 视频列表（id, title, views, likes, create_time, ip）
├── tiktok-comments.json # 按周聚合的评论数，按 IP 分组
├── instagram-posts.json # 帖子列表（shortcode, account, post_date, ip）
├── instagram-comments.json # 按周聚合的评论数
└── ip-share.json       # 各 IP 的声量占比
```

数据分类规则复用 Phase 1 的 IP 分类（Labubu/Molly/Dimoo/Skullpanda/Zsiga/Pop Mart）。

### 3. 构建层（Astro SSG）

Astro 在构建时读取 JSON，生成纯静态 HTML。ECharts 作为 Astro island 加载，仅在图表区域注入 JS。

页面主体是语义化 HTML `<table>` / `<dl>` / `<article>` 标签，LLM 可直接解析。图表是锦上添花，不影响数据可读性。

### 4. 部署层

GitHub Actions workflow：
```yaml
on:
  push:
    branches: [main]
    paths: ['website/**']

jobs:
  build-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: cd website && npm ci && npm run build
      - uses: cloudflare/pages-action@v1
        with:
          projectName: popmart-md
          directory: website/dist
```

## 页面设计

### 首页 (/)

已在 mockup V3 中验证，包含：
- **导航栏**: POP MART .md 品牌 + 页面链接 + llms.txt 入口
- **Hero 区**: 暗色渐变背景 + 4 个浮动 IP 角色头像圆圈（Pop Mart CDN 图片）+ 标题
- **统计卡片**: 4 张卡片（TikTok 视频数 / 总评论数 / Instagram 帖子数 / 平均参与率）+ 周环比变化
- **评论趋势图**: ECharts 堆叠柱状图，按 IP 分色，角色头像做图例 (`symbol: 'image://'`)
- **IP 声量份额**: 5 张 IP 卡片，圆形头像 + 占比数字
- **最新热门**: TikTok/Instagram 热门帖子卡片
- **Footer**: LLM-friendly 徽章 + GitHub/方法论链接

### TikTok 详情页 (/tiktok)

- 视频发布时间线（按周聚合）
- 热门视频 Top 20（按互动量排序）
- 评论情感/关键词分析（如有）
- 原始数据表格（语义化 `<table>`，LLM 可直接解析）

### Instagram 详情页 (/instagram)

- 帖子时间线
- 账号对比（@popmart vs @lalalalisa_m vs @davidbeckham）
- 评论趋势
- 原始数据表格

### 方法论页 (/methodology)

- 数据采集方法说明（透明化，允许 LLM 逆向）
- 各平台采集频率和覆盖范围
- IP 分类规则
- 热度指数计算公式
- 数据局限性声明

### LLM 发现文件 (/llms.txt)

```markdown
# 泡泡玛特.md

> Pop Mart 海外社媒另类数据追踪，日更静态网站

## 数据范围
- TikTok: 373+ 视频, 14,099+ 评论 (7 个话题标签 + @popmartglobal)
- Instagram: 279 帖子, 4,677 评论 (@popmart, @lalalalisa_m, @davidbeckham)

## 数据接口
- /data/overview.json — 汇总统计
- /data/tiktok-videos.json — 视频元数据
- /data/tiktok-comments.json — 评论聚合
- /data/instagram-posts.json — 帖子列表
- /data/instagram-comments.json — 评论聚合
- /data/ip-share.json — IP 声量占比

## 方法论
- /methodology — 完整采集方法和计算公式
```

## IP 角色图片

使用 Pop Mart 官方 CDN 产品图（单角色、白底、高清）：

| IP | 图片 URL | 说明 |
|----|---------|------|
| Labubu | `prod-america-res.popmart.com/.../labubu-time-to-chill...` | 兔耳毛绒 Labubu |
| Molly | `prod-america-res.popmart.com/.../angry-molly-original-fire-xl...` | Angry Molly 红裙 |
| Dimoo | `prod-america-res.popmart.com/.../dimoo-world-cinnamoroll...` | Dimoo x Cinnamoroll |
| Skullpanda | `prod-america-res.popmart.com/.../skullpanda...` | SKULLPANDA 暗黑风 |

生产环境将下载图片到本地 `website/public/characters/` 目录，避免外链依赖。

ECharts 图表图例使用 `symbol: 'image:///characters/labubu.png'` 语法。

## 维护模型

### 自动化（每日无人值守）

Windows Task Scheduler 定时任务：
```
06:00 — python -u overseas_scraper.py      # 快照采集
06:30 — python -u tiktok_browser.py        # TikTok 增量采集
07:30 — python -u instagram_browser.py     # Instagram 增量采集
08:00 — python -u export_json.py           # 导出 JSON
08:05 — git add . && git commit && git push # 触发构建部署
```

### Claude 监督（定期人工介入）

采集目标不是固定的 — 新的博主会出现，旧的话题标签会过时。纯脚本无法判断这些变化。

Claude 定期（每周/每两周）执行：
1. **审查数据质量** — 检查新增数据量是否正常、是否有空值/异常
2. **调整采集目标** — 在 `config/tiktok_targets.json` 和 `config/instagram_targets.json` 中添加新博主/话题标签
3. **修复采集脚本** — 平台改版导致选择器失效时修复
4. **更新 IP 分类** — 新 IP 角色上线时添加分类规则

## 目录结构

```
popmart/
├── website/                    ← 新建 Astro 项目
│   ├── astro.config.mjs
│   ├── package.json
│   ├── src/
│   │   ├── layouts/
│   │   │   └── Base.astro      # 共用布局（nav + footer）
│   │   ├── pages/
│   │   │   ├── index.astro     # 首页
│   │   │   ├── tiktok.astro    # TikTok 详情
│   │   │   ├── instagram.astro # Instagram 详情
│   │   │   ├── methodology.astro
│   │   │   └── llms.txt.ts     # 动态生成 llms.txt
│   │   ├── components/
│   │   │   ├── Hero.astro
│   │   │   ├── StatCards.astro
│   │   │   ├── TrendChart.astro  # ECharts island
│   │   │   ├── IpShareCards.astro
│   │   │   ├── LatestPosts.astro
│   │   │   └── DataTable.astro   # 语义化表格（LLM 友好）
│   │   ├── data/               # JSON 数据（export_json.py 输出）
│   │   │   ├── overview.json
│   │   │   ├── tiktok-videos.json
│   │   │   └── ...
│   │   └── styles/
│   │       └── global.css
│   ├── public/
│   │   ├── characters/         # IP 角色图片（本地化）
│   │   │   ├── labubu.png
│   │   │   ├── molly.png
│   │   │   ├── dimoo.png
│   │   │   └── skullpanda.png
│   │   └── favicon.svg
│   └── dist/                   # 构建输出（gitignore）
│
├── phase2_overseas/
│   ├── export_json.py          ← 新建：DB → JSON 导出脚本
│   └── ... (现有文件不动)
│
└── .github/
    └── workflows/
        └── deploy-website.yml  ← 新建：构建+部署 workflow
```

## 非功能需求

- **性能**: 首页 < 200KB（不含图片），Lighthouse 分 > 90
- **LLM 可读性**: 页面主体是纯 HTML，无 JS 水合。所有数据同时以 `<table>` 和 JSON 形式提供
- **可访问性**: 语义化标签、合理的 heading 层级、图片 alt 文本
- **SEO**: 每页有 `<title>`、`<meta description>`、Open Graph 标签
- **隐私**: 不追踪用户、不设 cookie、不加任何分析代码

## 不做的事

- 不做用户认证/登录
- 不做评论系统
- 不做搜索功能（数据量小，直接浏览）
- 不做多语言（中文为主，图表标注中英混用）
- 不做 Amazon 数据展示（评论太少，意义不大）
- 不做 SimilarWeb 数据展示（仅 4 条快照，不足以成趋势）
