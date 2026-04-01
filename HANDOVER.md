# Pop Mart 海外另类数据项目交接文档

**最后更新：2026-03-27**
**状态：Phase 2 进行中，时序采集尚未成功**

---

## 一、项目背景与目标

### 为什么做这个

Pop Mart（9992.HK）的核心投资叙事是海外扩张。官方数据（财报）每半年出一次，滞后严重。海外另类数据可以做到：

- **月度/周度追踪**海外实际热度变化
- **提前感知**销量拐点（亚马逊评论速率代理销量）
- **验证**明星/名人效应（Lisa/Beckham带货 → 评论时间戳可以精确定位）
- **与价格联动**：热度指标先行，股价跟随

### 数据维度设计

| 维度 | 数据源 | 用途 |
|---|---|---|
| Amazon 产品 | 评论数量/评分/价格/月销量 | 线上动销的直接代理 |
| SimilarWeb | popmart.com 月访问量/跳出率 | DTC官网流量，感知品牌力 |
| TikTok 社媒 | 话题播放量/粉丝数/评论时间戳 | 社媒声量，名人带货效应 |
| Instagram 名人 | Lisa/Beckham/popmart官号互动 | 名人效应量化 |

### 时间序列方法论

不需要每天重复抓截面数据——借鉴小红书项目的方法：

> **一次抓取 = 历史全量时序**
>
> 每条评论/帖子都有发布时间戳，把所有历史评论一次性抓下来，
> 按周聚合就得到了"评论速率"时间序列。
> Amazon评论速率 ≈ 销量代理曲线。

---

## 二、项目文件结构

```
C:\Users\lxxxxxx\Desktop\个人项目\popmart\
├── CLAUDE.md                     项目说明（给Claude看）
├── HANDOVER.md                   本文件（详细交接）
│
├── phase1_xiaohongshu/           Phase 1 小红书（已完成交付）
│   ├── scrape_comments.py        UC Driver 爬虫
│   ├── ip_analysis_main.py       主分析（Excel+图表）
│   ├── ip_analysis_clean.py      数据清洗
│   ├── ip_analysis_charts.py     可视化(8张PNG)
│   ├── article_charts.py         公众号文章配图
│   ├── popmart_comments.db       数据库(240帖/13000+评论)
│   ├── chart_data.json           1001帖宏观数据
│   ├── scrape_checkpoint.json    断点续传状态
│   ├── charts/                   8张分析图表
│   ├── article_images/           公众号文章配图
│   └── 项目交付.rar              已归档交付包
│
└── phase2_overseas/              Phase 2 海外数据（进行中）
    ├── overseas_scraper.py       每日快照采集（UC Driver）
    ├── ts_pw.py                  时序采集（Playwright + ChromePW）
    ├── login_helper.py           首次登录辅助
    ├── overseas_data.db          海外数据库
    ├── amazon_sku_list.json      12个监控ASIN
    ├── overseas_snapshot_20260326.json  手动截面快照
    ├── overseas_scraper_log.txt  快照日志
    ├── amazon_timeseries_log.txt Amazon时序日志
    ├── tiktok_timeseries_log.txt TikTok时序日志
    └── instagram_timeseries_log.txt Instagram时序日志
```

---

## 三、海外数据库结构（overseas_data.db）

### 快照表（overseas_scraper.py 写入，每日一次）

```sql
amazon_snapshots(
    id, scraped_at,
    asin, ip,               -- IP分类: Labubu/Skullpanda/Molly/Dimoo
    title, price_usd, rating,
    review_count,           -- 总评论数（整数）
    review_count_raw,       -- 原始文本如 "2,139"
    monthly_bought,         -- 月购量（整数）
    monthly_bought_raw,     -- 原始文本如 "20K+ bought in past month"
    answered_questions, availability, seller, badge
)

similarweb_traffic(
    id, scraped_at,
    domain,                 -- "popmart.com"
    total_visits,           -- 月访问量（整数）
    bounce_rate, avg_visit_duration,
    pages_per_visit, global_rank, country_rank
)

tiktok_data(
    id, scraped_at,
    metric_type,            -- 'hashtag' 或 'account'
    metric_name,            -- "#labubu" 或 "@popmartglobal"
    value,                  -- 数值（整数）
    value_raw               -- 原始文本 "3.6M"
)

instagram_data(
    id, scraped_at,
    username,               -- "popmart"
    followers, following, posts_count,
    bio, is_verified
)
```

