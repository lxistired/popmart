# Anti-Detection Browser & Scraping Tool Research (2026-03-28)

## Context

Current setup uses **Playwright + playwright-stealth** for time-series data collection (ts_pw.py) and **undetected-chromedriver** for daily snapshots (overseas_scraper.py). The core problem: Amazon and TikTok block Playwright-launched browsers. Instagram works but comments require login state. This document evaluates all viable alternatives.

---

## 1. Lightpanda

**What it is:** Open-source headless browser written in Zig + V8, designed for AI/automation. Claims 11x faster execution and 9x less memory vs Chrome headless. Supports CDP (Chrome DevTools Protocol), so it works with Playwright/Puppeteer.

**Anti-detection verdict: NOT suitable.**
- Lightpanda is optimized for speed and resource efficiency, NOT for anti-detection
- It has a distinct fingerprint (custom user-agent, non-standard JS execution patterns) that anti-bot systems like DataDome already document how to detect
- No login state / cookie persistence mechanism designed for scraping use cases
- Still in early development; not a drop-in replacement for real Chrome

**Use case:** LLM agent web browsing, mass page crawling where anti-bot is not a concern. Not relevant for this project.

| Criterion | Rating |
|-----------|--------|
| Anti-bot bypass | Very Poor |
| Python support | Via CDP/Playwright (indirect) |
| Login state | No native support |
| Cost | Free (open-source) |
| Maintenance | Active but early-stage |

---

## 2. Camoufox

**What it is:** Anti-detect browser built on a *modified Firefox* codebase. Fingerprint spoofing happens at the C++ engine level (not JS patches), making it fundamentally harder to detect than JS-only stealth plugins. Ships as a Python package with Playwright API compatibility.

**Anti-detection verdict: PROMISING but UNSTABLE in 2026.**
- Achieves 0% detection on CreepJS and BrowserScan when working correctly
- C++-level fingerprinting is theoretically superior to any JS-based stealth
- ~92% success rate with residential proxies (early sessions)
- **CRITICAL ISSUE (March 2026):** The maintainer had a year-long absence; the base Firefox version is outdated, and new fingerprint inconsistencies have appeared. Latest releases are "highly experimental" and "not suitable for production"
- Python 3.13 compatibility issues exist (our project uses Python 3.13)
- Playwright API compatibility has known bugs with recent Playwright versions

**Recommendation:** Monitor for stability. If the maintainer catches up (the project shows renewed activity in Feb-March 2026), this becomes the #1 recommendation for browser-based scraping. Today it is too risky for production.

| Criterion | Rating |
|-----------|--------|
| Anti-bot bypass | Excellent (when stable) / Poor (current unstable builds) |
| Python support | Native Python package, Playwright API |
| Login state | Yes (persistent context) |
| Cost | Free (open-source) |
| Maintenance | Recovering from hiatus, experimental |

---

## 3. undetected-playwright

**What it is:** A Python library extending standard Playwright with stealth patches. Multiple packages exist: `undetected-playwright-python`, `playwright-stealth`, `playwright-extra`.

**Anti-detection verdict: MARGINAL.**
- CreepJS Trust Score ~90.5% (A-) in controlled tests
- Only bypasses "simple detection" per official playwright-stealth docs
- **Cannot defeat enterprise anti-bot** (DataDome, Akamai, advanced Cloudflare)
- Modern anti-bot systems detect CDP usage itself, regardless of stealth patches
- This is essentially what we already use (playwright-stealth) -- upgrading to undetected-playwright-python provides only incremental improvement
- Amazon and TikTok use advanced detection that goes beyond what JS patches can address

**Recommendation:** Not worth switching to. We already use playwright-stealth; undetected-playwright is the same category of tool with marginal improvements.

| Criterion | Rating |
|-----------|--------|
| Anti-bot bypass | Poor-Fair (basic sites only) |
| Python support | Native |
| Login state | Yes (persistent context) |
| Cost | Free |
| Maintenance | Active |

---

## 4. Botright

**What it is:** Playwright-based framework with fingerprint spoofing (canvas, WebGL, audio context randomization) and built-in free AI CAPTCHA solvers (reCAPTCHA, hCaptcha).

**Anti-detection verdict: NOT VIABLE in 2026.**
- **Project is INACTIVE** -- maintenance has stopped
- Requires Python <3.9 (we use Python 3.13)
- Dependency issues with Python 3.11+
- Not updated to handle 2026 anti-bot techniques
- The free CAPTCHA solver was its main differentiator, but without maintenance it's unreliable

**Recommendation:** Do not use. Dead project with incompatible Python version requirements.

| Criterion | Rating |
|-----------|--------|
| Anti-bot bypass | Fair (when it worked) |
| Python support | Python <3.9 only |
| Login state | Yes |
| Cost | Free |
| Maintenance | INACTIVE |

