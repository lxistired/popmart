# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Pop Mart 数据分析项目

## 项目总览

泡泡玛特(9992.HK)数据分析项目，分两个阶段：
- **Phase 1** — 小红书舆情分析（已交付，不需要改动）
- **Phase 2** — 海外另类数据追踪（活跃开发中）

## 目录结构

```
popmart/
├── CLAUDE.md                    ← 本文件
├── HANDOVER.md                  ← 踩坑记录和操作清单
├── phase1_xiaohongshu/          ← Phase 1（已交付，不动）
│   ├── scrape_comments.py       小红书评论爬虫(UC Driver)
│   ├── ip_analysis_main.py      主分析脚本(Excel+图表)
│   ├── ip_analysis_clean.py     数据清洗
│   ├── ip_analysis_charts.py    可视化(8张PNG)
│   ├── popmart_comments.db      小红书数据库(240帖/13000+评论)
│   └── ...
│
├── phase2_overseas/             ← Phase 2（活跃开发中）
│   ├── shared/                  共享基础设施
│   │   ├── db.py                数据库连接+批量写入+去重索引
│   │   ├── log.py               文件+控制台日志
│   │   ├── rate.py              带抖动的延迟+重试
│   │   └── checkpoint.py        JSON检查点（断点续传）
│   ├── config/                  采集目标配置
│   │   ├── amazon_targets.json  12个ASIN+IP分类
│   │   ├── tiktok_targets.json  7个搜索词+账号
│   │   └── instagram_targets.json  3个账号
│   │
│   │  ── 时序采集脚本（DrissionPage，当前主力）──
│   ├── amazon_reviews_browser.py   Amazon评论日期（137条，受Amazon全局限制）
│   ├── tiktok_browser.py           TikTok视频元数据（158+条，进行中）
│   ├── instagram_browser.py        Instagram帖子+评论（279帖/4677评论，已完成）
│   │
│   │  ── 快照采集（UC Driver，每日跑一次）──
│   ├── overseas_scraper.py         4维度快照采集
│   │
│   │  ── 分析/文章生成 ──
│   ├── generate_article.py         公众号文章生成（8张图表+HTML）
│   ├── overseas_article.html       完整版文章（CSS渲染）
│   ├── overseas_article_wechat.html 公众号兼容版（静态图替换复杂CSS）
│   ├── overseas_analysis.py        海外热度分析报告（Excel+图表）
│   ├── article_charts/             文章图表PNG（8+2张）
│   │
│   │  ── 辅助/遗留 ──
│   ├── ts_pw.py                    旧版Playwright采集（已被上述3个脚本取代）
│   ├── login_helper.py             登录辅助（仅Amazon用）
│   ├── setup_instagram_session.py  Instagram instagrapi会话初始化
│   ├── db_migrate.py               数据库迁移工具
│   │
│   ├── overseas_data.db            海外数据库（9张表）
│   ├── chrome_data/                Amazon专用Chrome Profile
│   └── amazon_cookies.json         Amazon cookie备份
│
└── .planning/                   GSD项目管理
```

---

## Phase 1 — 小红书舆情分析（已交付）

### 数据架构

```
chart_data.json (1001帖宏观数据)
    ↓
ip_analysis_main.py → Excel报告 + 8张图表
    ↑
popmart_comments.db (240帖/13000+评论，深挖数据)
    ↑
scrape_comments.py (UC爬虫)
    ↑
dig_queue.txt (待挖帖子队列)
```

### SQLite：popmart_comments.db

```sql
posts(id, title, ip, likes TEXT, collects, comments_total, post_date, url, note_id)
-- UNIQUE(title), likes存为文本, post_date仅10%有值

comments(id, post_id, commenter, comment_date, comment_likes, comment_text, location)
-- UNIQUE(post_id, commenter, comment_date, comment_likes)
-- comment_date三种格式，经 ip_analysis_clean.py 统一为 YYYY-MM-DD
```