### 时序表（ts_pw.py 写入，一次性拉历史全量）

```sql
amazon_review_dates(
    id, asin, ip,
    review_date,            -- YYYY-MM-DD（从 "Reviewed on January 5, 2025" 解析）
    review_date_raw,        -- 原始文本
    review_title, rating,
    verified,               -- 1=认证购买
    scraped_at
)
-- 用法：SELECT review_date, COUNT(*) FROM amazon_review_dates
--       WHERE asin='B0DT44TSM2' GROUP BY review_date ORDER BY review_date

tiktok_videos(
    id, video_id UNIQUE,
    author, title,
    views, likes, comments_count,
    create_time,            -- ISO datetime
    source,                 -- 搜索词如 'search_Labubu Lisa'
    scraped_at
)

tiktok_comments(
    id, video_id,
    comment_id UNIQUE,
    comment_text,           -- 限300字
    comment_date,           -- YYYY-MM-DD
    comment_datetime,       -- ISO datetime（从Unix时间戳转换）
    likes, author_name, scraped_at
)

instagram_posts(
    id, shortcode UNIQUE,   -- URL中的帖子ID
    post_url, account,
    caption, post_date,
    source,                 -- 'account_lalalalisa_m'
    scraped_at
)

instagram_comments(
    id, shortcode,
    comment_id,
    comment_text,           -- 限300字
    comment_date,           -- YYYY-MM-DD
    comment_datetime,       -- ISO datetime
    likes, author_name, scraped_at
)
```

### 当前数据状态（2026-03-27）

| 表 | 行数 | 说明 |
|---|---|---|
| amazon_snapshots | 22 | ✅ 2天快照 (3/26~3/27) |
| similarweb_traffic | 4 | ✅ |
| tiktok_data | 16 | ✅ 7话题+账号数据 |
| instagram_data | 12 | ✅ |
| instagram_posts | 15 | ✅ 三账号帖子列表 |
| instagram_comments | 234 | ✅ 评论时间戳 |
| amazon_review_dates | **0** | ❌ 待采集 |
| tiktok_videos | **0** | ❌ 待采集 |
| tiktok_comments | **0** | ❌ 待采集 |

---

## 四、监控标的清单

### Amazon SKU（12个ASIN）

| IP | ASIN | 评论数 | 月销 | 价格 |
|---|---|---|---|---|
| Labubu | B0DT44TSM2 | 2100+ | **20K+** | $27.99 |
| Labubu | B0FJFV4PQN | 780+ | 3K+ | - |
| Labubu | B0DF4L27VH | 400+ | - | - |
| Skullpanda | B0BG8QHZV5 | 869 | 600+ | - |
| Skullpanda | B0D2D7MRRL | 345 | 300+ | - |
| Skullpanda | B0D2P3JDW8 | 200+ | - | - |
| Dimoo | B0DT95S945 | 129 | 100+ | - |
| Dimoo | B0D8HDBDL2 | 95 | - | - |
| Dimoo | B0DQKJ3C7T | 80 | - | - |
| Molly | B0D3T2QJ1W | 210 | 200+ | - |
| Molly | B0D8DRX8QL | 160 | - | - |
| Molly | B0DH7T7GQ1 | 120 | - | - |

> 注：`ts_pw.py` 目前只抓6个ASIN（Labubu×2, Skullpanda×2, Molly×1, Dimoo×1），
> 可以按需扩充 `AMAZON_TARGETS` 列表。