---

## 5. Puppeteer Extra + Stealth Plugin

**What it is:** Node.js (not Python) browser automation framework with a mature stealth plugin ecosystem. The stealth plugin patches navigator.webdriver, spoofs WebGL vendor strings, and mimics human browser properties.

**Anti-detection verdict: SIMILAR to playwright-stealth, slightly more mature.**
- More community-tested than playwright-stealth (larger ecosystem)
- Still uses CDP underneath, so advanced anti-bot systems detect the automation protocol itself
- **Major drawback: Node.js only** -- integrating into our Python codebase requires subprocess calls or rewriting in JS
- Same fundamental limitation as playwright-stealth: JS-level patches cannot defeat C++-level or protocol-level detection

**Recommendation:** Not worth the language switch. If we were building from scratch in Node.js, slightly better than playwright-stealth, but the difference is marginal and both fail against Amazon/TikTok.

| Criterion | Rating |
|-----------|--------|
| Anti-bot bypass | Fair (same tier as playwright-stealth) |
| Python support | None (Node.js only) |
| Login state | Yes |
| Cost | Free |
| Maintenance | Active, mature community |

---

## 6. DrissionPage *** RECOMMENDED ***

**What it is:** Python library that controls Chromium browsers WITHOUT the WebDriver protocol. It communicates with the browser through a different mechanism (DevTools Protocol in a non-standard way), making it fundamentally harder to detect than Selenium/Playwright. Combines browser automation (like Selenium) with HTTP requests (like requests library) in one unified API.

**Anti-detection verdict: STRONG -- best free option for our use case.**
- Does NOT use WebDriver protocol, eliminating the #1 detection vector
- In documented tests, sites that blocked Selenium within seconds allowed DrissionPage to run for hours
- Controls real Chrome browser (not a modified/custom browser)
- Can use existing Chrome user profile with all cookies/login state
- Supports both "browser mode" (full rendering) and "packet mode" (fast HTTP requests)
- Active development, works with Python 3.13
- Can integrate with CapSolver for CAPTCHA challenges
- pip install: `pip install DrissionPage`

**Key advantages for our project:**
1. Uses real Chrome with real user profile -- login state persistence is native
2. No WebDriver flag to detect -- the biggest reason Playwright gets caught
3. Can switch between browser mode (for JS-heavy pages) and packet mode (for API calls)
4. Chinese developer community (extensive docs in Chinese, relevant for our team)

**Limitations:**
- Less documentation in English
- Smaller community than Playwright/Selenium
- Still needs proxies for IP-level blocking
- Won't bypass TLS fingerprinting or advanced behavioral analysis alone

| Criterion | Rating |
|-----------|--------|
| Anti-bot bypass | Good-Excellent |
| Python support | Native, first-class |
| Login state | Yes (real Chrome profile) |
| Cost | Free (open-source) |
| Maintenance | Active |

---

## 7. API-Based Approaches (Official / Unofficial)

### Amazon Reviews

- **Official API (PA-API 5.0):** Does NOT provide review text or individual review data. Only aggregate ratings. Useless for our time-series use case.
- **Key change (Feb 2025):** Amazon now requires login cookies to view more than 8 recent reviews. Any scraping solution needs authenticated sessions.
- **Recommendation:** DrissionPage with logged-in Chrome profile, or third-party API services.

### TikTok Comments

- **Official API:** Research API exists but requires academic/business approval, limited to certain endpoints, no bulk comment access.
- **TikTokApi (davidteather):** Unofficial Python wrapper, latest release March 17, 2026. Comments function exists but hardcoded to 20 per request. Requires proxies. Frequent EmptyResponseException errors due to detection. Still the best free unofficial option.
- **TikTok mobile API:** Certificate pinning makes mitmproxy interception very difficult in 2026. Not recommended.
- **Recommendation:** TikTokApi library with residential proxies, or Apify/third-party services.

### Instagram Comments

- **Official API (Instagram Graph API):** Only for business/creator accounts you own. Cannot read other accounts' comments.
- **instagrapi:** Python library wrapping Instagram's private (mobile app) API. Last API validation: May 2025. Supports comment reading via `media_comments()`. Requires Instagram login. Works but "more suited for testing/research than production."
- **GraphQL doc_ids:** Instagram changes these every 2-4 weeks, breaking custom scrapers constantly.
- **Recommendation:** instagrapi is the best free option for Instagram comments. Pair with session management to avoid bans.

| Platform | Best Free Option | Best Paid Option | Reliability |
|----------|-----------------|-----------------|-------------|
| Amazon Reviews | DrissionPage + login | Oxylabs / ScrapingBee API | Medium |
| TikTok Comments | TikTokApi + proxies | Apify TikTok Comments Scraper | Low-Medium |
| Instagram Comments | instagrapi | Apify Instagram Scraper | Medium |

