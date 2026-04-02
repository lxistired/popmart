# Website Charts + Mobile + Update Mechanism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single broken weekly trend chart with 5 monthly ECharts interactive charts, add mobile responsive CSS, and change daily update script to launch Claude Code.

**Architecture:** Extend `export_json.py` with 5 new export functions (TDD), create 5 new Astro ECharts components replacing `TrendChart.astro`, add `@media` breakpoints to all components, and rewrite `daily_update.bat`.

**Tech Stack:** Python 3.13, pytest, Astro 5, ECharts 5 CDN, CSS @media queries

---

## File Structure

**Modify:**
- `phase2_overseas/export_json.py` — add 5 export functions + update `write_all()`
- `phase2_overseas/tests/test_export_json.py` — add tests for new exports
- `website/src/pages/index.astro` — replace TrendChart with 5 new chart components
- `website/src/styles/global.css` — add mobile breakpoints
- `website/src/layouts/Base.astro` — mobile nav styles
- `website/src/components/Hero.astro` — mobile hero styles
- `website/src/components/StatCards.astro` — mobile 2-col grid
- `website/src/components/IpShareCards.astro` — mobile scroll/grid
- `website/src/components/LatestPosts.astro` — mobile single column
- `scripts/daily_update.bat` — rewrite to launch Claude Code

**Create:**
- `website/src/components/BrandTrendChart.astro`
- `website/src/components/IpShareTrendChart.astro`
- `website/src/components/CrossPlatformChart.astro`
- `website/src/components/BrandVsUgcChart.astro`
- `website/src/components/CommentQualityChart.astro`

**Delete:**
- `website/src/components/TrendChart.astro`

---

### Task 1: Export brand-trend.json (TDD)

**Files:**
- Modify: `phase2_overseas/export_json.py`
- Modify: `phase2_overseas/tests/test_export_json.py`

- [ ] **Step 1: Write failing test**

Add to `phase2_overseas/tests/test_export_json.py`:

```python
def test_export_brand_trend(test_db):
    from export_json import export_brand_trend
    result = export_brand_trend(test_db)
    assert isinstance(result, list)
    assert len(result) > 0
    first = result[0]
    assert 'month' in first
    assert 'comments' in first
    assert 'videos' in first
    assert 'density' in first
    # density = comments / videos
    assert first['density'] == first['comments'] / max(first['videos'], 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py::test_export_brand_trend -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement export_brand_trend**

Add to `phase2_overseas/export_json.py` before `write_all()`:

```python
def _month_key(date_str):
    """Convert YYYY-MM-DD to YYYY-MM month key."""
    try:
        return date_str[:7]
    except (TypeError, IndexError):
        return None


def export_brand_trend(conn):
    """Export monthly comment volume + video count + comment density for TikTok."""
    # Monthly video count
    rows = conn.execute(
        "SELECT create_time FROM tiktok_videos"
    ).fetchall()
    monthly_videos = {}
    for (ts,) in rows:
        try:
            from datetime import datetime as dt
            d = dt.utcfromtimestamp(int(ts))
            month = d.strftime('%Y-%m')
        except (ValueError, TypeError, OSError):
            continue
        monthly_videos[month] = monthly_videos.get(month, 0) + 1

    # Monthly comment count
    comments = conn.execute(
        "SELECT comment_date FROM tiktok_comments"
    ).fetchall()
    monthly_comments = {}
    for (date,) in comments:
        month = _month_key(date)
        if month:
            monthly_comments[month] = monthly_comments.get(month, 0) + 1

    # Merge
    all_months = sorted(set(list(monthly_videos.keys()) + list(monthly_comments.keys())))
    result = []
    for m in all_months:
        vids = monthly_videos.get(m, 0)
        coms = monthly_comments.get(m, 0)
        density = round(coms / max(vids, 1), 1)
        result.append({'month': m, 'comments': coms, 'videos': vids, 'density': density})
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py::test_export_brand_trend -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add phase2_overseas/export_json.py phase2_overseas/tests/test_export_json.py
git commit -m "feat(export): add export_brand_trend — monthly comment volume + density"
```

---

### Task 2: Export ip-share-trend.json (TDD)

**Files:**
- Modify: `phase2_overseas/export_json.py`
- Modify: `phase2_overseas/tests/test_export_json.py`

- [ ] **Step 1: Write failing test**

Add to `phase2_overseas/tests/test_export_json.py`:

```python
def test_export_ip_share_trend(test_db):
    from export_json import export_ip_share_trend
    result = export_ip_share_trend(test_db)
    assert isinstance(result, list)
    assert len(result) > 0
    first = result[0]
    assert 'month' in first
    assert 'ip' in first
    assert 'share_pct' in first
    assert 'count' in first
    # share_pct should be between 0 and 100
    for r in result:
        assert 0 <= r['share_pct'] <= 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py::test_export_ip_share_trend -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement export_ip_share_trend**

Add to `phase2_overseas/export_json.py` before `write_all()`:

```python
def export_ip_share_trend(conn):
    """Export monthly IP comment share percentages (TikTok + Instagram combined)."""
    # Build video_id → IP mapping
    vid_rows = conn.execute("SELECT video_id, source, title FROM tiktok_videos").fetchall()
    video_ip = {vid: classify_ip(src or '', title or '') for vid, src, title in vid_rows}

    # Build shortcode → IP mapping
    post_rows = conn.execute("SELECT shortcode, account, caption FROM instagram_posts").fetchall()
    post_ip = {sc: classify_ip(acc or '', cap or '') for sc, acc, cap in post_rows}

    # Aggregate all comments by month and IP
    monthly = {}

    # TikTok comments
    tt_comments = conn.execute("SELECT video_id, comment_date FROM tiktok_comments").fetchall()
    for vid, date in tt_comments:
        month = _month_key(date)
        ip = video_ip.get(vid, 'Pop Mart')
        if month:
            key = (month, ip)
            monthly[key] = monthly.get(key, 0) + 1

    # Instagram comments
    ig_comments = conn.execute("SELECT shortcode, comment_date FROM instagram_comments").fetchall()
    for sc, date in ig_comments:
        month = _month_key(date)
        ip = post_ip.get(sc, 'Pop Mart')
        if month:
            key = (month, ip)
            monthly[key] = monthly.get(key, 0) + 1

    # Calculate monthly totals and percentages
    month_totals = {}
    for (month, ip), count in monthly.items():
        month_totals[month] = month_totals.get(month, 0) + count

    result = []
    for (month, ip), count in sorted(monthly.items()):
        total = month_totals[month]
        share_pct = round(count / total * 100, 1) if total else 0
        result.append({'month': month, 'ip': ip, 'share_pct': share_pct, 'count': count})
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py::test_export_ip_share_trend -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add phase2_overseas/export_json.py phase2_overseas/tests/test_export_json.py
git commit -m "feat(export): add export_ip_share_trend — monthly IP share percentages"
```

---

### Task 3: Export cross-platform-index.json (TDD)

**Files:**
- Modify: `phase2_overseas/export_json.py`
- Modify: `phase2_overseas/tests/test_export_json.py`

- [ ] **Step 1: Write failing test**

Add to `phase2_overseas/tests/test_export_json.py`:

```python
def test_export_cross_platform_index(test_db):
    from export_json import export_cross_platform_index
    result = export_cross_platform_index(test_db)
    assert isinstance(result, list)
    assert len(result) > 0
    first = result[0]
    assert 'month' in first
    assert 'platform' in first
    assert 'index' in first
    assert 'density' in first
    assert first['platform'] in ('TikTok', 'Instagram')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py::test_export_cross_platform_index -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement export_cross_platform_index**

Add to `phase2_overseas/export_json.py` before `write_all()`:

```python
def export_cross_platform_index(conn):
    """Export monthly comment density index (mean=100) for TikTok and Instagram."""
    result = []

    for platform, content_table, content_date_col, comment_table, comment_fk in [
        ('TikTok', 'tiktok_videos', 'create_time', 'tiktok_comments', 'video_id'),
        ('Instagram', 'instagram_posts', 'post_date', 'instagram_comments', 'shortcode'),
    ]:
        # Monthly content count
        if platform == 'TikTok':
            content_rows = conn.execute(f"SELECT {content_date_col} FROM {content_table}").fetchall()
            monthly_content = {}
            for (ts,) in content_rows:
                try:
                    from datetime import datetime as dt
                    d = dt.utcfromtimestamp(int(ts))
                    month = d.strftime('%Y-%m')
                except (ValueError, TypeError, OSError):
                    continue
                monthly_content[month] = monthly_content.get(month, 0) + 1
        else:
            content_rows = conn.execute(f"SELECT {content_date_col} FROM {content_table}").fetchall()
            monthly_content = {}
            for (date,) in content_rows:
                month = _month_key(date)
                if month:
                    monthly_content[month] = monthly_content.get(month, 0) + 1

        # Monthly comment count
        comment_rows = conn.execute(f"SELECT comment_date FROM {comment_table}").fetchall()
        monthly_comments = {}
        for (date,) in comment_rows:
            month = _month_key(date)
            if month:
                monthly_comments[month] = monthly_comments.get(month, 0) + 1

        # Calculate density per month
        months = sorted(set(list(monthly_content.keys()) + list(monthly_comments.keys())))
        densities = []
        for m in months:
            content = monthly_content.get(m, 0)
            comments = monthly_comments.get(m, 0)
            if content > 0:
                densities.append((m, comments / content))

        if not densities:
            continue

        # Mean density for normalization
        avg_density = sum(d for _, d in densities) / len(densities)
        if avg_density == 0:
            avg_density = 1

        # 3-month rolling average
        for i, (m, density) in enumerate(densities):
            window = [d for _, d in densities[max(0, i-2):i+1]]
            ma3 = sum(window) / len(window)
            index = round(ma3 / avg_density * 100, 1)
            result.append({
                'month': m,
                'platform': platform,
                'index': index,
                'density': round(density, 1),
            })

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py::test_export_cross_platform_index -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add phase2_overseas/export_json.py phase2_overseas/tests/test_export_json.py
git commit -m "feat(export): add export_cross_platform_index — dual-platform density index"
```

---

### Task 4: Export brand-vs-ugc.json and comment-quality.json (TDD)

**Files:**
- Modify: `phase2_overseas/export_json.py`
- Modify: `phase2_overseas/tests/test_export_json.py`

- [ ] **Step 1: Write failing tests**

Add to `phase2_overseas/tests/test_export_json.py`:

```python
def test_export_brand_vs_ugc(test_db):
    from export_json import export_brand_vs_ugc
    result = export_brand_vs_ugc(test_db)
    assert isinstance(result, dict)
    assert 'brand' in result
    assert 'ugc' in result
    for key in ['avg_views', 'avg_likes', 'avg_er_pct', 'avg_comments']:
        assert key in result['brand']
        assert key in result['ugc']


