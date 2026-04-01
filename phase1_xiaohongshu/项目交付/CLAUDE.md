# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

泡泡玛特（Pop Mart）小红书舆情分析。从小红书采集各IP相关帖子和评论数据，分析IP热度时间序列、评论生命周期、地域分布。

## 数据架构

```
chart_data.json (1001帖宏观数据，ip/date/likes)
    ↓
ip_analysis_main.py → Excel报告 + 图表
    ↑
popmart_comments.db (240帖/13000+评论，深挖数据)
    ↑
scrape_comments.py (UC爬虫自动采集)
    ↑
dig_queue.txt (259条待挖帖子队列，点赞\t标题)
```

### SQLite数据库：`popmart_comments.db`

```sql
posts(id, title, ip, likes TEXT, collects, comments_total, post_date, url, note_id)
-- UNIQUE(title), likes存为文本(如"81000")，排序需CAST
-- post_date仅10%有值(24/240)，其余通过最早评论日期推断

comments(id, post_id, commenter, comment_date, comment_likes, comment_text, location)
-- UNIQUE(post_id, commenter, comment_date, comment_likes)
-- comment_date原始三种格式：YYYY-MM-DD(52%) / MM-DD+地区(32%) / N天前+地区(15%)
-- ip_analysis_clean.py的parse_comment_date()统一为YYYY-MM-DD
-- comment_text 91.5%有内容，可做关键词分析
```

### chart_data.json

```json
{"posts": [{"ip": "Dimoo", "date": "2025-10-11", "likes": 2148}, ...], "total_unique": 1001}
```

注意采样偏差：2026-03占52.8%帖子，跨月绝对值对比不可靠，需用归一化指标（每帖均评论数、月内IP份额）。

## IP分类

`scrape_comments.py:classify_ip()` 按标题关键词匹配：
Labubu/拉布布 → Labubu | dimoo → Dimoo | 星星人 | molly → Molly | skullpanda/sp → Skullpanda | zsiga/嘎子 → Zsiga | 小甜豆 | 默认 → 泡泡玛特

## 核心公式

```
热度指数v1 = avg_likes × ln(post_count+1) × (1 + max_likes/(avg_likes+1) × 0.1)
热度指数v2 = v1 × (1 + min(comment_ratio, 50) × 0.01)  -- comment_ratio = 评论数/(帖子数+1)
```

## 关键命令

```bash
# 运行分析（生成Excel + 8张图表）
cd C:\Users\lxxxxxx\Desktop\个人项目\popmart
python ip_analysis_main.py

# 运行爬虫（需先关闭所有Chrome窗口）
python -u scrape_comments.py          # 全量
python -u scrape_comments.py --limit 3 # 测试3条

# 后台运行爬虫（PowerShell，输出重定向到日志）
Start-Process python '-u','scrape_comments.py' -WorkingDirectory $PWD -RedirectStandardOutput scrape_log.txt -RedirectStandardError scrape_log_err.txt -WindowStyle Hidden

# 查进度
python -c "
import sqlite3, json, os
conn = sqlite3.connect('popmart_comments.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM comments'); print('评论:', c.fetchone()[0])
c.execute('SELECT COUNT(*) FROM posts'); print('帖子:', c.fetchone()[0])
cp = json.load(open('scrape_checkpoint.json')) if os.path.exists('scrape_checkpoint.json') else {}
print('checkpoint:', len(cp.get('completed',[])))
"
```

## 代码模块

| 文件 | 职责 |
|------|------|
| `ip_analysis_clean.py` | 数据清洗：日期解析、likes转换、加载DB+chart_data为DataFrame |
| `ip_analysis_main.py` | 主分析：6个Sheet的Excel + 调用charts模块 |
| `ip_analysis_charts.py` | 可视化：8张PNG图表（评论密度/品牌趋势/份额/衰减/排名/地域/散点/仪表盘） |
| `scrape_comments.py` | UC爬虫：搜索→匹配→点击→滚动提取评论→SQLite入库 |

## 爬虫运行注意

- **启动前必须关闭所有Chrome**，否则UC连接失败
- 断点续传：`scrape_checkpoint.json` 记录已完成帖子，重启自动跳过
- 反爬延迟：帖子间2-4分钟+20%概率10-20分钟走神+每15条休息20-35分钟
- 进程监控：`wmic process where "name='python.exe'" get ProcessId,Name`
- 日志查看：`tail -30 scrape_log.txt`
- Chrome配置目录：`.uc_profile/`（保存登录状态，勿删）

## 硬编码需维护

- `ip_analysis_clean.py` 第16行 `SCRAPE_DATE = datetime(2026, 3, 25)` — 相对时间("N天前")反推的锚点
- `ip_analysis_clean.py` 第13行 `BASE_DIR` — 项目绝对路径
