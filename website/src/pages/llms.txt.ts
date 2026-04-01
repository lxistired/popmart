// website/src/pages/llms.txt.ts
import type { APIRoute } from 'astro';
import overview from '../data/overview.json';

export const GET: APIRoute = () => {
  const body = `# 泡泡玛特.md

> Pop Mart 海外社媒另类数据追踪，日更静态网站

## 数据范围
- TikTok: ${overview.tiktok_videos}+ 视频, ${overview.tiktok_comments}+ 评论
- Instagram: ${overview.instagram_posts} 帖子, ${overview.instagram_comments} 评论

## 数据接口 (JSON)
- /data/overview.json — 汇总统计
- /data/tiktok-videos.json — 视频元数据（含 IP 分类）
- /data/tiktok-trend.json — 每周评论趋势（按 IP 分组）
- /data/instagram-posts.json — 帖子列表（含 IP 分类）
- /data/instagram-trend.json — 每周评论趋势
- /data/ip-share.json — IP 声量占比

## 页面
- / — 首页概览
- /tiktok — TikTok 详细数据表格
- /instagram — Instagram 详细数据表格
- /methodology — 采集方法论和 IP 分类规则

## 更新频率
每日 UTC 08:00 自动更新
`;

  return new Response(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
