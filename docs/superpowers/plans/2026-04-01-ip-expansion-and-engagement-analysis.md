# IP扩展 + 官方号热度分析

> 日期: 2026-04-01
> 模式: Harness Design (Sprint-based, File-based Handoffs)

## 目标

1. **IP扩展**: 新增 星星人(Twinkle Twinkle) 和 哭娃(Crybaby) 到采集→分析→网站全链路
2. **官方号帖子热度分析**: 首30天评论量(Launch-30d Engagement)，按发布月份聚合，展示官方号热度趋势
3. **Instagram 采集目标对齐 TikTok**: 补齐缺失的 IP hashtag

---

## Sprint 1: IP扩展 — 星星人 + Crybaby

### 背景
- Phase 1(小红书)已有星星人和Crybaby分类，但Phase 2(海外)的 `IP_PATTERNS` 只有5个IP
- 网站角色图片只有4个(Labubu/Dimoo/Molly/Skullpanda)，缺 Zsiga/星星人/Crybaby
- 需要同步更新：IP分类规则、采集目标、颜色映射、角色图片、图表组件

### 任务

#### Task 1: 更新 IP_PATTERNS (export_json.py)
**文件**: `phase2_overseas/export_json.py:16-31`
- 在 `IP_PATTERNS` 列表中新增:
  ```python
  ('Twinkle', re.compile(r'twinkle|星星人', re.IGNORECASE)),
  ('Crybaby', re.compile(r'crybaby|cry\s*baby|哭娃', re.IGNORECASE)),
  ```
- 注意顺序：放在 Zsiga 之后、默认 'Pop Mart' 之前
- **验证**: 运行 `python -m pytest tests/ -v` 确认现有测试通过

#### Task 2: 更新采集目标 (TikTok + Instagram 对齐)
**TikTok** (`phase2_overseas/config/tiktok_targets.json`):
- 新增关键词: `"twinkle twinkle popmart"`, `"crybaby popmart"`

**Instagram** (`phase2_overseas/config/instagram_targets.json`):
- 当前 hashtag 严重不足（只有 labubu 系列），需对齐 TikTok 覆盖所有 IP
- 新增 hashtag: `mollypopmart`, `skullpanda`, `dimoo`, `popmartunboxing`, `twinkletwinkle`, `twinklepopmart`, `crybaby`, `crybabypopmart`

#### Task 3: 准备角色图片
**目录**: `website/public/characters/`
- 需要 `twinkle.png` 和 `crybaby.png` (约 200x200px, 透明背景PNG)
- 方案: 从 Pop Mart 官网提取产品图，裁剪处理
- 同时补充缺失的 `zsiga.png`

#### Task 4: 更新网站颜色映射和图片映射
**文件列表**:
- `website/src/components/IpShareCards.astro` — IP_COLORS + IP_IMAGES 新增:
  - Twinkle: `'#FFD600'` (星星黄)
  - Crybaby: `'#455A64'` (蓝灰色，沿用Phase 1)
- `website/src/components/IpShareTrendChart.astro` — IP_COLORS 同步
- `website/src/components/BrandTrendChart.astro` — 如有IP相关配色也同步

#### Task 5: 重新导出JSON数据
```bash
cd phase2_overseas && python -u export_json.py
```
- 新IP分类会影响: ip-share.json, ip-share-trend.json
- 复制到 website/src/data/ 和 website/public/data/

#### Task 6: 更新测试
**文件**: `phase2_overseas/tests/test_export_json.py`
- 新增测试用例: 确认 Twinkle/Crybaby 能被正确分类
- 运行全量测试: `python -m pytest tests/ -v`

---

## Sprint 2: 官方号帖子热度分析

### 背景
用户需求: 对比官方号不同时期帖子的热度变化。

**统计口径: 首30天评论量 (Launch-30d Engagement)**
- 每个帖子有发布日期(post_date)
- 该帖子的评论也有日期(comment_date)
- 只统计 comment_date 在 post_date 后30天内的评论数 → "首30天评论量"
- 按帖子发布月份聚合(月均)，展示官方号热度趋势
- 优点：公平对比新旧帖子（不受累积时间影响）

### 数据可用性
| 平台 | 官方账号 | 帖子数 | 评论数 | 日期精度 |
|------|---------|--------|--------|---------|
| TikTok | popmartglobal | ~35 | 有comment_date | YYYY-MM-DD |
| Instagram | popmart | ~279 | 有comment_date | YYYY-MM-DD |

### 任务

#### Task 7: 新增导出函数 export_official_engagement()
**文件**: `phase2_overseas/export_json.py`

```python
def export_official_engagement(conn):
    """官方号帖子首月热度分析。
    
    对每个官方号帖子，统计发布当月获得的评论数。
    按发布月份聚合，展示热度趋势。
    """
```