def test_export_comment_quality(test_db):
    from export_json import export_comment_quality
    result = export_comment_quality(test_db)
    assert isinstance(result, list)
    assert len(result) == 2
    platforms = {r['platform'] for r in result}
    assert platforms == {'TikTok', 'Instagram'}
    for r in result:
        assert 'high_pct' in r
        assert 'med_pct' in r
        assert 'low_pct' in r
        assert 'total' in r
        # Percentages should roughly sum to 100
        assert abs(r['high_pct'] + r['med_pct'] + r['low_pct'] - 100) < 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py::test_export_brand_vs_ugc tests/test_export_json.py::test_export_comment_quality -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement both functions**

Add to `phase2_overseas/export_json.py` before `write_all()`:

```python
def export_brand_vs_ugc(conn):
    """Export brand (popmartglobal) vs UGC comparison for TikTok."""
    rows = conn.execute(
        "SELECT author, views, likes, comments_count FROM tiktok_videos"
    ).fetchall()

    brand = {'views': [], 'likes': [], 'comments': [], 'er': []}
    ugc = {'views': [], 'likes': [], 'comments': [], 'er': []}

    for author, views, likes, comments in rows:
        views = int(views or 0)
        likes = int(likes or 0)
        comments = int(comments or 0)
        er = (likes + comments) / max(views, 1) * 100
        target = brand if author == 'popmartglobal' else ugc
        target['views'].append(views)
        target['likes'].append(likes)
        target['comments'].append(comments)
        target['er'].append(er)

    def avg(lst):
        return round(sum(lst) / max(len(lst), 1), 1)

    return {
        'brand': {
            'avg_views': avg(brand['views']),
            'avg_likes': avg(brand['likes']),
            'avg_er_pct': round(avg(brand['er']), 2),
            'avg_comments': avg(brand['comments']),
        },
        'ugc': {
            'avg_views': avg(ugc['views']),
            'avg_likes': avg(ugc['likes']),
            'avg_er_pct': round(avg(ugc['er']), 2),
            'avg_comments': avg(ugc['comments']),
        },
    }


def export_comment_quality(conn):
    """Export comment quality tiers (high/med/low by likes) for each platform."""
    result = []
    for platform, table in [('TikTok', 'tiktok_comments'), ('Instagram', 'instagram_comments')]:
        rows = conn.execute(f"SELECT likes FROM {table}").fetchall()
        total = len(rows)
        if total == 0:
            result.append({'platform': platform, 'high_pct': 0, 'med_pct': 0, 'low_pct': 0, 'total': 0})
            continue
        high = sum(1 for (l,) in rows if (int(l or 0)) >= 10)
        med = sum(1 for (l,) in rows if 3 <= (int(l or 0)) < 10)
        low = total - high - med
        result.append({
            'platform': platform,
            'high_pct': round(high / total * 100, 1),
            'med_pct': round(med / total * 100, 1),
            'low_pct': round(low / total * 100, 1),
            'total': total,
        })
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py::test_export_brand_vs_ugc tests/test_export_json.py::test_export_comment_quality -v`
Expected: PASS

- [ ] **Step 5: Update write_all() to include new exports**

In `phase2_overseas/export_json.py`, modify the `exports` dict in `write_all()`:

```python
def write_all(output_dir):
    """Export all JSON files to output_dir."""
    conn = sqlite3.connect(DB_PATH)
    os.makedirs(output_dir, exist_ok=True)

    exports = {
        'overview.json': export_overview(conn),
        'tiktok-videos.json': export_tiktok_videos(conn),
        'tiktok-trend.json': export_tiktok_trend(conn),
        'instagram-posts.json': export_instagram_posts(conn),
        'instagram-trend.json': export_instagram_trend(conn),
        'ip-share.json': export_ip_share(conn),
        'brand-trend.json': export_brand_trend(conn),
        'ip-share-trend.json': export_ip_share_trend(conn),
        'cross-platform-index.json': export_cross_platform_index(conn),
        'brand-vs-ugc.json': export_brand_vs_ugc(conn),
        'comment-quality.json': export_comment_quality(conn),
    }

    for filename, data in exports.items():
        path = os.path.join(output_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ {filename} ({len(json.dumps(data))} bytes)")

    conn.close()
    print(f"\n✅ All JSON exported to {output_dir}")
```

- [ ] **Step 6: Run all tests**

Run: `cd phase2_overseas && python -m pytest tests/test_export_json.py -v`
Expected: ALL PASS

- [ ] **Step 7: Run export to generate JSON files**

Run: `cd phase2_overseas && python -u export_json.py`
Expected: 11 JSON files exported to both `website/src/data/` and `website/public/data/`

- [ ] **Step 8: Commit**

```bash
git add phase2_overseas/export_json.py phase2_overseas/tests/test_export_json.py website/src/data/ website/public/data/
git commit -m "feat(export): add brand-vs-ugc + comment-quality exports, wire all 5 new exports into write_all"
```

---

### Task 5: BrandTrendChart.astro — 品牌热度走势

