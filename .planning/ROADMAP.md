# Roadmap: Pop Mart 海外另类数据追踪

## Milestones

- ✅ **v1.0 基础采集** - Phases 1-6 (shipped 2026-03-30)
- 🚧 **v1.1 数据管道重建 + 图表全面重做** - Phases 7-11 (in progress)

## Phases

<details>
<summary>✅ v1.0 基础采集 (Phases 1-6) - SHIPPED 2026-03-30</summary>

### Phase 1: 共享基础设施
**Goal**: 所有平台采集器可依赖的公共层已就绪，环境和账号凭证已准备完毕
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06, INFRA-07, INFRA-08
**Success Criteria** (what must be TRUE):
  1. shared/db.py 对现有 overseas_data.db 的 INSERT OR IGNORE 写入验证通过，不破坏已有快照数据
  2. 任意一个采集脚本中断后重启，从断点 JSON 恢复运行，不重头开始
  3. 每次运行产生带时间戳的日志文件，内容包含每条目标的采集结果摘要
  4. DrissionPage/instagrapi 环境就绪，账号凭证已配置
  5. 目标列表可通过 JSON 配置文件增减监控标的，不需要改动代码
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — pytest test scaffold
- [x] 01-02-PLAN.md — shared/ modules (db/log/rate/checkpoint) + config JSON files
- [x] 01-03-PLAN.md — dependency install, DB migration, Instagram session setup

### Phase 2: Instagram 时序采集
**Goal**: instagram_posts 和 instagram_comments 表已填充三个账号的历史评论，每条评论带时间戳
**Depends on**: Phase 1
**Requirements**: IG-01, IG-02, IG-03, IG-04
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md — TDD: test scaffold + instagram_ts.py implementation
- [x] 02-02-PLAN.md — Live API execution + human verification

### Phase 3: Amazon 时序采集
**Goal**: amazon_review_dates 表已填充 12 个 ASIN 的评论日期数据（受平台限制，137条）
**Depends on**: Phase 2
**Requirements**: AMZ-01, AMZ-02, AMZ-03, AMZ-04, AMZ-05
**Plans**: TBD

### Phase 4: TikTok 时序采集
**Goal**: tiktok_videos 表已填充含 create_time 的视频元数据，373视频/14K评论
**Depends on**: Phase 3
**Requirements**: TT-01, TT-02, TT-03, TT-04, TT-05
**Plans**: 1 plan

Plans:
- [x] 04-01-PLAN.md — TikTok DrissionPage 采集

### Phase 5: 分析报告
**Goal**: 三平台时序数据已输出为投研可用的趋势图和 Excel 报告
**Depends on**: Phase 4
**Requirements**: RPT-01, RPT-02, RPT-03, RPT-04, RPT-05, RPT-06
**Plans**: 1 plan

Plans:
- [x] 05-01-PLAN.md — overseas_analysis.py + generate_article.py

### Phase 6: 定时任务
**Goal**: overseas_scraper.py 每日自动运行，运维人员有明确故障处理手册
**Depends on**: Phase 5
**Requirements**: SCHED-01, SCHED-02
**Plans**: TBD

</details>

### 🚧 v1.1 数据管道重建 + 图表全面重做 (In Progress)

**Milestone Goal:** 重建采集-分析-展示全链路，使其支持可持续增量更新，分析口径从总数转向标准化贴均指标，网站图表全面重做。

#### Phase 7: Schema 基础修复

**Goal**: shared/db.py 是唯一可信的 schema 来源，init_db() 在全新和已有数据库上都无崩溃运行，新 IP 和增量更新所需的列已就位
**Depends on**: Phase 6 (v1.0)
**Requirements**: INFRA-11, INFRA-15
**Success Criteria** (what must be TRUE):
  1. 在空数据库上调用 init_db()，pragma_table_info 确认 tiktok_videos 含 last_comment_scraped_at、shares、likes、comments_count 列，instagram_posts 含 last_comment_scraped_at 列
  2. 在已有生产数据库（overseas_data.db）上调用 init_db()，现有数据行数不变，不抛出异常
  3. upsert_video_metadata() 更新已有视频的 views/likes/comments_count，不重置 id、create_time、scraped_at
  4. IP_PATTERNS 包含 twinkle/星星人 和 crybaby/哭娃 规则，dry-run 分类对已有视频标题产出非空 IP 分布
**Plans**: 1 plan

Plans:
- [x] 07-01-PLAN.md — Schema 完整性修复 + upsert 函数 + IP 分类验证

#### Phase 8: 采集器增量化重建