### TikTok监控

| 类型 | 目标 | 数值 |
|---|---|---|
| 话题 | #labubu | 3.6M播放 |
| 话题 | #popmart | 1.8M |
| 话题 | #molly | 726.7K ⚠️（被毒品"Molly"污染） |
| 话题 | #skullpanda | 237.4K |
| 话题 | #dimoo | 97.8K |
| 话题 | #themonsters | 66.4K |
| 话题 | #popmartlabubu | 22.9K |
| 账号 | @popmartglobal | 2.7M粉丝, 13.5M点赞 |

搜索关键词（ts_pw.py抓评论时序用）：
- "Labubu"
- "Labubu Lisa"
- "Pop Mart Labubu"
- "Labubu Beckham"

### Instagram监控

| 账号 | 粉丝 | 说明 |
|---|---|---|
| @popmart | 1.7M | Pop Mart官方（由TikTok bio `IG:@popmart` 确认） |
| @lalalalisa_m | Lisa官号 | 带货Labubu |
| @davidbeckham | Beckham官号 | 带货Labubu |

> ⚠️ **@popmart_global 是假的**，会404。真实官号是 @popmart。

---

## 五、脚本操作手册

### 5.1 每日快照：overseas_scraper.py（UC Driver）

**功能：** 每天跑一次，记录当日截面数据（Amazon价格/评分/月销、SimilarWeb流量、TikTok话题、Instagram粉丝）

**前置条件：** 关闭所有Chrome窗口

```powershell
cd C:\Users\lxxxxxx\Desktop\个人项目\popmart\phase2_overseas

# 前台运行（看实时输出）
python -u overseas_scraper.py

# 后台运行（推荐，输出到日志）
Start-Process python -ArgumentList '-u','overseas_scraper.py' `
  -WorkingDirectory (Get-Location) `
  -RedirectStandardOutput overseas_scraper_log.txt `
  -RedirectStandardError overseas_scraper_err.txt
```

**抓取顺序：** Amazon (12 ASIN) → SimilarWeb → TikTok (7话题+账号) → Instagram

**运行时长：** 约20-40分钟

---

### 5.2 首次登录：login_helper.py（Playwright + ChromePW）

**功能：** 打开一个专用浏览器（ChromePW profile），让用户手动登录3个网站，登录态保存供后续 ts_pw.py 使用

**重要：** 这个浏览器用的是 `%LOCALAPPDATA%\ChromePW`，不是你日常用的Chrome。但这个是专门给脚本用的，登录一次以后都不用重新登录。

```powershell
cd C:\Users\lxxxxxx\Desktop\个人项目\popmart\phase2_overseas
python -u login_helper.py
```

脚本会打开Chrome，自动跳转到三个登录页：
- Tab 1: Amazon 登录
- Tab 2: TikTok 登录
- Tab 3: Instagram 登录

登录完后**告诉Claude**，Claude会关闭浏览器保存session（或者等10分钟自动超时）。

---

### 5.3 时序采集：ts_pw.py（Playwright + ChromePW）

**功能：** 一次性抓取全部历史评论时间戳，构建时间序列

**前置条件：**
1. 先用 login_helper.py 登录过（ChromePW里有session）
2. **关闭所有Chrome窗口**（否则ChromePW profile被锁）

```powershell
cd C:\Users\lxxxxxx\Desktop\个人项目\popmart\phase2_overseas

# 全量（Amazon + TikTok + Instagram）
python -u ts_pw.py amazon tiktok instagram