**Files:**
- Create: `website/src/components/BrandTrendChart.astro`

- [ ] **Step 1: Create component**

Create `website/src/components/BrandTrendChart.astro`:

```astro
---
import brandTrend from '../data/brand-trend.json';
const months = brandTrend.map((r: any) => r.month);
const comments = brandTrend.map((r: any) => r.comments);
const density = brandTrend.map((r: any) => r.density);
const chartData = JSON.stringify({ months, comments, density });
---
<section class="section">
  <div class="section-header">
    <h2>品牌热度走势</h2>
    <span class="en">Monthly Buzz Trend</span>
  </div>
  <div class="chart-container">
    <div id="brand-trend-chart" style="width:100%;height:400px;"></div>
  </div>
</section>

<script define:vars={{ chartData }}>
  import('https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.esm.min.js').then(echarts => {
    const data = JSON.parse(chartData);
    const chart = echarts.init(document.getElementById('brand-trend-chart'));
    const maxComments = Math.max(...data.comments);
    chart.setOption({
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: function(params) {
          let tip = params[0].axisValue + '<br/>';
          params.forEach(p => {
            const val = p.seriesName === '评论密度' ? p.value.toFixed(1) : p.value.toLocaleString();
            tip += p.marker + ' ' + p.seriesName + ': ' + val + '<br/>';
          });
          return tip;
        }
      },
      grid: { left: 50, right: 50, top: 30, bottom: 50 },
      xAxis: {
        type: 'category',
        data: data.months,
        axisLabel: {
          fontSize: 10,
          interval: data.months.length > 10 ? Math.floor(data.months.length / 8) : 0,
          rotate: 30
        }
      },
      yAxis: [
        { type: 'value', name: '评论量', nameTextStyle: { color: '#999', fontSize: 11 } },
        { type: 'value', name: '贴均评论', nameTextStyle: { color: '#E53935', fontSize: 11 },
          splitLine: { show: false } }
      ],
      series: [
        {
          name: '评论量', type: 'bar', yAxisIndex: 0,
          data: data.comments,
          itemStyle: {
            color: function(params) {
              var ratio = params.value / (maxComments || 1);
              return 'rgba(255,143,0,' + (0.3 + 0.7 * ratio) + ')';
            },
            borderRadius: [4, 4, 0, 0]
          },
          barMaxWidth: 28,
        },
        {
          name: '评论密度', type: 'line', yAxisIndex: 1,
          data: data.density,
          lineStyle: { color: '#E53935', width: 2.5 },
          itemStyle: { color: '#E53935', borderColor: '#E53935', borderWidth: 2 },
          symbol: 'circle', symbolSize: 7,
          smooth: true,
        }
      ]
    });
    window.addEventListener('resize', () => chart.resize());
  });
</script>

<style>
  .chart-container {
    background: var(--color-card); border-radius: 20px;
    padding: 32px; box-shadow: var(--shadow);
  }
</style>
```

- [ ] **Step 2: Verify build**

Run: `cd website && npm run build 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add website/src/components/BrandTrendChart.astro
git commit -m "feat(website): add BrandTrendChart — monthly comment volume + density dual-axis"
```

---

### Task 6: IpShareTrendChart.astro — IP评论份额

**Files:**
- Create: `website/src/components/IpShareTrendChart.astro`

- [ ] **Step 1: Create component**

Create `website/src/components/IpShareTrendChart.astro`:

```astro
---
import ipShareTrend from '../data/ip-share-trend.json';

const IP_COLORS: Record<string, string> = {
  Labubu: '#FF6F00', Dimoo: '#1976D2', Molly: '#E91E63',
  Skullpanda: '#7B1FA2', 'Pop Mart': '#D32F2F', Zsiga: '#00897B',
};
const IP_IMAGES: Record<string, string> = {
  Labubu: '/popmart/characters/labubu.png', Dimoo: '/popmart/characters/dimoo.png',
  Molly: '/popmart/characters/molly.png', Skullpanda: '/popmart/characters/skullpanda.png',
};

const months = [...new Set(ipShareTrend.map((r: any) => r.month))].sort();
const ips = [...new Set(ipShareTrend.map((r: any) => r.ip))];

const series = ips.map(ip => ({
  name: ip,
  type: 'line',
  stack: 'total',
  areaStyle: { opacity: 0.75 },
  lineStyle: { width: 0.5, color: '#fff' },
  itemStyle: { color: IP_COLORS[ip] || '#999' },
  emphasis: { focus: 'series' },
  data: months.map(m => {
    const match = ipShareTrend.find((r: any) => r.month === m && r.ip === ip);
    return match ? match.share_pct : 0;
  }),
}));

const chartData = JSON.stringify({ months, series });
---
<section class="section">
  <div class="section-header">
    <h2>IP 评论份额趋势</h2>
    <span class="en">IP Share of Voice Trend</span>
  </div>
  <div class="chart-container">
    <div id="ip-share-trend-chart" style="width:100%;height:400px;"></div>
    <div class="chart-legend">
      {ips.map(ip => (
        <div class="legend-item">
          {IP_IMAGES[ip] && (
            <div class="legend-avatar">
              <img src={IP_IMAGES[ip]} alt={ip} width="36" height="36" loading="lazy">
            </div>
          )}
          <div class="legend-color" style={'background:' + (IP_COLORS[ip] || '#999')}></div>
          {ip}
        </div>
      ))}
    </div>
  </div>
</section>

<script define:vars={{ chartData }}>
  import('https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.esm.min.js').then(echarts => {
    const data = JSON.parse(chartData);
    const chart = echarts.init(document.getElementById('ip-share-trend-chart'));
    chart.setOption({
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: function(params) {
          let tip = params[0].axisValue + '<br/>';
          params.forEach(p => {
            tip += p.marker + ' ' + p.seriesName + ': ' + p.value.toFixed(1) + '%<br/>';
          });
          return tip;
        }
      },
      grid: { left: 50, right: 20, top: 20, bottom: 50 },
      xAxis: {
        type: 'category',
        data: data.months,
        boundaryGap: false,
        axisLabel: {
          fontSize: 10,
          interval: data.months.length > 10 ? Math.floor(data.months.length / 8) : 0,
          rotate: 30
        }
      },
      yAxis: {
        type: 'value', max: 100,
        axisLabel: { formatter: '{value}%' }
      },
      series: data.series,
    });
    window.addEventListener('resize', () => chart.resize());
  });
</script>

<style>
  .chart-container {
    background: var(--color-card); border-radius: 20px;
    padding: 32px; box-shadow: var(--shadow);
  }
  .chart-legend {
    display: flex; justify-content: center; gap: 28px;
    margin-top: 20px; flex-wrap: wrap;
  }
  .legend-item {
    display: flex; align-items: center; gap: 10px;
    font-size: 14px; font-weight: 600; color: #444;
  }
  .legend-avatar {
    width: 36px; height: 36px; border-radius: 50%;
    overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.12);
    border: 2px solid white; flex-shrink: 0; background: #fff;
  }
  .legend-avatar img { width: 100%; height: 100%; object-fit: cover; transform: scale(1.3); }
  .legend-color { width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; }
</style>
```

