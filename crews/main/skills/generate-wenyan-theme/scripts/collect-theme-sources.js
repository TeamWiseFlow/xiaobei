#!/usr/bin/env node
/**
 * collect-theme-sources.js — collect WeChat article HTML samples for theme generation.
 */

import { spawn } from "node:child_process";
import { constants } from "node:fs";
import { access, mkdir, open, stat } from "node:fs/promises";
import { basename, dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_OUTPUT = "wenyan-theme-sources.json";
const DEFAULT_ACCOUNT_COUNT = 10;
const DEFAULT_SCAN_BATCH = 20;
const DEFAULT_MAX_SCAN = 100;

function printJson(data) {
  process.stdout.write(`${JSON.stringify(data, null, 2)}\n`);
}

function fail(message, code = 1) {
  printJson({ ok: false, error: message });
  process.exit(code);
}

function usage() {
  process.stdout.write(
    [
      "Usage:",
      "  node ./skills/generate-wenyan-theme/scripts/collect-theme-sources.js --url <mp.weixin.qq.com URL> [--output file]",
      "  node ./skills/generate-wenyan-theme/scripts/collect-theme-sources.js --account <公众号名> [--keywords k1,k2] [--count 10] [--output file]",
      "",
      "Options:",
      "  --scan-batch N   每批扫描文章数，默认 20",
      "  --max-scan N     关键词筛选最多扫描文章数，默认 100",
      "",
      "Output:",
      "  --output 工作区内相对 .json 路径（可含子目录，如 wenyan-theme/sources.json）；禁止绝对路径 / .. 上跳。",
    ].join("\n") + "\n"
  );
}

function readFlag(args, flag) {
  const idx = args.indexOf(flag);
  if (idx < 0 || idx + 1 >= args.length) return null;
  const value = args[idx + 1];
  return value && !value.startsWith("--") ? value : null;
}

function readNumberFlag(args, flag, fallback) {
  const raw = readFlag(args, flag);
  if (!raw) return fallback;
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback;
}

function parseKeywords(raw) {
  if (!raw) return [];
  return raw
    .split(/[,，\n]/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

function defaultWxHunterPath() {
  const currentFile = fileURLToPath(import.meta.url);
  // Script lives at: crews/main/skills/generate-wenyan-theme/scripts/
  // wx-mp-hunter is a sibling skill under crews/main/skills/, so go up 2
  // levels to reach crews/main/skills/, then into the wx-mp-hunter tree.
  const skillsRoot = resolve(dirname(currentFile), "../..");
  return join(skillsRoot, "wx-mp-hunter", "scripts", "wx-mp-hunter.sh");
}

function isWechatArticleUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "mp.weixin.qq.com";
  } catch {
    return false;
  }
}

function parseArgs() {
  const args = process.argv.slice(2);
  if (args.includes("--help") || args.includes("-h")) {
    usage();
    process.exit(0);
  }

  const url = readFlag(args, "--url") ?? "";
  const account = readFlag(args, "--account") ?? "";
  if (url && account) fail("--url 与 --account 只能二选一");
  if (!url && !account) fail("必须提供 --url 或 --account");
  if (url && !isWechatArticleUrl(url)) fail("--url 必须是 https://mp.weixin.qq.com 域名下的文章链接");

  return {
    mode: url ? "url" : "account",
    url,
    account,
    keywords: parseKeywords(readFlag(args, "--keywords")),
    count: readNumberFlag(args, "--count", DEFAULT_ACCOUNT_COUNT),
    scanBatch: Math.min(readNumberFlag(args, "--scan-batch", DEFAULT_SCAN_BATCH), DEFAULT_SCAN_BATCH),
    maxScan: readNumberFlag(args, "--max-scan", DEFAULT_MAX_SCAN),
    output: readFlag(args, "--output") ?? DEFAULT_OUTPUT,
    wxHunter: defaultWxHunterPath(),
  };
}

async function assertExecutableFile(filePath, label) {
  const info = await stat(filePath).catch(() => null);
  if (!info) fail(`找不到 ${label}: ${filePath}`);
  if (!info.isFile()) fail(`${label} 不是文件: ${filePath}`);
  await access(filePath, constants.X_OK).catch(() => fail(`${label} 不可执行: ${filePath}`));
}

function workspaceOutputPath(filePath) {
  if (!filePath.endsWith(".json")) fail("--output 必须使用 .json 后缀");
  if (filePath.startsWith(sep)) {
    fail("--output 不能是绝对路径");
  }
  // 允许工作区内的相对路径（可含子目录，如 wenyan-theme/sources.json），禁止 .. 上跳。
  const cwd = resolve(process.cwd());
  const absolute = resolve(cwd, filePath);
  const relativePrefix = `${cwd}${sep}`;
  if (absolute === cwd || !absolute.startsWith(relativePrefix)) {
    fail("--output 必须位于当前工作目录内（可含子目录，禁止 .. 上跳或绝对路径）");
  }
  return absolute;
}

function runJson(command, args) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"], shell: false });
    let stdout = "";
    let stderr = "";

    child.stdout.setEncoding("utf-8");
    child.stderr.setEncoding("utf-8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", rejectPromise);
    child.on("close", (code) => {
      let parsed = null;
      try {
        parsed = JSON.parse(stdout);
      } catch {
        rejectPromise(new Error(`命令输出不是 JSON: ${basename(command)} ${args.join(" ")}\n${stderr || stdout}`));
        return;
      }

      if (code !== 0) {
        const error = String(parsed.error ?? stderr ?? `命令失败，退出码 ${code}`);
        rejectPromise(new Error(error));
        return;
      }
      resolvePromise(parsed);
    });
  });
}