---

## 8. Third-Party Scraping Services/APIs

### Tier 1: Enterprise (best anti-bot bypass)

**Bright Data**
- Scraping Browser: full headless browser in the cloud with built-in proxy rotation and anti-bot bypass
- Amazon Reviews API: structured JSON output, handles CAPTCHA
- Pricing: starts at $1.50/1K requests, no monthly minimum
- GDPR/ISO 27001/SOC 2 certified
- Best for: high-volume, production-grade scraping

**Oxylabs**
- Web Scraper API: starts at $49/month for 17.5K results
- Amazon-specific scraper: parses more fields than competitors
- Best for: Amazon-heavy workloads

### Tier 2: Mid-range

**ScrapingBee**
- Amazon Scraper API: structured data extraction
- Headless browser rendering for JS-heavy sites
- Pricing: starts at $49/month
- Good for: small-to-mid volume social media scraping

**Apify**
- TikTok Comments Scraper: $5/1K results (pay-per-result)
- Amazon Reviews Scraper: structured output with ratings, dates, images
- Free tier: $5 credits/month (~1K TikTok comments)
- Starter: $39/month
- Best for: our use case -- low volume, specific endpoints

**Scrapfly**
- Anti-bot bypass with fingerprint rotation
- TLS fingerprint spoofing (critical for Instagram)
- Supports TikTok and Instagram

### Tier 3: Budget

**Scrape.do** -- $0.12/1K requests, 1K free/month
**ZenRows** -- Amazon/social media support, anti-bot included
**Decodo** -- Amazon review scraper with free trial

### Cost Estimate for Our Use Case

Our scraping volume is LOW (6 ASINs, 4 TikTok queries, 3 Instagram accounts, daily):
- Amazon: ~6 ASINs x 25 pages x 30 days = ~4,500 requests/month
- TikTok: ~4 queries x 50 videos x 30 days = ~6,000 requests/month
- Instagram: ~3 accounts x 20 posts x 30 days = ~1,800 requests/month
- **Total: ~12,300 requests/month**

| Provider | Monthly Cost (est.) | Notes |
|----------|-------------------|-------|
| Apify (pay-per-result) | ~$60-80/month | Best for TikTok comments specifically |
| Bright Data | ~$20-50/month | Most reliable, flexible |
| ScrapingBee | $49/month (fixed) | Good all-rounder |
| Scrape.do | ~$2/month + free tier | Budget option for Amazon only |

---

## 9. Browser Automation Alternatives

### Selenium + undetected-chromedriver (already in use)

We already use this for overseas_scraper.py. Key characteristics:
- Patches ChromeDriver to avoid detection
- Works well for Amazon product pages (daily snapshots work)
- Cannot easily share login state with Playwright
- **Could be extended** to handle Amazon reviews if we add login flow

### DrissionPage (detailed above in #6)

The strongest alternative. Key differentiator: no WebDriver protocol at all.

### SeleniumBase (UC Mode)

- Built on top of Selenium with an "Undetected Chrome" mode
- Also includes a "Playwright mode" with stealth
- Claims to bypass CAPTCHAs and bot-detection
- Python native, active maintenance
- Worth investigating as a middle ground

---

## 10. Mobile API Approach

**Concept:** Intercept the mobile app's API calls (which are often less protected than web) using mitmproxy or Charles Proxy.

**Status in 2026:**
- **TikTok:** Certificate pinning blocks mitmproxy. Documented failures. Would need Frida/objection to bypass SSL pinning on a rooted device. Very high technical complexity.
- **Amazon:** Mobile app also uses certificate pinning. Possible with rooted Android + Frida but extremely fragile.
- **Instagram:** instagrapi already reverse-engineers the mobile API, so this is redundant.

**Recommendation:** Not viable without significant reverse-engineering effort. Use instagrapi for Instagram (which already does this). For TikTok/Amazon, use other approaches.

---

## RECOMMENDATION MATRIX

### Priority 1: Quick wins (implement this week)

| Platform | Tool | Action |
|----------|------|--------|
| **Amazon Reviews** | **DrissionPage** | Replace ts_pw.py Amazon module. Use real Chrome profile with existing login. No WebDriver detection. |
| **Instagram Comments** | **instagrapi** | Replace ts_pw.py Instagram module. Direct private API access, no browser needed. Much faster. |

### Priority 2: Medium-term (if Priority 1 doesn't fully work)

| Platform | Tool | Action |
|----------|------|--------|
| **TikTok Comments** | **TikTokApi** + residential proxy | Try the unofficial API wrapper first. If EmptyResponseException, add proxy rotation. |
| **TikTok Comments** | **Apify TikTok Comments Scraper** | Fallback: $5/1K comments, pay-per-result. Free tier covers testing. |
| **Amazon Reviews** | **Apify Amazon Reviews Scraper** | Fallback if DrissionPage gets blocked. Structured output. |