- [ ] **Step 2: Verify build**

Run: `cd website && npm run build 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add website/src/components/IpShareTrendChart.astro
git commit -m "feat(website): add IpShareTrendChart — stacked area IP share over time"
```

---

### Task 7: CrossPlatformChart.astro — 双平台热度指数

**Files:**
- Create: `website/src/components/CrossPlatformChart.astro`

- [ ] **Step 1: Create component**

Create `website/src/components/CrossPlatformChart.astro`:

```astro
---
import crossPlatform from '../data/cross-platform-index.json';

const tiktok = crossPlatform.filter((r: any) => r.platform === 'TikTok');
const instagram = crossPlatform.filter((r: any) => r.platform === 'Instagram');
const allMonths = [...new Set(crossPlatform.map((r: any) => r.month))].sort();

const chartData = JSON.stringify({
  months: allMonths,
  tiktok: allMonths.map(m => { const r = tiktok.find((t: any) => t.month === m); return r ? r.index : null; }),
  instagram: allMonths.map(m => { const r = instagram.find((t: any) => t.month === m); return r ? r.index : null; }),
});
---
<section class="section">
  <div class="section-header">
    <h2>双平台热度指数</h2>
    <span class="en">Cross-Platform Buzz Index</span>
  </div>
  <div class="chart-container">
    <div id="cross-platform-chart" style="width:100%;height:400px;"></div>
  </div>
</section>

<script define:vars={{ chartData }}>
  import('https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.esm.min.js').then(echarts => {
    const data = JSON.parse(chartData);
    const chart = echarts.init(document.getElementById('cross-platform-chart'));
    chart.setOption({
      tooltip: {
        trigger: 'axis',
        formatter: function(params) {
          let tip = params[0].axisValue + '<br/>';
          params.forEach(p => {
            if (p.value != null) tip += p.marker + ' ' + p.seriesName + ': ' + p.value.toFixed(1) + '<br/>';
          });
          return tip;
        }
      },
      grid: { left: 50, right: 20, top: 30, bottom: 50 },
      xAxis: {
        type: 'category', data: data.months,
        axisLabel: {
          fontSize: 10,
          interval: data.months.length > 10 ? Math.floor(data.months.length / 8) : 0,
          rotate: 30
        }
      },
      yAxis: {
        type: 'value', name: '热度指数',
        nameTextStyle: { color: '#999', fontSize: 11 }
      },
      series: [
        {
          name: 'TikTok', type: 'line', data: data.tiktok, connectNulls: true,
          lineStyle: { color: '#1a1a1a', width: 2.5 },
          itemStyle: { color: '#1a1a1a', borderColor: '#1a1a1a', borderWidth: 2 },
          symbol: 'circle', symbolSize: 7, smooth: true,
        },
        {
          name: 'Instagram', type: 'line', data: data.instagram, connectNulls: true,
          lineStyle: { color: '#E1306C', width: 2.5 },
          itemStyle: { color: '#E1306C', borderColor: '#E1306C', borderWidth: 2 },
          symbol: 'circle', symbolSize: 7, smooth: true,
        },
        {
          name: '均值基准', type: 'line',
          data: data.months.map(() => 100),
          lineStyle: { color: '#ccc', width: 1, type: 'dashed' },
          symbol: 'none', silent: true,
          label: { show: false },
        }
      ],
      legend: {
        data: ['TikTok', 'Instagram'],
        bottom: 5, textStyle: { fontSize: 12 }
      }
    });
    window.addEventListener('resize', () => chart.resize());
  });
</script>

<style>
  .chart-container {
    background: var(--color-card); border-radius: 20px;
    padding: 32px; box-shadow: var(--shadow);
  }
</style>
```