# 单模块测试
python -u ts_pw.py amazon
python -u ts_pw.py tiktok
python -u ts_pw.py instagram
```

**运行时长预估：**
- Amazon: 6个ASIN × 最多25页 × 3-4秒/页 ≈ 30-60分钟
- TikTok: 4个关键词搜索 + 30个视频评论 ≈ 60-120分钟
- Instagram: 3个账号 × 8帖 × 5秒 ≈ 30分钟

---

## 六、踩坑记录（必读！下次别再浪费时间）

### 坑1：UC Driver 没有登录态

**症状：** overnight 定时任务跑完，amazon_review_dates / tiktok_comments 全是0行。

**原因：** UC Driver（undetected-chromedriver）每次启动都是全新浏览器，没有任何cookies，访问TikTok/Amazon需要登录的页面会被拦截在登录页。

**解决：** 改用 Playwright 的 `launch_persistent_context`，指向一个有登录态的Chrome profile目录。

---

### 坑2：Playwright 用真实Chrome profile → 锁冲突

**症状：** `playwright._impl._errors.TargetClosedError: BrowserType.launch_persistent_context: Target page, context or browser has been closed`，Browser logs 里有 `exitCode=21`。

**原因：** Chrome exit code 21 = `RESULT_CODE_PROFILE_IN_USE`。Chrome检测到profile目录被占用（哪怕你"关掉"了Chrome，后台进程还活着）。

**表现：** Chrome正常启动（能看到浏览器窗口），但1-2秒内就自动关闭。

**解决步骤（按顺序）：**
```powershell
# 1. 强杀所有chrome进程
Stop-Process -Name chrome -Force -ErrorAction SilentlyContinue

# 2. 等1-2秒
Start-Sleep -Seconds 2

# 3. 删掉 LevelDB 锁文件（这个是关键！光杀进程不够）
Remove-Item "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\LOCK" -Force -ErrorAction SilentlyContinue