**SQL逻辑**:
```sql
-- TikTok: popmartglobal 帖子的首30天评论量
SELECT 
    strftime('%Y-%m', datetime(v.create_time, 'unixepoch')) as post_month,
    v.video_id,
    COUNT(c.comment_id) as launch_30d_comments
FROM tiktok_videos v
LEFT JOIN tiktok_comments c ON v.video_id = c.video_id
    AND julianday(c.comment_date) - julianday(datetime(v.create_time, 'unixepoch')) BETWEEN 0 AND 30
WHERE v.author = 'popmartglobal'
GROUP BY v.video_id;

-- Instagram: popmart 帖子的首30天评论量
SELECT
    strftime('%Y-%m', p.post_date) as post_month,
    p.shortcode,
    COUNT(c.comment_id) as launch_30d_comments
FROM instagram_posts p
LEFT JOIN instagram_comments c ON p.shortcode = c.shortcode
    AND julianday(c.comment_date) - julianday(p.post_date) BETWEEN 0 AND 30
WHERE p.account = 'popmart'
GROUP BY p.shortcode;
```

**按月聚合后输出** (`official-engagement.json`):
```json
{
  "tiktok": [
    {"month": "2025-01", "posts": 3, "total_30d_comments": 150, "avg_30d_comments": 50},
    {"month": "2025-02", "posts": 5, "total_30d_comments": 420, "avg_30d_comments": 84}
  ],
  "instagram": [
    {"month": "2024-06", "posts": 8, "total_30d_comments": 2100, "avg_30d_comments": 262}
  ]
}
```

#### Task 8: 新增 Astro 图表组件
**文件**: `website/src/components/OfficialEngagementChart.astro`

- **图表类型**: 双平台折线图 (类似 CrossPlatformChart)
- **X轴**: 发布月份
- **Y轴**: 平均首月评论数 (avg_comments)
- **两条线**: TikTok (黑色) + Instagram (粉色)
- **标题**: "官方号帖子热度 OFFICIAL POST ENGAGEMENT"
- **副标题**: "帖子发布后30天内平均评论数"
- 复用 CrossPlatformChart.astro 的 ECharts 加载模式

#### Task 9: 接入首页
**文件**: `website/src/pages/index.astro`
- 导入 OfficialEngagementChart
- 放在 BrandVsUgcChart 之后、CommentQualityChart 之前
- 图表顺序: 品牌热度 → IP份额 → 跨平台指数 → 品牌vs UGC → **官方号热度** → 评论质量

#### Task 10: 更新 export_json.py 的 write_all()
- 新增 `export_official_engagement()` 调用
- 输出到 `official-engagement.json`

#### Task 11: 测试
- 新增 `test_export_official_engagement` 测试
- 运行全量测试
- 本地 `astro build` 验证构建

---

## Sprint 3: 集成验证 + 部署

#### Task 12: 全量数据刷新
```bash
cd phase2_overseas
python -u export_json.py
cp website数据文件...
```

#### Task 13: 本地构建验证
```bash
cd website && npm run build
```

#### Task 14: 视觉验证
- 用浏览器打开本地构建结果或部署后的站点
- 验证所有图表渲染正确
- 验证移动端适配
- 验证新IP在IP份额卡片和趋势图中正确显示

#### Task 15: 提交部署
- git add + commit + push
- 等待 GitHub Actions 部署
- 在线验证 https://lxistired.github.io/popmart/

---

## 文件变更清单

| 文件 | 变更类型 | Sprint |
|------|---------|--------|
| `phase2_overseas/export_json.py` | 修改: IP_PATTERNS + 新函数 | 1, 2 |
| `phase2_overseas/config/tiktok_targets.json` | 修改: 新增关键词 | 1 |
| `phase2_overseas/config/instagram_targets.json` | 修改: 对齐TikTok hashtag | 1 |
| `phase2_overseas/tests/test_export_json.py` | 修改: 新增测试 | 1, 2 |
| `website/public/characters/twinkle.png` | 新增 | 1 |
| `website/public/characters/crybaby.png` | 新增 | 1 |
| `website/public/characters/zsiga.png` | 新增 | 1 |
| `website/src/components/IpShareCards.astro` | 修改: 颜色+图片 | 1 |
| `website/src/components/IpShareTrendChart.astro` | 修改: 颜色 | 1 |
| `website/src/components/OfficialEngagementChart.astro` | 新增 | 2 |
| `website/src/pages/index.astro` | 修改: 导入新图表 | 2 |
| `website/src/data/official-engagement.json` | 新增 | 2 |
| `website/public/data/official-engagement.json` | 新增 | 2 |

## 执行模式

按 Harness Design 模式执行:
- 每个 Sprint 完成后进行 **Evaluator Review** (代码审查 + 视觉验证)
- 使用 Subagent-Driven Development 并行执行独立任务
- 文件级 handoff: Sprint 1 的 IP_PATTERNS 变更是 Sprint 2 的前置依赖
- Sprint 3 的视觉验证是质量门控

## 角色图片获取方案

角色图片需要从外部获取（Pop Mart 官网产品图）。方案:
1. 优先: 从 popmart.com 产品页截取角色图片
2. 备选: 用简单的文字+颜色圆形占位符（类似 Pop Mart 的 "Po" 占位符）
3. 图片规格: 200x200px, PNG, 透明背景，风格与现有 labubu.png 一致