- [ ] **Step 2: Verify build**

Run: `cd website && npm run build 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add website/src/components/CrossPlatformChart.astro
git commit -m "feat(website): add CrossPlatformChart — dual-platform buzz index with baseline"
```

---

### Task 8: BrandVsUgcChart.astro + CommentQualityChart.astro

**Files:**
- Create: `website/src/components/BrandVsUgcChart.astro`
- Create: `website/src/components/CommentQualityChart.astro`

- [ ] **Step 1: Create BrandVsUgcChart**

Create `website/src/components/BrandVsUgcChart.astro`:

```astro
---
import brandVsUgc from '../data/brand-vs-ugc.json';
const chartData = JSON.stringify(brandVsUgc);
---
<section class="section">
  <div class="section-header">
    <h2>品牌 vs UGC</h2>
    <span class="en">Brand vs User-Generated Content</span>
  </div>
  <div class="chart-container">
    <div id="brand-ugc-chart" style="width:100%;height:400px;"></div>
  </div>
</section>

<script define:vars={{ chartData }}>
  import('https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.esm.min.js').then(echarts => {
    const data = JSON.parse(chartData);
    const b = data.brand, u = data.ugc;
    const dims = ['平均播放量', '平均点赞', '平均参与率%', '每视频均评论'];
    const brandVals = [b.avg_views, b.avg_likes, b.avg_er_pct, b.avg_comments];
    const ugcVals = [u.avg_views, u.avg_likes, u.avg_er_pct, u.avg_comments];
    // Normalize to UGC = 100
    const brandNorm = brandVals.map((v, i) => Math.round(v / (ugcVals[i] || 1) * 100));
    const ugcNorm = ugcVals.map(() => 100);

    const chart = echarts.init(document.getElementById('brand-ugc-chart'));
    chart.setOption({
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function(params) {
          let tip = params[0].axisValue + '<br/>';
          params.forEach((p, i) => {
            const raw = p.seriesName === '品牌官号' ? brandVals[p.dataIndex] : ugcVals[p.dataIndex];
            const fmt = p.dataIndex === 2 ? raw.toFixed(1) + '%' : raw.toLocaleString();
            tip += p.marker + ' ' + p.seriesName + ': ' + fmt + ' (' + p.value + ')<br/>';
          });
          return tip;
        }
      },
      grid: { left: 50, right: 20, top: 30, bottom: 40 },
      xAxis: { type: 'category', data: dims, axisLabel: { fontSize: 11 } },
      yAxis: {
        type: 'value', name: '相对水平 (UGC=100)',
        nameTextStyle: { color: '#999', fontSize: 11 }
      },
      legend: { data: ['品牌官号', '用户UGC'], bottom: 5 },
      series: [
        {
          name: '品牌官号', type: 'bar', data: brandNorm, barGap: '10%',
          itemStyle: { color: '#E53935', borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 36,
          label: { show: true, position: 'top', fontSize: 10,
            formatter: function(p) { var r = brandVals[p.dataIndex]; return p.dataIndex === 2 ? r.toFixed(1) + '%' : (r > 999 ? (r/1000).toFixed(0) + 'K' : r); }
          }
        },
        {
          name: '用户UGC', type: 'bar', data: ugcNorm,
          itemStyle: { color: '#333', borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 36,
          label: { show: true, position: 'top', fontSize: 10,
            formatter: function(p) { var r = ugcVals[p.dataIndex]; return p.dataIndex === 2 ? r.toFixed(1) + '%' : (r > 999 ? (r/1000).toFixed(0) + 'K' : r); }
          }
        }
      ]
    });
    window.addEventListener('resize', () => chart.resize());
  });
</script>

<style>
  .chart-container {
    background: var(--color-card); border-radius: 20px;
    padding: 32px; box-shadow: var(--shadow);
  }
</style>
```

- [ ] **Step 2: Create CommentQualityChart**

Create `website/src/components/CommentQualityChart.astro`:

