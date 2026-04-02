---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: 数据管道重建 + 图表全面重做
status: executing
stopped_at: Completed 09-01-PLAN.md
last_updated: "2026-04-02T06:47:53.715Z"
last_activity: 2026-04-02
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 4
  completed_plans: 4
  percent: 40
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-01)

**Core value:** 能稳定采集并增量更新三个平台的评论时序数据，通过标准化贴均指标产出可持续追踪的热度分析
**Current focus:** Phase 8 — 采集器增量化重建

## Current Position

Phase: 8 of 11 (采集器增量化重建)
Plan: 2 of 2 (08-01 complete)
Status: Ready to execute
Last activity: 2026-04-02

Progress: [####░░░░░░] 40%

## Performance Metrics

**Velocity:**

- Total plans completed: 1 (v1.1)
- Average duration: 9min
- Total execution time: 9min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 07-schema | 1 | 9min | 9min |

*Updated after each plan completion*
| Phase 08-scrapers P02 | 6min | 2 tasks | 2 files |
| Phase 08-scrapers P01 | 8min | 2 tasks | 2 files |
| Phase 09-export P01 | 11min | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v1.1 Init]: 分析口径从总数→贴均，因平台搜索偏向近期帖
- [v1.1 Init]: 删除永久 checkpoint，与分析层根本冲突
- [v1.1 Init]: 图表全面重做，新口径不兼容旧组件
- [v1.1 Research]: Three-layer skip problem — 必须同时修复 checkpoint + video dedup + INSERT OR IGNORE 三层，只改一层会产生"运行正常但无新数据"的隐性失败
- [v1.1 Research]: 切换贴均指标后历史月份因采样偏差会显示虚高，每月数据需附 n= 样本数字段
- [v1.1 Research]: 不需要新依赖库，全部改动是 SQL 模式和逻辑修正
- [Phase 7]: init_db(conn=None) pattern for testability without changing existing callers
- [Phase 7]: ON CONFLICT DO UPDATE only touches volatile metrics, never identity fields
- [Phase 7]: last_comment_scraped_at excluded from upsert UPDATE SET -- scrapers set it directly
- [Phase 7]: _apply_incremental_migrations uses try/except per ALTER for idempotency
- [Phase 08-scrapers]: Per-post immediate save replaces batch accumulation to prevent data loss on crash
- [Phase 08-scrapers]: Session-scoped checkpoint: reset completed sets at run start, checkpoint file for crash recovery only
- [Phase 08-scrapers]: _needs_comment_refresh: 90-day recency + 7-day staleness window for comment re-scraping
- [Phase 08-scrapers]: Session-scoped checkpoint: completed=set() at run start for both TikTok and Instagram scrapers
- [Phase 08-scrapers]: Upsert-all-discovered pattern: every video/post gets metadata refreshed, comment fetch is conditional on _needs_comment_refresh
- [Phase 09-export]: All volume metrics use metadata comments_count, never COUNT of comment rows
- [Phase 09-export]: Pop Mart brand excluded from all IP share calculations
- [Phase 09-export]: export_comment_quality deleted, replaced by export_data_coverage

### Pending Todos

None yet.

### Blockers/Concerns

- Chrome 必须关闭才能运行采集脚本（Phase 8/11 执行前需确认）
- TikTok session 1-2 天过期，全量重采（Phase 11）需监控登录态
- 60 个 Instagram 零评论帖子部分可能因平台限制无法补抓（Phase 8 需评估策略）

## Session Continuity

Last session: 2026-04-02T06:47:53.705Z
Stopped at: Completed 09-01-PLAN.md
Resume file: None