### IP分类规则

Labubu/拉布布 → Labubu | dimoo → Dimoo | 星星人 | molly → Molly | skullpanda/sp → Skullpanda | zsiga/嘎子 → Zsiga | 小甜豆 | 默认 → 泡泡玛特

### 热度指数公式

```
v1 = avg_likes × ln(post_count+1) × (1 + max_likes/(avg_likes+1) × 0.1)
v2 = v1 × (1 + min(comment_ratio, 50) × 0.01)
```

### 硬编码需维护

- `ip_analysis_clean.py:16` → `SCRAPE_DATE = datetime(2026, 3, 25)` 相对时间锚点
- `ip_analysis_clean.py:13` → `BASE_DIR` 项目绝对路径

---

## Phase 2 — 海外另类数据追踪（开发中）

### 投研逻辑

Pop Mart 海外扩张是核心增长叙事。通过 4 个维度的另类数据构建"海外热度"指标：

| 维度 | 数据源 | 意义 | 采集状态 |
|------|--------|------|----------|
| Amazon 产品 | 评论数/评分/价格/月销 | 线上渠道动销 | 137条评论（受限） |
| SimilarWeb | popmart.com 月访问量 | DTC官网流量 | 4条快照 |
| TikTok | 视频发布时间/播放量 | 社媒声量/传播力 | 158+视频（进行中） |
| Instagram | 帖子+评论时间戳 | 名人效应/品牌力 | 279帖/4677评论（完成） |

### 采集架构（已从 Playwright 迁移到 DrissionPage）

**旧方案**：`ts_pw.py`（Playwright）→ Amazon/TikTok 被检测封杀，已废弃
**新方案**：每个平台独立的 DrissionPage 脚本，不使用 WebDriver 协议

#### 1. instagram_browser.py — Instagram 时序（已完成）
- 使用 `instagrapi`（私有移动 API）获取帖子列表
- 使用 DrissionPage 打开帖子页面提取评论
- 数据：279 帖子 + 4677 条评论，含时间戳

#### 2. amazon_reviews_browser.py — Amazon 评论时序（部分完成）
- DrissionPage + 独立 `chrome_data/` Profile（不碰用户 Chrome）
- 双层 cookie 持久化：Chrome Profile（主）+ JSON 备份（fallback）
- **已知限制**：Amazon 对所有用户限制评论展示数量（"limited selection of reviews"），每个 ASIN 仅 8-13 条可见。这不是反爬问题，是 Amazon 产品策略。
- 支持 `--real-profile` 使用用户真实 Chrome Profile

#### 3. tiktok_browser.py — TikTok 视频+评论时序（进行中）
- DrissionPage 访问 `/tag/{hashtag}` 提取视频 ID 列表
- 逐个访问视频页，从 `__UNIVERSAL_DATA_FOR_REHYDRATION__` JSON 提取 createTime/views/likes
- **评论采集需要登录态**：通过 `page.listen` 拦截 `/api/comment/list/` API 获取精确时间戳
- Cookie持久化：JSON备份 + CDP注入恢复（`tiktok_cookies.json`），首次需手动登录一次
- `--backfill` 模式：跳过hashtag采集，直接为已有视频补采评论
- 毒品内容过滤（`#molly` 搜索可能命中 MDMA）、浏览器断连自动重建

#### 4. overseas_scraper.py — 每日快照（UC Driver）
- 12 ASIN 价格/评分/月购买量 + SimilarWeb + TikTok hashtag + Instagram 账号
```bash
cd phase2_overseas && python -u overseas_scraper.py
```

### 运行命令