function toArticleSummary(item) {
  const link = String(item.link ?? "").trim();
  if (!isWechatArticleUrl(link)) return null;

  const createTime = Number(item.create_time ?? NaN);
  return {
    title: String(item.title ?? "").trim(),
    link,
    digest: String(item.digest ?? "").trim(),
    author: String(item.author ?? "").trim(),
    create_time: Number.isFinite(createTime) ? createTime : null,
    item_show_type: Number(item.item_show_type ?? 0),
    is_deleted: Boolean(item.is_deleted),
  };
}

function articleMatches(article, keywords) {
  if (keywords.length === 0) return true;
  const haystack = `${article.title}\n${article.digest}\n${article.author}`.toLowerCase();
  return keywords.some((keyword) => haystack.includes(keyword.toLowerCase()));
}

async function searchAccount(wxHunter, keyword) {
  const data = await runJson(wxHunter, ["search", keyword, "--begin", "0", "--size", "5"]);
  const accounts = Array.isArray(data.accounts) ? data.accounts : [];
  if (accounts.length === 0) fail(`未搜索到公众号: ${keyword}`);
  return accounts[0];
}

async function listCandidateArticles(options, fakeid) {
  const selected = [];
  const seen = new Set();
  let begin = 0;
  const targetCount = options.keywords.length > 0 ? options.count : Math.min(options.count, DEFAULT_ACCOUNT_COUNT);

  while (selected.length < targetCount && begin < options.maxScan) {
    const data = await runJson(options.wxHunter, [
      "account-posts",
      fakeid,
      "--begin",
      String(begin),
      "--size",
      String(options.scanBatch),
    ]);
    const rawArticles = Array.isArray(data.articles) ? data.articles : [];
    if (rawArticles.length === 0) break;

    for (const raw of rawArticles) {
      const article = toArticleSummary(raw);
      if (!article || article.is_deleted || seen.has(article.link)) continue;
      seen.add(article.link);
      if (articleMatches(article, options.keywords)) selected.push(article);
      if (selected.length >= targetCount) break;
    }

    begin += options.scanBatch;
  }

  return selected;
}

async function fetchArticleHtml(wxHunter, article) {
  const data = await runJson(wxHunter, ["fetch", article.link, "--html"]);
  return {
    ...article,
    title: String(data.title ?? article.title),
    author: String(data.author ?? article.author),
    publish_time: String(data.publish_time ?? ""),
    content_text: String(data.content_text ?? ""),
    content_html: String(data.content_html ?? ""),
  };
}

async function writeOutput(filePath, data) {
  const absolute = workspaceOutputPath(filePath);
  await mkdir(dirname(absolute), { recursive: true });
  const file = await open(absolute, constants.O_WRONLY | constants.O_CREAT | constants.O_TRUNC | constants.O_NOFOLLOW, 0o600).catch(
    (error) => {
      throw new Error(`无法安全写入输出文件: ${error instanceof Error ? error.message : String(error)}`);
    }
  );
  try {
    await file.writeFile(`${JSON.stringify(data, null, 2)}\n`, "utf-8");
  } finally {
    await file.close();
  }
  return absolute;
}

async function collectByUrl(options) {
  const sample = await fetchArticleHtml(options.wxHunter, {
    title: "",
    link: options.url,
    digest: "",
    author: "",
    create_time: null,
    item_show_type: 0,
    is_deleted: false,
  });
  const output = await writeOutput(options.output, {
    mode: "url",
    source_url: options.url,
    collected_at: new Date().toISOString(),
    articles: [sample],
  });
  printJson({ ok: true, mode: "url", output, count: 1, articles: [{ title: sample.title, link: sample.link }] });
}

async function collectByAccount(options) {
  const account = await searchAccount(options.wxHunter, options.account);
  const fakeid = String(account.fakeid ?? "");
  if (!fakeid) fail(`公众号搜索结果缺少 fakeid: ${options.account}`);

  const candidates = await listCandidateArticles(options, fakeid);
  if (candidates.length === 0) fail("未找到符合条件的文章");

  const samples = [];
  for (const article of candidates) {
    samples.push(await fetchArticleHtml(options.wxHunter, article));
  }

  const output = await writeOutput(options.output, {
    mode: "account",
    account: {
      fakeid,
      nickname: String(account.nickname ?? options.account),
      alias: String(account.alias ?? ""),
      signature: String(account.signature ?? ""),
    },
    keywords: options.keywords,
    collected_at: new Date().toISOString(),
    scanned_limit: options.maxScan,
    articles: samples,
  });

  printJson({
    ok: true,
    mode: "account",
    output,
    count: samples.length,
    account: { nickname: String(account.nickname ?? options.account), alias: String(account.alias ?? "") },
    articles: samples.map((item) => ({ title: item.title, link: item.link, publish_time: item.publish_time })),
  });
}

async function main() {
  const options = parseArgs();
  await assertExecutableFile(options.wxHunter, "wx-mp-hunter wrapper");

  if (options.mode === "url") {
    await collectByUrl(options);
    return;
  }
  await collectByAccount(options);
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  fail(message);
});