### Priority 3: If all else fails

| Platform | Tool | Action |
|----------|------|--------|
| All platforms | **Bright Data Scraping Browser** | Cloud-hosted browser with built-in anti-bot. Most expensive but most reliable. |
| All platforms | **Camoufox** | Monitor for stable release. When Python 3.13 support lands, evaluate. |

---

## IMPLEMENTATION PLAN

### Step 1: Install DrissionPage + instagrapi

```bash
pip install DrissionPage instagrapi TikTokApi
```

### Step 2: Amazon Reviews via DrissionPage

Replace the `scrape_amazon_reviews()` function in ts_pw.py:
- DrissionPage can attach to an already-running Chrome or launch Chrome with a real user profile
- Navigate to review pages, extract review dates/text/ratings
- No WebDriver flag = significantly lower detection rate
- Can switch to "packet mode" for faster data extraction after initial page load

Key API pattern:
```python
from DrissionPage import ChromiumPage

page = ChromiumPage()  # Connects to running Chrome or launches new
page.get(f'https://www.amazon.com/product-reviews/{asin}?sortBy=recent')
reviews = page.eles('css:[data-hook="review"]')
for review in reviews:
    date_raw = review.ele('css:[data-hook="review-date"]').text
    title = review.ele('css:[data-hook="review-title"]').text
    # ... extract and save to DB
```

### Step 3: Instagram Comments via instagrapi

Replace the Instagram module in ts_pw.py entirely:
```python
from instagrapi import Client

cl = Client()
cl.login('username', 'password')  # Or load session
media_id = cl.media_pk_from_url('https://www.instagram.com/p/XXXXX/')
comments = cl.media_comments(media_id, amount=100)
for comment in comments:
    # comment.text, comment.created_at_utc, comment.user.username, comment.pk
    # ... save to DB
```

### Step 4: TikTok Comments via TikTokApi

```python
from TikTokApi import TikTokApi

async with TikTokApi() as api:
    await api.create_sessions(num_sessions=1, sleep_after=3)
    video = api.video(id='VIDEO_ID')
    async for comment in video.comments(count=100):
        # comment.text, comment.create_time, comment.author.username
        # ... save to DB
```

If this fails due to detection, fall back to Apify:
```python
from apify_client import ApifyClient
client = ApifyClient("YOUR_API_TOKEN")
run = client.actor("clockworks/tiktok-comments-scraper").call(
    run_input={"postURLs": ["https://www.tiktok.com/@user/video/ID"]}
)
for item in client.dataset(run["defaultDatasetId"]).iterate_items():
    # item['text'], item['createTime'], item['user']['nickname']
```

---

## SUMMARY TABLE

| Tool | Anti-Bot | Python | Login State | Cost | Status | Verdict |
|------|----------|--------|-------------|------|--------|---------|
| Lightpanda | Very Poor | Indirect | No | Free | Early | SKIP |
| Camoufox | Excellent* | Native | Yes | Free | Unstable | MONITOR |
| undetected-playwright | Poor-Fair | Native | Yes | Free | Active | SKIP (already using equivalent) |
| Botright | Fair | Py<3.9 | Yes | Free | DEAD | SKIP |
| Puppeteer+Stealth | Fair | No (JS) | Yes | Free | Active | SKIP (wrong language) |
| **DrissionPage** | **Good-Excellent** | **Native** | **Yes** | **Free** | **Active** | **USE for Amazon** |
| **instagrapi** | **N/A (API)** | **Native** | **Yes** | **Free** | **Active** | **USE for Instagram** |
| **TikTokApi** | **Fair** | **Native** | **N/A** | **Free** | **Active** | **TRY for TikTok** |
| Apify | Excellent | Native | N/A | $5/1K | Active | FALLBACK (paid) |
| Bright Data | Excellent | Native | Yes | $$$ | Active | LAST RESORT |
| SeleniumBase UC | Good | Native | Yes | Free | Active | ALTERNATIVE to DrissionPage |

*Camoufox "Excellent" rating is for when it was stable; current builds are experimental.

---

## KEY INSIGHT

The fundamental problem is not which browser we use -- it's that **Playwright and Selenium both use WebDriver/CDP protocols that anti-bot systems detect at the protocol level**. The solution is either:

1. **Avoid the protocol entirely** (DrissionPage, instagrapi private API, TikTokApi)
2. **Modify the browser engine itself** (Camoufox -- when stable)
3. **Let someone else handle it** (Apify, Bright Data, Oxylabs)

Trying to patch Playwright with stealth plugins is fundamentally limited because the detection happens below the JS layer.