```bash
cd phase2_overseas

# Instagram（已完成，通常不需要重跑）
python -u instagram_browser.py

# Amazon（首次需登录，之后自动）
python -u amazon_reviews_browser.py          # 用独立Profile
python -u amazon_reviews_browser.py --real-profile  # 用真实Chrome（需先关Chrome）

# TikTok（首次需登录，之后cookie自动恢复）
python -u tiktok_browser.py                  # 全部7个关键词
python -u tiktok_browser.py labubu dimoo     # 指定关键词
python -u tiktok_browser.py --backfill       # 只补采评论，跳过hashtag

# 每日快照
python -u overseas_scraper.py

# 文章生成（同时输出完整版和公众号版）
python -u generate_article.py
# → overseas_article.html（完整CSS渲染版）
# → overseas_article_wechat.html（公众号兼容版，hero/footer用静态PNG）
# → article_charts/（8张分析图 + 2张公众号专用PNG）
```

### SQLite：overseas_data.db

#### 快照表（overseas_scraper.py 写入）

```sql
amazon_snapshots(id, scraped_at, asin, ip, title, price_usd REAL,
    rating REAL, reviews INTEGER, bsr_main INTEGER, bsr_category,
    bsr_rank INTEGER, bought_monthly, in_stock INTEGER)
-- 每日每ASIN一行

similarweb_traffic(id, scraped_at, domain, monthly_visits,
    visit_duration, pages_per_visit, bounce_rate,
    top_countries, traffic_sources, raw_json)

tiktok_data(id, scraped_at, data_type, keyword,
    hashtag_views, hashtag_posts, video_id, video_title,
    video_views, video_likes, video_comments, video_shares,
    video_author, video_date, account_followers, account_likes, raw_json)
-- data_type: 'hashtag' / 'search_video' / 'account'

instagram_data(id, scraped_at, data_type, keyword,
    hashtag_posts, account_username, account_followers,
    account_posts INTEGER, post_url, post_likes, post_comments,
    post_caption, celebrity_name, raw_json)
-- data_type: 'hashtag' / 'account' / 'celebrity_post'
```

#### 时序表（各平台独立脚本写入）

```sql
amazon_review_dates(id, asin, ip, review_date, review_date_raw,
    review_title, rating, verified, scraped_at)
-- 每条评论一行，review_date = YYYY-MM-DD

tiktok_videos(id, video_id UNIQUE, author, title, views, likes,
    comments_count, create_time, source, scraped_at)

tiktok_comments(id, video_id, comment_id UNIQUE, comment_text,
    comment_date, comment_datetime, likes, author_name, scraped_at)

instagram_posts(id, shortcode UNIQUE, post_url, account, caption,
    post_date, source, scraped_at)

instagram_comments(id, shortcode, comment_id, comment_text,
    comment_date, comment_datetime, likes, author_name, scraped_at)
```

### 数据状态（2026-03-31）

| 表 | 行数 | 来源 | 说明 |
|----|------|------|------|
| amazon_snapshots | 22 | overseas_scraper.py | 每日快照 |
| similarweb_traffic | 4 | overseas_scraper.py + SimilarWeb PRO | 3条月度数据(Dec-Feb) + 1条汇总 |
| tiktok_data | 16 | overseas_scraper.py | hashtag/账号元数据 |
| instagram_data | 12 | overseas_scraper.py | 账号快照 |
| amazon_review_dates | 137 | amazon_reviews_browser.py | 受Amazon限制 |
| tiktok_videos | 373 | tiktok_browser.py | 7/7关键词+@popmartglobal ✅ |
| tiktok_comments | 14,099 | tiktok_browser.py | 340/373视频有评论 ✅ |
| instagram_posts | 279 | instagram_browser.py | ✅ 完成 |
| instagram_comments | 4677 | instagram_browser.py | ✅ 完成 |

查看实时行数：
```bash
cd phase2_overseas
python -c "import sqlite3; c=sqlite3.connect('overseas_data.db'); [print(f'{t}: {c.execute(f\"SELECT COUNT(*) FROM {t}\").fetchone()[0]}') for t in ['amazon_snapshots','similarweb_traffic','tiktok_data','instagram_data','amazon_review_dates','tiktok_videos','tiktok_comments','instagram_posts','instagram_comments']]"
```

