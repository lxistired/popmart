"""
泡泡玛特小红书评论自动提取脚本 v3
使用 undetected-chromedriver + ActionChains真实点击

用法：
1. 关闭所有Chrome窗口
2. python scrape_comments.py          # 全量
   python scrape_comments.py --limit 3 # 测试前3条
"""

import json
import os
import re
import sqlite3
import sys
import time
import random
import traceback
from urllib.parse import quote


def driver_sleep(driver, seconds):
    """带心跳的等待，每20s ping一次driver防止DevTools断连"""
    end = time.time() + seconds
    while time.time() < end:
        chunk = min(20, end - time.time())
        if chunk > 0:
            time.sleep(chunk)
        try:
            _ = driver.current_url  # 心跳ping
        except Exception:
            raise  # 真的断了就抛出，让上层处理

# --- Config ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'popmart_comments.db')
# 切换 dig_queue.txt / test_queue.txt 来测试
QUEUE_PATH = os.path.join(SCRIPT_DIR, 'test_queue.txt') if '--test' in sys.argv else os.path.join(SCRIPT_DIR, 'dig_queue.txt')
CHECKPOINT_PATH = os.path.join(SCRIPT_DIR, 'scrape_checkpoint.json')
UC_PROFILE = os.path.join(SCRIPT_DIR, '.uc_profile')
BASE_URL = 'https://www.xiaohongshu.com'

# JS: 从DOM提取一级评论（滚动到底后调用）
EXTRACT_ALL_JS = """
return (function() {
    var scroller = document.querySelector('.note-scroller');
    var items = document.querySelectorAll('.comment-item:not(.comment-item-sub)');
    var comments = [];
    items.forEach(function(item) {
        var nameEl = item.querySelector('.author-wrapper .name');
        var contentEl = item.querySelector('.note-text');
        var dateEl = item.querySelector('.date');
        var likeEl = item.querySelector('.like-wrapper .count');
        var locationEl = item.querySelector('.location');
        if (contentEl && contentEl.textContent.trim()) {
            comments.push({
                name: nameEl ? nameEl.textContent.trim() : '',
                content: contentEl.textContent.trim(),
                date: dateEl ? dateEl.textContent.trim() : '',
                likes: likeEl ? likeEl.textContent.trim() : '0',
                location: locationEl ? locationEl.textContent.trim() : ''
            });
        }
    });
    var totalMatch = document.querySelector('.comments-el');
    var total = totalMatch ? (totalMatch.textContent.match(/共\\s*(\\d+)\\s*条/) || [])[1] : '-1';
    return JSON.stringify({total: total, count: comments.length, comments: comments});
})();
"""

# JS: 提取搜索结果中的note卡片（优先取带xsec_token的链接）
SEARCH_CARDS_JS = r"""
return (function() {
    var noteMap = {};
    document.querySelectorAll('a').forEach(function(a) {
        var href = a.getAttribute('href') || '';
        var match = href.match(/(?:\/explore\/|\/search_result\/)([a-f0-9]{24})/);
        if (match) {
            var nid = match[1];
            if (!noteMap[nid]) {
                var section = a.closest('section.note-item') || a.closest('[class*="note"]') || a.parentElement;
                noteMap[nid] = {noteId: nid, title: section ? section.textContent.trim().substring(0,100) : '', href: ''};
            }
            // 优先保存带xsec_token的链接
            if (href.includes('xsec_token')) {
                noteMap[nid].href = href;
            } else if (!noteMap[nid].href) {
                noteMap[nid].href = href;
            }
        }
    });
    var cards = [];
    for (var nid in noteMap) { cards.push(noteMap[nid]); }
    return JSON.stringify(cards);
})();
"""


def load_queue(path, limit=None):
    posts = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t', 1)
            if len(parts) == 2:
                posts.append((int(parts[0]), parts[1].strip()))
    return posts[:limit] if limit else posts


def load_checkpoint():
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'completed': [], 'url_map': {}}


def save_checkpoint(data):
    with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def title_similarity(a, b):
    a_clean = re.sub(r'[^\w]', '', a.lower())
    b_clean = re.sub(r'[^\w]', '', b.lower())
    if not a_clean or not b_clean:
        return 0
    common = sum(1 for c in a_clean if c in b_clean)
    return common / max(len(a_clean), len(b_clean))


def classify_ip(title):
    t = title.lower()
    if 'labubu' in t or '拉布布' in t or 'the monsters' in t: return 'Labubu'
    if 'dimoo' in t: return 'Dimoo'
    if '星星人' in t: return '星星人'
    if 'molly' in t: return 'Molly'
    if 'skullpanda' in t or 'sp' in t.split(): return 'Skullpanda'
    if 'zsiga' in t or '嘎子' in t: return 'Zsiga'
    if '小甜豆' in t: return '小甜豆'
    return '泡泡玛特'


