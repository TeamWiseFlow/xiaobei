---
name: rss-reader
description: Discover the RSS/Atom feed URL for a website, then run the fetch-rss.mjs script to retrieve and parse articles from the feed.
metadata:
  openclaw:
    emoji: "📡"
    always: false
    requires:
      bins:
      - node
---

# RSS / Atom Feed Reader

Use this skill when:
- The user wants to monitor or retrieve updates from a website
- The user provides an RSS or Atom feed URL directly
- You need to efficiently collect multiple articles from one source without visiting each page

> 通过 PATH 调用 wrapper：`rss-reader <cmd>`，无需拼接脚本路径。

---

## Step 1 — Discover the feed URL

If you already have an RSS/Atom URL, skip to Step 2.

**Method A — page source**
Navigate to the website, take a snapshot, and look for `<link rel="alternate">` tags in `<head>`:
```html
<link rel="alternate" type="application/rss+xml" href="/feed">
<link rel="alternate" type="application/atom+xml" href="/atom.xml">
```

**Method B — common paths** (try one at a time until one returns XML)
```
/feed  /feed.xml  /rss  /rss.xml  /atom.xml  /index.xml
/?feed=rss2  /feeds/posts/default
```

**Method C** — look for RSS icons 🟠 or links labelled "RSS", "Subscribe", "Feed".

A valid feed URL returns XML starting with `<rss`, `<feed`, or `<rdf:RDF`.

---

## Step 2 — Run the script

```bash
rss-reader <feed_url> [--limit N] [--skip url1,url2,...]
```

| Option | Description |
|--------|-------------|
| `--limit N` | Max entries to return (default: 20) |
| `--skip url1,url2,...` | Skip entries whose URLs are already processed (deduplication) |

**Output** is markdown with two sections:
1. **Full-content articles** — entries where the feed includes the complete article body (>200 chars). Process these directly; **no need to visit the article URL**.
2. **Summary-only links** — entries with only a short snippet. Visit each URL to retrieve the full content.

---

## Step 3 — Handle results

- For full-content articles: extract title, author, date, and content directly from the script output.
- For summary-only links: use `browser.navigate(url)` to fetch each article page.
- Pass the script output directly to the user or to your processing pipeline.

---

## Edge cases

| Situation | Action |
|-----------|--------|
| Feed returns 404 | Try alternative paths from Step 1 |
| Feed requires login | Follow the **browser-guide** skill |
| Script error "Failed to parse feed" | Feed XML may be malformed; report the URL to the user |
| Empty feed | Report: "This RSS feed has no entries." |