### 监控标的

- **Amazon**: 12 ASIN（`config/amazon_targets.json`）
- **TikTok**: 7 话题标签 + @popmartglobal（`config/tiktok_targets.json`）
  - ⚠️ #molly 被毒品"Molly"污染，`tiktok_browser.py` 已内置 `DRUG_KEYWORDS` 过滤
- **Instagram**: @popmart、@lalalalisa_m、@davidbeckham（`config/instagram_targets.json`）
  - ⚠️ **@popmart_global 是假的**，会404。真实官号是 @popmart

### 已知限制

1. **Amazon 评论数量** — Amazon 对所有用户（包括真人浏览器）限制评论展示（"limited selection of reviews"），`medleyReviewsAjaxUrl` 被设为空字符串。每个 ASIN 仅能获取 8-13 条评论。详见 `.planning/debug/amazon-review-pagination-duplicates.md`
2. **TikTok 评论** — 评论 API 需要登录态，通过 `page.listen` 拦截 `/api/comment/list/` 获取。Cookie 通过 JSON + CDP注入持久化（`tiktok_cookies.json`）。首次需手动登录一次，之后自动恢复
3. **TikTok 速率限制** — DrissionPage 连续访问过多视频页会断连。脚本每 10 个视频自动休息 15-25 秒，关键词间隔 40-70 秒

### 注意事项

1. **Chrome profile 锁** — `chrome_data/Default/LOCK` 文件残留会导致启动失败，脚本已自动处理
2. **Python 输出缓冲** — 始终用 `python -u`
3. **中文路径** — 脚本内用 `os.path.dirname(os.path.abspath(__file__))`，不硬编码
4. **代理** — v2rayN，`socks5://127.0.0.1:10808`，所有 DrissionPage 脚本已配置
5. **不要 kill Chrome 进程** — 会丢失 session cookie。用 `page.quit()` 正常退出

### 待完成工作

- [x] Instagram 时序采集（279帖/4677评论）
- [~] Amazon 评论时序（137条，受平台限制暂停深入）
- [x] TikTok 视频+评论时序（373视频/14,099评论）
- [x] 文章生成 generate_article.py — 8张图表 + 公众号文章（完整版+WeChat兼容版）
- [ ] 编写 overseas_analysis.py — 生成海外热度分析报告（图表+Excel）
- [ ] 设置定时任务 — overseas_scraper.py 每日自动快照
- [ ] （可选）SimilarWeb PRO 数据获取

---

## 环境依赖

```
Python 3.13
DrissionPage         # 主力浏览器自动化（amazon_reviews_browser/tiktok_browser/instagram_browser）
instagrapi           # Instagram 私有API（instagram_ts.py/instagram_browser.py 帖子列表获取）
undetected-chromedriver  # overseas_scraper.py 快照采集
playwright           # ts_pw.py, login_helper.py（遗留，仅这两个文件使用）
playwright-stealth   # 反自动化检测（仅遗留脚本使用）
pandas / matplotlib / openpyxl  # 分析和文章生成
pytest               # 单元测试（phase2_overseas/tests/）
sqlite3              # 内置
```

安装：
```bash
pip install DrissionPage instagrapi undetected-chromedriver playwright playwright-stealth pandas matplotlib openpyxl pytest
playwright install chromium
```

## 运行测试

```bash
cd phase2_overseas && python -m pytest tests/ -v
```
测试使用内存 SQLite（`:memory:`），不触碰 overseas_data.db。

## 运行顺序（新环境）