# 4. 再运行脚本
```

---

### 坑3：用真实Chrome profile → TikTok登录不了

**症状：** Playwright用真实Chrome profile启动后，打开TikTok是未登录状态。即使用户在自己Chrome里明明登录着。

**原因：**
1. Playwright启动时加了 `--enable-automation` 标记，TikTok检测到自动化工具，清空session
2. Playwright还加了 `--disable-sync`，Chrome Sync不工作，服务端session不同步
3. 真实Chrome的cookies是DPAPI加密的，Playwright自己的Chromium可能无法正确读取

**结论：** 用真实Chrome profile这条路在Windows上对TikTok基本不可行。

---

### 坑4：login_helper.py 里用Playwright登录TikTok → 登录按钮失效/很卡

**症状：** Playwright打开的浏览器窗口里，TikTok登录页面点不动，或者极其卡顿。

**原因：** TikTok有bot检测，Playwright自动化标记（`navigator.webdriver = true`）被检测到，直接屏蔽交互。

**现状：** 用户已经在自己的Chrome里登录了TikTok/Amazon/Instagram。

**当前解决方向：**
- 方案A（推荐）：改用 `ChromePW` 独立profile，在 login_helper.py 里加 `--disable-blink-features=AutomationControlled`，patch掉webdriver标记，让TikTok检测不到自动化
- 方案B：在login_helper.py里加更多anti-detection措施（user agent、WebGL指纹等）
- 方案C（暂定，用户手动）：用户在自己Chrome里登录，然后用工具（如 `EditThisCookie`）把cookies导出，脚本里手动注入cookies

---

### 坑5：两个脚本的profile路径不一致（已修复）

**症状：** `login_helper.py` 用 `%LOCALAPPDATA%\ChromePW`，`ts_pw.py` 用 `%LOCALAPPDATA%\Google\Chrome\User Data`。登录helper存的session，ts_pw.py根本读不到。

**修复：** ts_pw.py 已改为与 login_helper.py 一致，都用 `ChromePW`。

---

### 坑6：Python输出缓冲，后台日志看不到

**症状：** 脚本后台跑了5分钟，日志文件还是空的，不知道脚本在做什么。

**原因：** Python stdout默认在非TTY时是块缓冲（4KB满了才写），后台重定向时特别明显。

**解决：** 始终用 `python -u`（unbuffered mode）运行脚本。

---

### 坑7：中文路径在PowerShell/cmd里乱码

**症状：** `xcopy` 或者 cmd 里的路径显示乱码，有时候导致找不到文件。

**原因：** Windows PowerShell/cmd 的编码设置跟Python不一致，中文字符（如"个人项目"）会被乱码处理。

**解决：**
- 脚本里用 `os.path.dirname(os.path.abspath(__file__))` 获取自身路径，不要硬编码中文
- 如果必须硬编码，用Unicode转义：`"\u4e2a\u4eba\u9879\u76ee"` = "个人项目"
- 运行脚本时 cd 到纯ASCII路径再运行，或者用完整绝对路径

---

### 坑8：BASE_DIR指向旧路径（已修复）

**症状：** ts_pw.py 的 `BASE_DIR` 原来硬编码指向 `~\Desktop\个人项目\popmart`，
但脚本已经移动到 `phase2_overseas/` 子目录，导致找不到 `overseas_data.db`。

**修复：** ts_pw.py 已改为 `os.path.dirname(os.path.abspath(__file__))`，
自动定位到脚本所在目录（即 phase2_overseas/）。

---

## 七、待完成工作

### 紧急
- [ ] **解决TikTok登录问题** → ts_pw.py 的 TikTok评论API需要登录态
  - 优先试：login_helper.py 加anti-detection措施 + 用ChromePW profile
  - 备选：手动导出cookies注入
- [ ] **采集 amazon_review_dates** → 这个不需要登录，应该现在就能跑
- [ ] **验证 instagram_comments 采集** → instagram_posts:15 / instagram_comments:234 已有数据

### 正常
- [ ] **overseas_analysis.py** — 分析脚本（图表+Excel报告）
  - 输入：overseas_data.db
  - 输出：Amazon评论速率时序图、TikTok讨论热度图、综合海外热度指数
- [ ] **设置每日定时快照** — overseas_scraper.py 每天夜里自动跑
- [ ] **SimilarWeb PRO数据** — 免费版数据精度低，PRO版需要登录

### 锦上添花
- [ ] 把海外热度指数与股价走势叠加（日线/周线）
- [ ] 名人带货事件标注（Lisa ins发布日期 vs 评论激增）

---

## 八、关键链接和账号信息

### 官方账号（已确认）

| 平台 | 账号 | 确认方式 |
|---|---|---|
| TikTok | @popmartglobal | 官方账号，2.7M粉丝 |
| Instagram | @popmart | TikTok bio写明 "IG:@popmart" |
| Instagram | ❌ @popmart_global | **假的，404** |

### Amazon搜索算法偏差

Amazon搜索"Dimoo"会把Labubu/Monsters产品排到最前面（1300+评论），
真正的Dimoo产品最多129评论。这说明在Amazon算法眼里，Labubu = Pop Mart的代名词。

---

## 九、下次启动的操作清单

```
□ 1. 关闭所有Chrome窗口
□ 2. cd 到 phase2_overseas 目录
□ 3. 先跑 Amazon（不需要登录）：
      python -u ts_pw.py amazon
□ 4. 确认 amazon_review_dates 有数据写入
□ 5. 解决TikTok登录问题（见坑4的方案）
□ 6. 完整跑：python -u ts_pw.py amazon tiktok instagram
□ 7. 写 overseas_analysis.py 出图表
```

---

## 十、环境信息

```
OS: Windows 11 Home China
Python: 3.13 (C:\Users\lxxxxxx\AppData\Local\Programs\Python\Python313\)
Chrome: 146.x（C:\Program Files\Google\Chrome\Application\chrome.exe）
ChromeDriver: ~/.cache/selenium/chromedriver/win64/146.0.7680.165/chromedriver.exe

依赖包：
  playwright            # ts_pw.py, login_helper.py
  undetected-chromedriver  # overseas_scraper.py
  sqlite3               # 内置

安装命令：
  pip install playwright undetected-chromedriver
  playwright install chromium
```
