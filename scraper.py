#!/usr/bin/env python3
"""Daily news scraper — fetches from 6 sources and inserts into Supabase."""
import json, re, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

SUPABASE_URL = "https://sqrzrvstlvxqxdxvhlxz.supabase.co"
ANON_KEY     = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNxcnpydnN0bHZ4cXhkeHZobHh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEwMTUzMjAsImV4cCI6MjA5NjU5MTMyMH0.C6Gz61TB3GhLnbDWywogGZDcqTu1G2ta9-Dyo60Yiho"
TODAY        = datetime.now(timezone.utc).strftime("%Y-%m-%d")
UA           = {"User-Agent": "Mozilla/5.0 (compatible; TechNewsScraper/1.0)"}

# ── Category heuristics ───────────────────────────────────────────────────────

def categorize(title, summary=""):
    t = (title + " " + summary).lower()
    if any(k in t for k in ["llm","large language","gpt","claude","gemini","mistral","llama","deepseek","qwen",
                              "arxiv","neural","transformer","benchmark","foundation model","multimodal",
                              "diffusion","reasoning model","o1","o3","ai research"]):
        return "A"
    if any(k in t for k in ["chatgpt","copilot","cursor","openai","anthropic","ai tool","ai product",
                              "plugin","ai assistant","agent","launch","new feature"]):
        return "B"
    if any(k in t for k in ["open source","open-source","github","hugging face","ollama",
                              "npm release","pypi","new library","repo"]):
        return "C"
    if any(k in t for k in ["react","vue","svelte","swift","kotlin","android","ios","javascript",
                              "typescript","rust","golang","python","frontend","backend","docker",
                              "kubernetes","devops","next.js","database","postgres","redis","web dev"]):
        return "D"
    return "E"

# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_url(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()

def fetch_json(url, timeout=10):
    return json.loads(fetch_url(url, timeout))

def clean_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()

def truncate(text, n=200):
    text = clean_html(text)
    return (text[:n] + "…") if len(text) > n else text

def make_item(category, title, source, summary, url, image_url=None):
    return {
        "category":  category,
        "title":     title,
        "source":    source,
        "summary":   summary,
        "url":       url or "",
        "date":      TODAY,
        "type":      "scraped",
        "image_url": image_url,
    }

# ── Sources ───────────────────────────────────────────────────────────────────

def fetch_hn(limit=15):
    print("→ Hacker News")
    items = []
    try:
        ids = fetch_json("https://hacker-news.firebaseio.com/v1/topstories.json")
        for id in ids:
            if len(items) >= limit:
                break
            try:
                it = fetch_json(f"https://hacker-news.firebaseio.com/v1/item/{id}.json", timeout=5)
                if it.get("type") == "story" and it.get("title") and it.get("url"):
                    items.append(make_item(
                        categorize(it["title"]), it["title"],
                        "Hacker News", it["title"], it["url"]
                    ))
            except:
                pass
    except Exception as e:
        print(f"  error: {e}")
    print(f"  {len(items)} items")
    return items


def fetch_devto(limit=12):
    print("→ Dev.to")
    items = []
    try:
        articles = fetch_json(f"https://dev.to/api/articles?per_page={limit}&top=7")
        for a in articles:
            title   = a.get("title", "")
            summary = truncate(a.get("description") or title)
            image   = a.get("cover_image") or a.get("social_image")
            items.append(make_item(categorize(title, summary), title, "Dev.to", summary, a.get("url",""), image))
    except Exception as e:
        print(f"  error: {e}")
    print(f"  {len(items)} items")
    return items


def fetch_github_trending(limit=10):
    print("→ GitHub Trending")
    items = []
    try:
        html  = fetch_url("https://github.com/trending?since=daily").decode("utf-8", errors="ignore")
        slugs = re.findall(r'<h2[^>]*>\s*<a\s+href="/([a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+)"', html)
        descs = re.findall(r'class="[^"]*col-9[^"]*"[^>]*>\s*(.*?)\s*</p>', html, re.DOTALL)
        for i, slug in enumerate(slugs[:limit]):
            desc = clean_html(descs[i]) if i < len(descs) else ""
            name = slug.replace("/", " / ")
            items.append(make_item(
                categorize(name, desc), name,
                "GitHub Trending", desc or f"GitHub 热门仓库：{name}",
                f"https://github.com/{slug}"
            ))
    except Exception as e:
        print(f"  error: {e}")
    print(f"  {len(items)} items")
    return items


def fetch_arxiv(limit=8):
    print("→ arXiv cs.AI")
    items = []
    try:
        root    = ET.fromstring(fetch_url("https://rss.arxiv.org/rss/cs.AI"))
        channel = root.find("channel")
        for entry in (channel.findall("item") if channel else [])[:limit]:
            title = (entry.findtext("title") or "").strip()
            link_el = entry.find("link")
            link = ""
            if link_el is not None:
                link = (link_el.text or "").strip()
                if not link and link_el.tail:
                    link = link_el.tail.strip()
            desc = truncate(entry.findtext("description") or "")
            if title:
                items.append(make_item("A", title, "arXiv", desc, link))
    except Exception as e:
        print(f"  error: {e}")
    print(f"  {len(items)} items")
    return items


def fetch_rss(feed_url, source_name, limit=8):
    print(f"→ {source_name}")
    items = []
    try:
        root    = ET.fromstring(fetch_url(feed_url))
        channel = root.find("channel")
        for entry in (channel.findall("item") if channel else [])[:limit]:
            title = (entry.findtext("title") or "").strip()
            link_el = entry.find("link")
            link = ""
            if link_el is not None:
                link = (link_el.text or "").strip()
                if not link and link_el.tail:
                    link = link_el.tail.strip()
            desc = truncate(entry.findtext("description") or "")
            image_url = None
            enc = entry.find("enclosure")
            if enc is not None and (enc.get("type","").startswith("image")):
                image_url = enc.get("url")
            media = entry.find("{http://search.yahoo.com/mrss/}content")
            if media is not None:
                image_url = media.get("url") or image_url
            if title:
                items.append(make_item(categorize(title, desc), title, source_name, desc, link, image_url))
    except Exception as e:
        print(f"  error: {e}")
    print(f"  {len(items)} items")
    return items

# ── Supabase ──────────────────────────────────────────────────────────────────

def insert(items):
    if not items:
        return
    body = json.dumps(items).encode()
    req  = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/news_items",
        data=body,
        headers={
            "apikey":        ANON_KEY,
            "Authorization": f"Bearer {ANON_KEY}",
            "Content-Type":  "application/json",
            "Prefer":        "resolution=ignore-duplicates,return=minimal",
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req)
        print(f"\n✓ 写入成功，状态 {resp.status}，共 {len(items)} 条")
    except urllib.error.HTTPError as e:
        print(f"\n✗ Supabase 错误 {e.code}: {e.read().decode()[:300]}")


def db_count():
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/news_items?select=count",
        headers={"apikey": ANON_KEY, "Authorization": f"Bearer {ANON_KEY}", "Prefer": "count=exact"},
    )
    return urllib.request.urlopen(req).headers.get("content-range","?").split("/")[-1]

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Scraper running — {TODAY}\n")
    all_items  = []
    all_items += fetch_hn()
    all_items += fetch_devto()
    all_items += fetch_github_trending()
    all_items += fetch_arxiv()
    all_items += fetch_rss("https://36kr.com/feed", "36kr")
    all_items += fetch_rss("https://www.infoq.cn/feed", "InfoQ")
    print(f"\n总计抓取 {len(all_items)} 条")
    insert(all_items)
    print(f"数据库当前共 {db_count()} 条")