```astro
---
import commentQuality from '../data/comment-quality.json';
const chartData = JSON.stringify(commentQuality);
---
<section class="section">
  <div class="section-header">
    <h2>评论质量分层</h2>
    <span class="en">Comment Quality Tiers</span>
  </div>
  <div class="chart-container">
    <div id="comment-quality-chart" style="width:100%;height:360px;"></div>
  </div>
</section>

<script define:vars={{ chartData }}>
  import('https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.esm.min.js').then(echarts => {
    const data = JSON.parse(chartData);
    const platforms = data.map(d => d.platform);
    const chart = echarts.init(document.getElementById('comment-quality-chart'));
    chart.setOption({
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function(params) {
          const idx = params[0].dataIndex;
          const d = data[idx];
          return d.platform + ' (' + d.total.toLocaleString() + ' 条评论)<br/>' +
            params.map(p => p.marker + ' ' + p.seriesName + ': ' + p.value.toFixed(1) + '%').join('<br/>');
        }
      },
      grid: { left: 50, right: 20, top: 30, bottom: 40 },
      xAxis: { type: 'category', data: platforms, axisLabel: { fontSize: 13 } },
      yAxis: {
        type: 'value', max: 100,
        axisLabel: { formatter: '{value}%' }
      },
      legend: { bottom: 5 },
      series: [
        {
          name: '高互动 ≥10赞', type: 'bar', stack: 'total',
          data: data.map(d => d.high_pct),
          itemStyle: { color: '#4CAF50' },
          barMaxWidth: 80,
          label: { show: true, position: 'inside', fontSize: 11, fontWeight: 600,
            formatter: p => p.value > 5 ? p.value.toFixed(0) + '%' : '' }
        },
        {
          name: '中互动 3-9赞', type: 'bar', stack: 'total',
          data: data.map(d => d.med_pct),
          itemStyle: { color: '#FFC107' },
          label: { show: true, position: 'inside', fontSize: 11, fontWeight: 600,
            formatter: p => p.value > 5 ? p.value.toFixed(0) + '%' : '' }
        },
        {
          name: '低互动 <3赞', type: 'bar', stack: 'total',
          data: data.map(d => d.low_pct),
          itemStyle: { color: '#E0E0E0' },
          label: { show: true, position: 'inside', fontSize: 11, fontWeight: 600, color: '#666',
            formatter: p => p.value > 5 ? p.value.toFixed(0) + '%' : '' }
        }
      ]
    });
    window.addEventListener('resize', () => chart.resize());
  });
</script>

<style>
  .chart-container {
    background: var(--color-card); border-radius: 20px;
    padding: 32px; box-shadow: var(--shadow);
  }
</style>
```

- [ ] **Step 3: Verify build**

Run: `cd website && npm run build 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add website/src/components/BrandVsUgcChart.astro website/src/components/CommentQualityChart.astro
git commit -m "feat(website): add BrandVsUgcChart + CommentQualityChart"
```

---

### Task 9: Wire up index.astro — replace TrendChart with 5 new charts

**Files:**
- Modify: `website/src/pages/index.astro`
- Delete: `website/src/components/TrendChart.astro`

- [ ] **Step 1: Update index.astro**

Replace `website/src/pages/index.astro` with:

```astro
---
// website/src/pages/index.astro
import Base from '../layouts/Base.astro';
import Hero from '../components/Hero.astro';
import StatCards from '../components/StatCards.astro';
import BrandTrendChart from '../components/BrandTrendChart.astro';
import IpShareTrendChart from '../components/IpShareTrendChart.astro';
import CrossPlatformChart from '../components/CrossPlatformChart.astro';
import BrandVsUgcChart from '../components/BrandVsUgcChart.astro';
import CommentQualityChart from '../components/CommentQualityChart.astro';
import IpShareCards from '../components/IpShareCards.astro';
import LatestPosts from '../components/LatestPosts.astro';
---
<Base title="泡泡玛特.md — 海外另类数据追踪">
  <Hero />
  <StatCards />
  <BrandTrendChart />
  <IpShareTrendChart />
  <CrossPlatformChart />
  <BrandVsUgcChart />
  <CommentQualityChart />
  <IpShareCards />
  <LatestPosts />
</Base>
```

- [ ] **Step 2: Delete old TrendChart**

Run: `rm website/src/components/TrendChart.astro`

- [ ] **Step 3: Verify build**

Run: `cd website && npm run build 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add website/src/pages/index.astro
git rm website/src/components/TrendChart.astro
git commit -m "feat(website): replace single TrendChart with 5 monthly ECharts on homepage"
```

---

### Task 10: Mobile responsive CSS

**Files:**
- Modify: `website/src/styles/global.css`
- Modify: `website/src/layouts/Base.astro`
- Modify: `website/src/components/Hero.astro`
- Modify: `website/src/components/StatCards.astro`
- Modify: `website/src/components/IpShareCards.astro`
- Modify: `website/src/components/LatestPosts.astro`

- [ ] **Step 1: Add global mobile breakpoint**

Append to `website/src/styles/global.css`:

```css
@media (max-width: 768px) {
  .section { margin: 20px auto; padding: 0 12px; }
  .section-header h2 { font-size: 18px; }
  .section-header .en { font-size: 11px; }
}
```

- [ ] **Step 2: Mobile nav in Base.astro**

Append inside `<style>` of `website/src/layouts/Base.astro`:

```css
@media (max-width: 768px) {
  nav { padding: 0 16px; height: 52px; }
  .nav-logo a { font-size: 16px; letter-spacing: 1px; }
  .nav-links { gap: 14px; }
  .nav-links a { font-size: 12px; }
  .llms-link { display: none; }
  footer { flex-direction: column; gap: 12px; padding: 24px 16px; text-align: center; }
  .footer-links { flex-wrap: wrap; justify-content: center; }
  main { margin-top: 52px; }
}
```

- [ ] **Step 3: Mobile Hero**

Append inside `<style>` of `website/src/components/Hero.astro`:

```css
@media (max-width: 768px) {
  .hero { height: 320px; }
  .hero-chars { display: none; }
  .hero h1 { font-size: 36px; }
  .hero-sub { font-size: 14px; margin-bottom: 16px; }
  .hero-update { font-size: 11px; }
  .hero-badge { font-size: 10px; padding: 4px 12px; margin-bottom: 16px; }
}
```

- [ ] **Step 4: Mobile StatCards**

Append inside `<style>` of `website/src/components/StatCards.astro`:

