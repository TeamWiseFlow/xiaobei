#!/usr/bin/env node
/**
 * fetch-rss.mjs — Fetch and parse an RSS/Atom feed, output as markdown
 *
 * Usage:
 *   node fetch-rss.mjs <url> [--limit N] [--skip url1,url2,...]
 *
 * Output (stdout): markdown text ready for the LLM to read.
 *   - Entries with full content (>200 chars): included inline as article blocks.
 *   - Entries with only short snippets: listed as links for later fetching.
 */

import { createRequire } from "node:module";
import { URL } from "node:url";

const require = createRequire(import.meta.url);

let Parser;
try {
  Parser = require("rss-parser");
} catch {
  console.error("Error: 'rss-parser' not found. Run: npm install rss-parser");
  process.exit(1);
}

// ── Argument parsing ──────────────────────────────────────────────────────────
const args = process.argv.slice(2);
if (!args.length || args[0] === "--help" || args[0] === "-h") {
  console.log("Usage: node fetch-rss.mjs <url> [--limit N] [--skip url1,url2,...]\n");
  process.exit(0);
}

const feedUrl = args[0];
let limit = 20;
let skipUrls = new Set();

for (let i = 1; i < args.length; i++) {
  if (args[i] === "--limit" && args[i + 1]) limit = parseInt(args[++i], 10) || 20;
  if (args[i] === "--skip" && args[i + 1])
    skipUrls = new Set(args[++i].split(",").map((u) => u.trim()).filter(Boolean));
}

try {
  new URL(feedUrl);
} catch {
  console.error(`Error: "${feedUrl}" is not a valid URL.`);
  process.exit(1);
}

// ── Fetch ─────────────────────────────────────────────────────────────────────
const parser = new Parser({
  customFields: {
    item: [
      ["content:encoded", "contentEncoded"],
      ["dc:creator", "dcCreator"],
    ],
  },
  timeout: 15000,
  headers: { "User-Agent": "rss-reader-skill/1.0" },
});

let feed;
try {
  feed = await parser.parseURL(feedUrl);
} catch (err) {
  const msg = String(err.message || err);
  if (msg.match(/40[134]/))
    console.error(`Error: Feed requires authentication or was not found — ${feedUrl}`);
  else if (msg.match(/ENOTFOUND|ETIMEDOUT|ECONNREFUSED/))
    console.error(`Error: Network error — ${msg}`);
  else
    console.error(`Error: Failed to parse feed — ${msg}`);
  process.exit(1);
}

// ── Process entries ───────────────────────────────────────────────────────────
const fullArticles = [];   // entries with substantial content (>200 chars)
const linkOnlyItems = [];  // entries with only a short snippet or no content

let count = 0;
for (const item of feed.items) {
  if (count >= limit) break;

  const url = item.link || item.guid || "";
  if (!url || skipUrls.has(url)) continue;

  // Content priority aligned with rss_parsor.py:
  // content:encoded > content (feedparser's content list) > summary > description
  const rawContent =
    item.contentEncoded || item.content || item.summary || item.description || "";
  const author = item.dcCreator || item.creator || item.author || "";
  const title = item.title || "(no title)";
  const publishDate = item.isoDate || item.pubDate || item.published || "";
  const dateStr = publishDate ? publishDate.slice(0, 10) : "";

  if (rawContent.length > 200) {
    fullArticles.push({ title, url, author, dateStr, content: rawContent });
  } else if (rawContent.length > 50) {
    // Short snippet — needs original page visit
    linkOnlyItems.push({ title, url, author, dateStr, snippet: rawContent });
  } else {
    // No usable content — link only
    linkOnlyItems.push({ title, url, author, dateStr, snippet: "" });
  }
  count++;
}

// ── Output ────────────────────────────────────────────────────────────────────
const feedTitle = feed.title || feedUrl;
const feedDesc = feed.description || feed.subtitle || "";

const lines = [];
lines.push(`## Feed: ${feedTitle}`);
if (feedDesc) lines.push(`> ${feedDesc}`);
lines.push(`Source: ${feedUrl}`);
lines.push(`Retrieved: ${new Date().toISOString().slice(0, 10)} | Total in feed: ${feed.items.length} | Returned: ${count}`);
lines.push("");

if (fullArticles.length > 0) {
  for (const a of fullArticles) {
    lines.push("---");
    lines.push("");
    lines.push(`### ${a.title}`);
    lines.push(`URL: ${a.url}`);
    const meta = [a.author && `Author: ${a.author}`, a.dateStr && `Date: ${a.dateStr}`]
      .filter(Boolean)
      .join(" | ");
    if (meta) lines.push(meta);
    lines.push("");
    lines.push(a.content);
    lines.push("");
  }
  lines.push("---");
  lines.push("");
}

if (linkOnlyItems.length > 0) {
  lines.push("## Articles with summary only — visit URL for full content:");
  lines.push("");
  let idx = 1;
  for (const l of linkOnlyItems) {
    const meta = [l.author && `Author: ${l.author}`, l.dateStr && `Date: ${l.dateStr}`]
      .filter(Boolean)
      .join(", ");
    const snippetPart = l.snippet ? ` — ${l.snippet}` : "";
    lines.push(`* [[${idx}] ${l.title}](${l.url})${snippetPart}${meta ? ` (${meta})` : ""}`);
    idx++;
  }
}

console.log(lines.join("\n"));
