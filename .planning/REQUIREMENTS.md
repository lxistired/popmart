# Requirements: Pop Mart 数据管道重建 v1.1

**Defined:** 2026-04-01
**Core Value:** 能稳定采集并增量更新三个平台的评论时序数据，通过标准化贴均指标产出可持续追踪的热度分析

## v1.0 Validated Requirements

Requirements from v1.0 milestone — shipped and confirmed working.

- ✓ INFRA-01~08: 共享DB层、分页、增量采集、重试、日志、配置、断点续采、日期截止
- ✓ IG-01~04: Instagram instagrapi 帖子评论采集
- ✓ AMZ-01~05: Amazon DrissionPage 评论采集（受平台限制137条）
- ✓ TT-01~05: TikTok DrissionPage 视频+评论采集（373视频/14K评论）
- ✓ Astro 5 SSG + ECharts 10个图表组件 + GitHub Pages 部署

## v1.1 Requirements

### Infrastructure 基础设施修复 (INFRA)

- [x] **INFRA-11**: shared/db.py init_db() 在全新和已有数据库上都正确运行，补齐缺失列
- [x] **INFRA-12**: 采集脚本 checkpoint 从永久完成跳过改为会话级别，每次运行重新扫描所有关键词
- [x] **INFRA-13**: tiktok_videos 和 instagram_posts 元数据通过 UPSERT 在重新访问时刷新
- [x] **INFRA-14**: 新增 last_comment_scraped_at 列，近期视频每次运行重新抓取评论
- [x] **INFRA-15**: IP 分类规则新增 Twinkle 和 Crybaby

### Analysis 分析口径重建 (ANAL)

- [ ] **ANAL-01**: export_brand_trend 从 COUNT(评论行) 改为 AVG(元数据 comments_count) 按月分组
- [ ] **ANAL-02**: export_tiktok_trend 改为按月统计贴均评论数（使用元数据）
- [ ] **ANAL-03**: export_instagram_trend 同样改为按月贴均评论数
- [ ] **ANAL-04**: export_ip_share 和 export_ip_share_trend 改为基于帖子数+元数据评论数
- [ ] **ANAL-05**: export_cross_platform_index 改用元数据驱动的密度指数
- [ ] **ANAL-06**: export_official_engagement 使用元数据 comments_count 按发布月分组
- [ ] **ANAL-07**: 删除 export_comment_quality，替换为数据覆盖率摘要
- [ ] **ANAL-08**: export_ip_share_trend 排除 Pop Mart 主品牌
- [ ] **ANAL-09**: 新增 export_ugc_amplification — UGC vs 官方放大倍率趋势

### Website 网站图表重做 (WEB)

- [ ] **WEB-01**: 所有图表组件适配新分析口径的 JSON 数据格式
- [ ] **WEB-02**: IP 份额卡片和趋势图新增 Twinkle + Crybaby
- [ ] **WEB-03**: 官方号帖子热度图表使用新口径数据
- [ ] **WEB-04**: 新增 UGC 放大倍率图表组件
- [ ] **WEB-05**: 删除 Comment Quality 图表，替换或移除
- [ ] **WEB-06**: 首页 overview 统计卡片适配新数据结构

### Scraping 数据采集 (SCRP)

- [x] **SCRP-01**: 60个零评论 Instagram 帖子评论数据补全
- [x] **SCRP-02**: TikTok 采集目标新增 twinkle/crybaby 关键词
- [x] **SCRP-03**: Instagram 采集目标全面对齐 TikTok（14个 hashtag + @popmart 200帖）
- [ ] **SCRP-04**: 清除旧 checkpoint 后全量重新采集
- [ ] **SCRP-05**: 配置定时任务每日自动采集+导出+部署

## v2 Requirements

- **PERF-01**: 采集运行时间优化（视频数超1000时控制在2小时内）
- **TEXT-01**: 评论文本情感分析
- **ALERT-01**: 热度异常告警
- **HIST-01**: 历史数据生存者偏差校正

## Out of Scope

| Feature | Reason |
|---------|--------|
| 实时交互看板 | 当前需求是静态网站展示 |
| Phase 1 小红书改动 | 已交付锁定 |
| TikTok 直播数据 | 复杂度高，收益不明确 |
| SimilarWeb PRO API | 付费且非核心 |
| Instagram DOM 重构 | 已知风险但不在本里程碑范围 |
| 评论文本深度分析 | 2.8%采样率下统计意义不足 |
| 网站视觉/美学重设计 | 保留现有风格 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-11 | Phase 7 | Complete |
| INFRA-15 | Phase 7 | Complete |
| INFRA-12 | Phase 8 | Complete |
| INFRA-13 | Phase 8 | Complete |
| INFRA-14 | Phase 8 | Complete |
| SCRP-01 | Phase 8 | Complete |
| SCRP-02 | Phase 8 | Complete |
| SCRP-03 | Phase 8 | Complete |
| ANAL-01 | Phase 9 | Pending |
| ANAL-02 | Phase 9 | Pending |
| ANAL-03 | Phase 9 | Pending |
| ANAL-04 | Phase 9 | Pending |
| ANAL-05 | Phase 9 | Pending |
| ANAL-06 | Phase 9 | Pending |
| ANAL-07 | Phase 9 | Pending |
| ANAL-08 | Phase 9 | Pending |
| ANAL-09 | Phase 9 | Pending |
| WEB-01 | Phase 10 | Pending |
| WEB-02 | Phase 10 | Pending |
| WEB-03 | Phase 10 | Pending |
| WEB-04 | Phase 10 | Pending |
| WEB-05 | Phase 10 | Pending |
| WEB-06 | Phase 10 | Pending |
| SCRP-04 | Phase 11 | Pending |
| SCRP-05 | Phase 11 | Pending |

**Coverage:**
- v1.1 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0

---
*Requirements defined: 2026-04-01*
*Last updated: 2026-04-01 after roadmap creation (v1.1 phases 7-11)*
