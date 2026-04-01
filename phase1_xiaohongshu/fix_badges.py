#!/usr/bin/env python3
"""
Replace emoji-based badges with CSS letter-initial avatars in popmart_article_v2.html.

Three types of replacements:
1. IP badges: emoji + name -> circular letter avatar + name
2. Data callout icons: emoji -> colored circle with character
3. Section h2 headers: emoji prefix -> colored bar prefix
4. Chart headers: remove 📊 prefix emoji from chart title bars
"""

import re

INPUT_FILE = r"C:\Users\lxxxxxx\Desktop\个人项目\popmart\popmart_article_v2.html"
OUTPUT_FILE = INPUT_FILE  # overwrite in place

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    html = f.read()

original_len = len(html)

# ===========================================================================
# 1. IP BADGES — replace emoji with CSS circular letter avatar
# ===========================================================================
# Pattern: <span style="display:inline-block; background:#COLOR; color:white; padding:1px 8px; border-radius:10px; font-size:13px;">EMOJI NAME</span>

ip_badge_map = {
    "🎪 泡泡玛特": ("泡", "#D32F2F", "泡泡玛特"),   # also matches #E53935 variant
    "🐰 Labubu":   ("L",  "#FF8F00", "Labubu"),
    "🌊 Dimoo":    ("D",  "#1E88E5", "Dimoo"),
    "👧 Molly":    ("M",  "#EC407A", "Molly"),
    "💀 Skullpanda": ("S", "#8E24AA", "Skullpanda"),
}

badge_count = 0
for emoji_text, (letter, new_bg, name) in ip_badge_map.items():
    # Match the full span with any background color
    # The pattern: <span style="display:inline-block; background:#XXXXXX; color:white; padding:1px 8px; border-radius:10px; font-size:13px;">EMOJI_TEXT</span>
    pattern = (
        r'<span\s+style="display:inline-block;\s*background:#[A-Fa-f0-9]+;\s*color:white;\s*'
        r'padding:1px 8px;\s*border-radius:10px;\s*font-size:13px;">'
        + re.escape(emoji_text)
        + r'</span>'
    )

    avatar_span = (
        f'<span style="display:inline-block; width:18px; height:18px; border-radius:50%; '
        f'background:rgba(255,255,255,0.3); text-align:center; line-height:18px; font-size:11px; '
        f'margin-right:4px; vertical-align:middle;">{letter}</span>'
    )

    replacement = (
        f'<span style="display:inline-block; background:{new_bg}; color:white; padding:2px 10px; '
        f'border-radius:12px; font-size:13px; font-weight:600; vertical-align:middle; margin:0 2px;">'
        f'{avatar_span}{name}</span>'
    )

    html, n = re.subn(pattern, replacement, html)
    badge_count += n
    print(f"  IP badge '{emoji_text}': {n} replacements")

print(f"Total IP badge replacements: {badge_count}")

# ===========================================================================
# 2. DATA CALLOUT ICONS — replace emoji with colored circle + character
# ===========================================================================
callout_map = {
    "📝": ("帖", "#E53935", "14px"),
    "💬": ("评", "#FF8F00", "14px"),
    "🎭": ("IP", "#1E88E5", "11px"),
    "📍": ("城", "#EC407A", "14px"),
}

callout_count = 0
for emoji, (char, bg, fsize) in callout_map.items():
    # Pattern: <div style="font-size:12px; margin-bottom:4px;">EMOJI</div>
    pattern = (
        r'<div\s+style="font-size:12px;\s*margin-bottom:4px;">'
        + re.escape(emoji)
        + r'</div>'
    )

    circle_html = (
        f'<div style="margin-bottom:4px;">'
        f'<span style="display:inline-block;width:24px;height:24px;border-radius:50%;'
        f'background:{bg};color:white;text-align:center;line-height:24px;font-size:{fsize};">'
        f'{char}</span></div>'
    )

    html, n = re.subn(pattern, circle_html, html)
    callout_count += n
    print(f"  Callout icon '{emoji}': {n} replacements")

print(f"Total callout icon replacements: {callout_count}")

# ===========================================================================
# 3. SECTION H2 HEADERS — remove emoji prefix, add colored bar
# ===========================================================================
# Pattern: <h2 style="...">EMOJI TEXT</h2>
# The h2 tags all have the same style pattern

colored_bar = (
    '<span style="display:inline-block;width:6px;height:20px;'
    'background:linear-gradient(#D32F2F,#FF6F00);border-radius:3px;'
    'margin-right:8px;vertical-align:middle;"></span>'
)

# List of emoji prefixes found in h2 tags (with trailing space)
h2_emojis = ["🔧 ", "📊 ", "📈 ", "🏆 ", "⚡ ", "⏳ ", "🗺️ ", "⚖️ ", "🔬 ", "🎯 ", "⚠️ ", "🔮 "]

h2_count = 0
for emoji_prefix in h2_emojis:
    # Match within h2 tag content
    pattern = (
        r'(<h2\s+style="[^"]*">)'
        + re.escape(emoji_prefix)
    )
    replacement = r'\1' + colored_bar
    html, n = re.subn(pattern, replacement, html)
    h2_count += n
    if n > 0:
        print(f"  H2 emoji '{emoji_prefix.strip()}': {n} replacements")

print(f"Total h2 emoji replacements: {h2_count}")

# ===========================================================================
# 4. CHART HEADER EMOJI — remove 📊 from chart title bars
#    These are inside gradient divs, not h2 tags
# ===========================================================================
# Pattern: inside a div with gradient background, the text starts with "📊 图N:"
# e.g., >📊 图2: 月度评论份额分布（按IP）<
# Also handle the terminal emoji: 📊 进度 and ⏱️ and 🛌 (inside <pre>-like code blocks, leave those alone)

# Only replace 📊 that appears at the start of chart title text in gradient header divs
# Pattern: after "font-weight:600;">📊 "
chart_pattern = r'(font-weight:600;">)\s*📊\s+'
html, n = re.subn(chart_pattern, r'\1', html)
print(f"Chart header 📊 removal: {n} replacements")

# Also handle: after padding:12px 20px; ... >📊  (the chart headers without font-weight in same line)
# These are on their own lines like: 📊 图1: ...
# The pattern in the HTML is: <div style="...font-weight:600;">\n📊 图1:
# Let's handle the multiline case too
chart_pattern2 = r'(font-weight:600;">\s*\n)\s*📊\s+'
html, n2 = re.subn(chart_pattern2, r'\1', html)
print(f"Chart header 📊 removal (multiline): {n2} replacements")

# ===========================================================================
# Summary
# ===========================================================================
print(f"\n--- Summary ---")
print(f"Original file size: {original_len:,} chars")
print(f"New file size: {len(html):,} chars")
print(f"Difference: {len(html) - original_len:+,} chars")

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\nSaved to: {OUTPUT_FILE}")