def parse_comment_likes(s):
    s = s.strip()
    if s in ('赞', '0', '', '抢首评'):
        return 0
    s = s.replace(',', '')
    if '万' in s:
        return int(float(s.replace('万', '')) * 10000)
    try:
        return int(s)
    except:
        return 0


def save_to_db(post_title, post_likes, note_id, ip, comments_data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id FROM posts WHERE title = ?', (post_title[:60],))
    row = c.fetchone()
    if row:
        post_id = row[0]
        c.execute('UPDATE posts SET note_id = ?, comments_total = ? WHERE id = ?',
                  (note_id, len(comments_data), post_id))
    else:
        c.execute('INSERT OR IGNORE INTO posts (title, ip, likes, comments_total, note_id) VALUES (?, ?, ?, ?, ?)',
                  (post_title[:60], ip, str(post_likes), len(comments_data), note_id))
        post_id = c.lastrowid or c.execute('SELECT id FROM posts WHERE title = ?', (post_title[:60],)).fetchone()[0]

    inserted = 0
    for cm in comments_data:
        try:
            c.execute('INSERT OR IGNORE INTO comments (post_id, commenter, comment_date, comment_likes, comment_text, location) VALUES (?, ?, ?, ?, ?, ?)',
                     (post_id, cm['name'], cm['date'], str(parse_comment_likes(cm['likes'])), cm['content'], cm.get('location', '')))
            if c.rowcount > 0:
                inserted += 1
        except:
            pass
    conn.commit()
    conn.close()
    return inserted


def check_captcha(driver):
    """检测是否遇到验证码/安全检测，等待用户手动处理"""
    try:
        url = driver.current_url
        body = driver.find_element_by_tag_name('body').text[:500]
    except:
        return False

    is_captcha = ('captcha' in url or 'Security Verification' in driver.title or
                  'verify' in url or '请打开小红书App扫码' in body or
                  "This Page Isn't Available" in body)

    if is_captcha:
        print('  ⚠️ 安全验证！请在Chrome中手动完成验证...')
        for _ in range(120):  # 最多等10分钟
            time.sleep(5)
            try:
                new_url = driver.current_url
                if 'captcha' not in new_url and 'verify' not in new_url and '404' not in new_url:
                    print('  ✅ 验证通过')
                    time.sleep(2)
                    return True
            except:
                pass
        print('  ❌ 验证超时')
        return False
    return False


def scroll_and_extract_comments(driver):
    """滚动评论区并提取所有一级评论"""
    all_comments = []
    seen = set()
    no_new = 0

    for attempt in range(40):
        try:
            result_json = driver.execute_script(EXTRACT_ALL_JS)
            result = json.loads(result_json) if result_json else {}
            comments = result.get('comments', [])
        except:
            break

        new = 0
        for cm in comments:
            key = cm['content'][:50] + cm['name']
            if key not in seen:
                seen.add(key)
                all_comments.append(cm)
                new += 1

        if new == 0:
            no_new += 1
            if no_new >= 6:
                break
        else:
            no_new = 0

        # 滚动 .note-scroller 到底部触发懒加载
        try:
            driver.execute_script("""
                var s = document.querySelector('.note-scroller');
                if (s) { s.scrollTop = s.scrollHeight; }
                else { window.scrollBy(0, 600); }
            """)
            time.sleep(2.0 + random.random() * 2.0)
        except:
            break

    return all_comments


def main():
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains

    # 解析参数
    limit = None
    for i, arg in enumerate(sys.argv):
        if arg == '--limit' and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    queue = load_queue(QUEUE_PATH, limit=limit)
    checkpoint = load_checkpoint()
    completed_titles = set(checkpoint.get('completed', []))
    url_map = checkpoint.get('url_map', {})
    remaining = [(likes, title) for likes, title in queue if title not in completed_titles]

    print(f'=== 泡泡玛特评论提取 v3 (uc + 真实点击) ===')
    print(f'队列: {len(queue)} | 已完成: {len(completed_titles)} | 待处理: {len(remaining)}')

    if not remaining:
        print('所有帖子已处理完毕！')
        return

    # 启动Chrome
    print(f'\n启动Chrome...')
    print(f'  配置: {UC_PROFILE}')

    try:
        options = uc.ChromeOptions()
        options.add_argument('--window-size=1300,850')
        driver = uc.Chrome(options=options, user_data_dir=UC_PROFILE, use_subprocess=True)
    except Exception as e:
        print(f'❌ 启动失败: {e}')
        print('请确保已关闭所有Chrome窗口后重试。')
        return

    driver.set_page_load_timeout(60)
    driver.implicitly_wait(5)
    print('✅ Chrome启动成功')

    # 检查登录（带重试）
    print('验证登录...')
    for load_try in range(3):
        try:
            driver.get(f'{BASE_URL}/explore')
            break
        except Exception as e:
            print(f'  页面加载慢，重试 ({load_try+1}/3)...')
            if load_try == 2:
                print(f'❌ 页面加载失败: {e}')
                driver.quit()
                return
            time.sleep(5)

    time.sleep(6)
    check_captcha(driver)

    for attempt in range(120):
        try:
            body = driver.find_element(By.TAG_NAME, 'body').text[:500]
            if '手机号登录' in body or '验证码登录' in body or '密码登录' in body:
                if attempt == 0:
                    print('⚠️ 未登录！请在Chrome中登录小红书...')
                    print('  （登录后脚本自动继续，最多等10分钟）')
                time.sleep(5)
            else:
                print('✅ 已登录')
                break
        except:
            time.sleep(3)
    else:
        print('❌ 登录超时')
        driver.quit()
        return

    # 主循环
    start_time = time.time()
    success_count = 0
    fail_count = 0
    total_comments = 0

    for idx, (likes, title) in enumerate(remaining):
        progress = f'[{idx + 1}/{len(remaining)}]'
        print(f'\n{progress} {title[:45]}... (赞:{likes})')

        keyword = re.sub(r'[^\w\u4e00-\u9fffA-Za-z0-9]', ' ', title).strip()[:25]
        if len(keyword) < 4:
            keyword = title[:20]

        try:
            # === Step 1: 搜索（通过搜索框，不用URL导航）===
            # 先确保在XHS域内
            cur = driver.current_url
            if 'xiaohongshu.com' not in cur:
                try:
                    driver.get(f'{BASE_URL}/explore')
                except:
                    pass
                time.sleep(5)

            # 用搜索框输入关键词
            try:
                search_input = driver.find_element(By.ID, 'search-input')
                ActionChains(driver).move_to_element(search_input).click().perform()
                time.sleep(0.5)
                search_input.clear()
                time.sleep(0.3)
                search_input.send_keys(keyword)
                time.sleep(0.3)
                search_input.send_keys(Keys.ENTER)
            except Exception as search_err:
                # 备选：点击搜索图标区域后输入
                try:
                    search_box = driver.find_element(By.CSS_SELECTOR, 'input[placeholder*="搜索"], .search-input')
                    search_box.click()
                    time.sleep(0.5)
                    search_box.clear()
                    search_box.send_keys(keyword + Keys.ENTER)
                except:
                    print(f'  搜索框找不到，跳过')
                    fail_count += 1
                    continue

            time.sleep(10 + random.random() * 8)

            # 检查验证码
            if check_captcha(driver):
                time.sleep(3)

            # 等待搜索结果
            cards = []
            for wait_try in range(8):
                try:
                    cards_json = driver.execute_script(SEARCH_CARDS_JS)
                    cards = json.loads(cards_json) if cards_json else []
                    if cards:
                        break
                except:
                    pass
                time.sleep(2)

            if not cards:
                # 保存调试截图
                debug_file = os.path.join(SCRIPT_DIR, f'debug_search_{idx}.png')
                try:
                    driver.save_screenshot(debug_file)
                    print(f'  无搜索结果，截图: debug_search_{idx}.png')
                except:
                    print(f'  无搜索结果')
                fail_count += 1
                continue

            # 匹配标题
            best = max(cards, key=lambda c: title_similarity(title, c.get('title', '')))
            note_id = best['noteId']
            score = title_similarity(title, best.get('title', ''))
            print(f'  note_id: {note_id} (匹配: {score:.2f})')

            # === Step 2: 打开帖子（用带xsec_token的链接或ActionChains点击）===
            post_href = best.get('href', '')
            if 'xsec_token' in post_href:
                # 有token，直接导航
                full_url = post_href if post_href.startswith('http') else BASE_URL + post_href
                try:
                    driver.get(full_url)
                except:
                    pass  # 超时但可能部分加载了
            else:
                # 没有token，用真实点击
                try:
                    link_el = driver.find_element(By.CSS_SELECTOR, f'a[href*="{note_id}"]')
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link_el)
                    time.sleep(0.5)
                    ActionChains(driver).move_to_element(link_el).pause(0.3).click().perform()
                except:
                    print(f'  ❌ 点击失败，跳过')
                    fail_count += 1
                    continue

            time.sleep(15 + random.random() * 10)

            # 检查是否被拦截（404/验证码）
            if check_captcha(driver):
                time.sleep(3)

            cur_url = driver.current_url
            if '404' in cur_url or "This Page Isn't Available" in driver.title:
                print(f'  ❌ 帖子被拦截(404)，跳过')
                driver.back()
                time.sleep(2)
                fail_count += 1
                continue

            # 验证帖子overlay确实打开（URL含note_id），最多重试3次
            overlay_open = note_id in cur_url
            if not overlay_open:
                print(f'  ⚠️ overlay未打开(url:{cur_url[-60:]}), 重试...')
                for retry in range(3):
                    try:
                        link_el = driver.find_element(By.CSS_SELECTOR, f'a[href*="{note_id}"]')
                        ActionChains(driver).move_to_element(link_el).pause(0.5).click().perform()
                        time.sleep(10 + random.random() * 5)
                        cur_url = driver.current_url
                        if note_id in cur_url:
                            overlay_open = True
                            print(f'  ✅ 重试{retry+1}次后overlay打开')
                            break
                    except Exception as exc:
                        print(f'  重试{retry+1}失败: {exc}')
                        time.sleep(3)
                if not overlay_open:
                    print(f'  ❌ overlay始终未打开，跳过')
                    fail_count += 1
                    continue

            # === Step 3: 滚动提取评论 ===
            # 检测评论区是否被关闭
            try:
                no_comments = driver.execute_script("return !!document.querySelector('.no-comments')")
                if no_comments:
                    print(f'  ⚠️ 评论区已关闭（no-comments），永久跳过')
                    checkpoint['completed'].append(title)
                    checkpoint['url_map'][title] = note_id
                    save_checkpoint(checkpoint)
                    fail_count += 1
                    continue
            except:
                pass
            all_comments = scroll_and_extract_comments(driver)
            print(f'  评论: {len(all_comments)} 条一级评论')

            # === Step 4: 保存 ===
            if all_comments:
                ip = classify_ip(title)
                inserted = save_to_db(title, likes, note_id, ip, all_comments)
                print(f'  入库: {inserted} 条 (IP: {ip})')
                total_comments += len(all_comments)

            # 只有抓到评论才标记完成，0条留着下次重抓
            if all_comments:
                checkpoint['completed'].append(title)
                checkpoint['url_map'][title] = note_id
                save_checkpoint(checkpoint)
            success_count += 1

            # 返回搜索页（按Esc关闭弹窗或后退）
            try:
                from selenium.webdriver.common.keys import Keys
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(1)
            except:
                pass
            try:
                driver.back()
                time.sleep(2)
            except:
                pass

            # 帖子间随机延迟（模拟人工浏览：2-4分钟）
            wait = random.uniform(120, 240)
            # 20%概率触发"走神/去干别的"延迟（额外10-20分钟）
            if random.random() < 0.20:
                extra = random.uniform(60, 180)
                print(f'  💤 等待 {wait:.0f}s + 走神 {extra/60:.1f}分钟...')
                driver_sleep(driver, wait + extra)
            else:
                print(f'  💤 等待 {wait:.0f}s...')
                driver_sleep(driver, wait)

        except Exception as e:
            print(f'  ❌ {type(e).__name__}: {str(e)[:100]}')
            traceback.print_exc()
            fail_count += 1
            # 尝试恢复
            try:
                driver.get(f'{BASE_URL}/explore')
                time.sleep(3)
            except:
                print('  浏览器已断开，退出')
                break

        # 进度报告 + 每15条大休息（模拟刷累了去休息：20-35分钟）
        if (idx + 1) % 15 == 0:
            elapsed = time.time() - start_time
            rate = (idx + 1) / elapsed * 3600
            print(f'\n  📊 {idx+1}/{len(remaining)} | 成功:{success_count} 失败:{fail_count}')
            print(f'  ⏱️ {elapsed/60:.1f}分钟 | {rate:.0f}条/时 | 评论:{total_comments}')
            big_wait = random.uniform(180, 300)
            print(f'  🛌 每15条小休息 {big_wait/60:.1f}分钟...')
            driver_sleep(driver, big_wait)

    elapsed = time.time() - start_time
    print(f'\n{"="*50}')
    print(f'✅ {success_count}成功 / {fail_count}失败 / {total_comments}条评论 / {elapsed/60:.1f}分钟')

    try:
        driver.quit()
    except:
        pass


if __name__ == '__main__':
    main()