**Goal**: TikTok 和 Instagram 采集器每次运行真正发现新内容，不再因 checkpoint 或 skip gate 永久阻塞；零评论历史帖子和新 IP 目标均纳入采集范围
**Depends on**: Phase 7
**Requirements**: INFRA-12, INFRA-13, INFRA-14, SCRP-01, SCRP-02, SCRP-03
**Success Criteria** (what must be TRUE):
  1. 对 2 个已存在且评论数为 0 的 TikTok 视频 ID 运行重建后的采集器，COUNT(tiktok_comments) 在运行前后增加，日志显示"已存在但补采评论"而非"跳过"
  2. 对 2 个零评论 Instagram 帖子运行采集器，instagram_comments 表新增对应评论行，last_comment_scraped_at 更新为当前时间
  3. 新运行开始时 checkpoint 重置为空，日志不出现"已永久完成，跳过整个关键词"
  4. tiktok_browser.py --keywords twinkle crybaby 正常采集并写入，ip 字段分类正确
  5. Instagram 目标覆盖 14 个 hashtag + @popmart 200 帖，配置文件已更新
**Plans**: 2 plans
**UI hint**: no

Plans:
- [ ] 08-01-PLAN.md — TikTok scraper three-layer fix (checkpoint + upsert + comment refresh)
- [ ] 08-02-PLAN.md — Instagram scraper three-layer fix + comment backfill

#### Phase 9: 分析导出层重写（贴均指标）

**Goal**: export_json.py 全部导出函数使用元数据 comments_count 驱动的贴均指标，JSON 输出包含 n（月帖数）和 data_confidence 字段，分析口径与采集实际覆盖率解耦
**Depends on**: Phase 8
**Requirements**: ANAL-01, ANAL-02, ANAL-03, ANAL-04, ANAL-05, ANAL-06, ANAL-07, ANAL-08, ANAL-09
**Success Criteria** (what must be TRUE):
  1. brand-trend.json 包含 avg_comments_per_post 键而非 total_comments，每月数据对象含 n 字段（帖子数）
  2. ip-share.json 和 ip-share-trend.json 不含 "Pop Mart" 主品牌条目，Twinkle 和 Crybaby 作为独立 IP 出现
  3. cross-platform-index.json 两个平台均使用 SUM(comments_count) from 元数据表而非 COUNT(评论行)
  4. overview.json 含 data_freshness 字段（最后采集时间戳）和各平台覆盖率摘要，不含 comment_quality 相关键
  5. ugc-amplification.json 输出月度 avg_views(UGC) / avg_views(official) 趋势数组
**Plans**: TBD

#### Phase 10: 网站图表全面重做

**Goal**: 网站所有图表消费新 JSON 格式，新增 Twinkle/Crybaby IP 系列和 UGC 放大倍率图表，数据过时时展示警告徽章
**Depends on**: Phase 9
**Requirements**: WEB-01, WEB-02, WEB-03, WEB-04, WEB-05, WEB-06
**Success Criteria** (what must be TRUE):
  1. 本地 astro dev 启动后，趋势图显示 avg_comments_per_post 数值（非总评论数），月柱标注 n=X 样本数
  2. IP 份额图和趋势图展示 Twinkle 和 Crybaby 系列，数据开始日期前显示为空而非零（connectNulls: false）
  3. UGC 放大倍率图表可渲染，显示月度 UGC/官方平均播放比
  4. Comment Quality 图表已从页面移除，替换为数据覆盖率面板（平台覆盖率、日期范围、月帖数）
  5. 当任一平台最新数据超过 7 天时，Hero 区域显示数据过时警告徽章
**Plans**: TBD
**UI hint**: yes

#### Phase 11: 全量重采 + 部署上线

**Goal**: 以重建后的采集器对全部目标完成一次干净的全量采集，填充 last_comment_scraped_at，网站以新数据重新构建并部署到 GitHub Pages，定时任务配置完毕
**Depends on**: Phase 10
**Requirements**: SCRP-04, SCRP-05
**Success Criteria** (what must be TRUE):
  1. tiktok_videos 和 instagram_posts 中 last_comment_scraped_at IS NOT NULL 的行占比超过 90%
  2. GitHub Pages 部署后，网站品牌趋势图显示的贴均评论数与本地 export_json.py 输出一致
  3. Windows Task Scheduler 任务历史显示至少一次自动运行成功，日志文件时间戳正确
**Plans**: TBD

## Progress

**Execution Order:**
v1.0: 1 → 2 → 3 → 4 → 5 → 6
v1.1: 7 → 8 → 9 → 10 → 11

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. 共享基础设施 | v1.0 | 3/3 | Complete | 2026-03-28 |
| 2. Instagram 时序采集 | v1.0 | 2/2 | Complete | 2026-03-29 |
| 3. Amazon 时序采集 | v1.0 | -/- | Partial (on hold) | 2026-03-29 |
| 4. TikTok 时序采集 | v1.0 | 1/1 | Complete | 2026-03-30 |
| 5. 分析报告 | v1.0 | 1/1 | Complete | 2026-03-30 |
| 6. 定时任务 | v1.0 | 0/TBD | Deferred to v1.1 | - |
| 7. Schema 基础修复 | v1.1 | 1/1 | Complete | 2026-04-02 |
| 8. 采集器增量化重建 | v1.1 | 0/2 | Planned | - |
| 9. 分析导出层重写 | v1.1 | 0/TBD | Not started | - |
| 10. 网站图表全面重做 | v1.1 | 0/TBD | Not started | - |
| 11. 全量重采 + 部署上线 | v1.1 | 0/TBD | Not started | - |