```bash
cd phase2_overseas

# 1. 快照采集（无需登录，UC Driver）
python -u overseas_scraper.py

# 2. Instagram 时序（instagrapi + DrissionPage，首次需 setup_instagram_session.py）
python -u instagram_browser.py

# 3. Amazon 时序（DrissionPage，首次需登录，之后cookie自动恢复）
python -u amazon_reviews_browser.py

# 4. TikTok 时序（DrissionPage，首次需登录，之后cookie自动恢复）
python -u tiktok_browser.py

# 5. 分析报告
python -u overseas_analysis.py    # → Excel + charts/
python -u generate_article.py     # → HTML + article_charts/
```

## shared/ — 共享基础设施（Phase 2 新脚本使用）

| 模块 | 功能 |
|------|------|
| `shared/db.py` | `get_conn()` WAL模式连接, `init_db()` 建表+唯一索引, `batch_insert()` 批量INSERT OR IGNORE |
| `shared/log.py` | `get_logger(platform)` 带时间戳日志文件 + 控制台双输出 |
| `shared/rate.py` | `sleep_jitter(base, jitter)` 随机延迟, `retry_with_backoff` 指数退避装饰器 |
| `shared/checkpoint.py` | `load_checkpoint(platform)` / `save_checkpoint(platform, state)` JSON断点续传 |

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Pop Mart 海外另类数据追踪**

泡泡玛特(9992.HK)海外另类数据分析项目。通过采集 Amazon 评论时序、TikTok 视频评论、Instagram 帖子评论，构建"海外热度"时间序列指标，为投研提供领先于财报的动销/声量信号。

**Core Value:** **能稳定采集三个平台的历史评论并带时间戳**——有了评论时序数据，后续的分析报告、热度指标、定时任务都是顺理成章的事。

### Constraints

- **环境**: Windows 11, Python 3.13, Chrome 146, v2rayN 代理 (socks5://127.0.0.1:10808)
- **反检测**: 不能用 Playwright/CDP 协议访问 Amazon/TikTok（已证实被检测），主力方案是 DrissionPage
- **Chrome 冲突**: 任何需要控制 Chrome 的工具必须处理 profile 锁问题
- **成本**: 优先免费方案（DrissionPage/instagrapi），付费仅作 fallback
- **数据库**: 复用现有 overseas_data.db，表结构可扩展但不破坏已有数据
- **输出格式**: 中文为主，图表标注可中英混用
<!-- GSD:project-end -->

## Conventions (key patterns)

- **命名**: snake_case 文件名和函数名；UPPER_SNAKE 模块常量；DataFrame 加 `_df` 后缀；pivot 加 `_pivot` 后缀
- **无类型注解**: 全代码库不使用 type annotations
- **DB 访问**: `INSERT OR IGNORE` 去重；Phase 2 新脚本用 `shared/db.py` 的 `batch_insert()`；分析层用 `pd.read_sql_query()`
- **Schema**: `CREATE TABLE IF NOT EXISTS` 内联在 Python 代码中，无独立 SQL 文件
- **错误处理**: 采集脚本单条目失败继续循环；`KeyboardInterrupt` 打印已保存提示
- **日志**: emoji 前缀（✅❌⚠️）+ 进度 `[idx/total]`；始终 `python -u` 无缓冲运行
- **反检测延迟**: `sleep_jitter()` 随机间隔；TikTok 每 10 视频休息 15-25s，关键词间 40-70s

## Architecture

```
采集层 (DrissionPage/UC Driver/instagrapi)
  ↓ INSERT OR IGNORE
数据层 (SQLite: popmart_comments.db / overseas_data.db)
  ↓ pd.read_sql_query()
分析层 (overseas_analysis.py / generate_article.py)
  ↓
输出层 (Excel + PNG charts + HTML articles)
```

- 每个平台独立脚本，无编排层，CLI 手动调用
- Phase 2 新脚本使用 `shared/` 共享模块（db/log/rate/checkpoint）
- 采集脚本通过 UNIQUE 约束 + `INSERT OR IGNORE` 保证幂等性
- 断点续传：`shared/checkpoint.py` JSON 文件 或 DB 内日期查重

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