```css
@media (max-width: 768px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: -30px; padding: 0 12px; }
  .stat-card { padding: 16px; }
  .stat-value { font-size: 24px; }
  .stat-label { font-size: 11px; }
  .stat-icon { width: 32px; height: 32px; font-size: 16px; margin-bottom: 10px; }
}
```

- [ ] **Step 5: Mobile IpShareCards**

Append inside `<style>` of `website/src/components/IpShareCards.astro`:

```css
@media (max-width: 768px) {
  .ip-grid {
    grid-template-columns: repeat(3, 1fr); gap: 10px;
  }
  .ip-card { padding: 16px 10px; }
  .ip-avatar { width: 52px; height: 52px; margin-bottom: 8px; }
  .ip-card h4 { font-size: 12px; }
  .ip-share { font-size: 20px; }
  .ip-label { font-size: 9px; }
}
```

- [ ] **Step 6: Mobile LatestPosts**

Append inside `<style>` of `website/src/components/LatestPosts.astro`:

```css
@media (max-width: 768px) {
  .posts-grid { grid-template-columns: 1fr; }
  .post-card { padding: 14px 16px; }
  .post-platform { width: 36px; height: 36px; font-size: 14px; border-radius: 10px; }
  .post-meta h4 { font-size: 13px; }
}
```

- [ ] **Step 7: Mobile chart heights**

Each of the 5 new chart components already has `.chart-container` styled. Add this to each chart component's `<style>` block (BrandTrendChart, IpShareTrendChart, CrossPlatformChart, BrandVsUgcChart, CommentQualityChart):

```css
@media (max-width: 768px) {
  .chart-container { padding: 16px; border-radius: 14px; }
}
```

And update each chart `<div>` height via inline style: change `height:400px` to `height:min(400px, 55vw)` in each chart component. Alternatively, keep 400px and let ECharts auto-resize via CSS:

For each chart component, wrap the chart div in a responsive container. The simplest approach: in each chart component, change the chart div style from `style="width:100%;height:400px;"` to `class="chart-area"` and add to `<style>`:

```css
.chart-area { width: 100%; height: 400px; }
@media (max-width: 768px) {
  .chart-area { height: 260px; }
  .chart-container { padding: 16px; border-radius: 14px; }
}
```

Apply this to all 5 chart components by changing `style="width:100%;height:400px;"` to `class="chart-area"`.

Also add mobile for chart legend in IpShareTrendChart:

```css
@media (max-width: 768px) {
  .chart-legend { gap: 12px; margin-top: 12px; }
  .legend-item { font-size: 11px; gap: 6px; }
  .legend-avatar { width: 28px; height: 28px; }
}
```

- [ ] **Step 8: Verify build**

Run: `cd website && npm run build 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 9: Commit**

```bash
git add website/src/styles/global.css website/src/layouts/Base.astro website/src/components/Hero.astro website/src/components/StatCards.astro website/src/components/IpShareCards.astro website/src/components/LatestPosts.astro website/src/components/BrandTrendChart.astro website/src/components/IpShareTrendChart.astro website/src/components/CrossPlatformChart.astro website/src/components/BrandVsUgcChart.astro website/src/components/CommentQualityChart.astro
git commit -m "feat(website): add mobile responsive CSS for all components and charts"
```

---

### Task 11: Update daily_update.bat

**Files:**
- Modify: `scripts/daily_update.bat`

- [ ] **Step 1: Rewrite daily_update.bat**

Replace `scripts/daily_update.bat` with:

```batch
@echo off
REM scripts/daily_update.bat — Launch Claude Code for daily data update
REM Schedule via Windows Task Scheduler at 08:00 daily

echo [%date% %time%] Launching Claude Code for daily update >> "%~dp0daily_update.log"

cd /d "C:\Users\lxxxxxx\Desktop\个人项目\popmart"

REM Launch Claude Code with update prompt
claude -p "执行每日海外数据更新：1) cd phase2_overseas 2) python -u tiktok_browser.py 采集新视频和评论 3) python -u instagram_browser.py 检查新帖子 4) python -u export_json.py 导出网站数据 5) git add website/src/data/ website/public/data/ && git commit -m 'data: daily update' && git push origin main。每步完成后报告结果，如遇到登录态过期等问题请记录并跳过。" --dangerously-skip-permissions

echo [%date% %time%] Claude Code session finished >> "%~dp0daily_update.log"
```

- [ ] **Step 2: Commit**

```bash
git add scripts/daily_update.bat
git commit -m "feat(scripts): rewrite daily_update.bat to launch Claude Code for full pipeline"
```

---

### Task 12: Push and visual verification

**Files:** None (deployment task)

- [ ] **Step 1: Push to main**

Run: `git push origin main`

- [ ] **Step 2: Wait for GitHub Actions deployment**

Run: `gh run list --limit 1 --workflow "Deploy Website"` and wait for success.

- [ ] **Step 3: Hard-reload and verify in browser**

Navigate to `https://lxistired.github.io/popmart/`, hard-reload (Ctrl+Shift+R), and visually verify:
- All 5 charts render with data
- IP avatars in chart legends load
- Tooltips work on hover
- Mobile view: use browser DevTools (Ctrl+Shift+M) to toggle responsive mode at 375px width
- Verify 2-col stat cards, hidden hero characters, shorter charts, simplified nav

- [ ] **Step 4: Iterate on visual issues**

If any chart looks broken or mobile layout needs adjustment, fix and push again.
