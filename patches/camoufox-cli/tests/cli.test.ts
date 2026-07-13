import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { buildCommand, getSocketPath, getPidPath, shortenSession, parseArgs } from "../src/cli.js";
import { loadDefaults } from "../src/config.js";

// buildCommand calls process.exit on error; mock it to throw instead
beforeEach(() => {
  vi.spyOn(process, "exit").mockImplementation((code) => {
    throw new Error(`process.exit(${code})`);
  });
  vi.spyOn(process.stderr, "write").mockImplementation(() => true);
  // Isolate from any real ~/.camoufox-cli/config.json on the dev's machine.
  process.env.CAMOUFOX_CLI_CONFIG = path.join(os.tmpdir(), "camoufox-cli-absent-dir", "config.json");
});

describe("buildCommand", () => {
  // --- Navigation ---
  it("open", () => {
    const cmd = buildCommand("open", ["open", "https://example.com"]);
    expect(cmd.action).toBe("open");
    expect((cmd.params as any).url).toBe("https://example.com");
  });

  it("back", () => {
    const cmd = buildCommand("back", ["back"]);
    expect(cmd.action).toBe("back");
  });

  it("forward", () => {
    const cmd = buildCommand("forward", ["forward"]);
    expect(cmd.action).toBe("forward");
  });

  it("reload", () => {
    const cmd = buildCommand("reload", ["reload"]);
    expect(cmd.action).toBe("reload");
  });

  it("url", () => {
    const cmd = buildCommand("url", ["url"]);
    expect(cmd.action).toBe("url");
  });

  it("title", () => {
    const cmd = buildCommand("title", ["title"]);
    expect(cmd.action).toBe("title");
  });

  it("close", () => {
    const cmd = buildCommand("close", ["close"]);
    expect(cmd.action).toBe("close");
  });

  it("close --all", () => {
    const cmd = buildCommand("close", ["close", "--all"]);
    expect((cmd.params as any).all).toBe(true);
  });

  // --- Snapshot ---
  it("snapshot basic", () => {
    const cmd = buildCommand("snapshot", ["snapshot"]);
    expect(cmd.action).toBe("snapshot");
    expect((cmd.params as any).interactive).toBe(false);
  });

  it("snapshot interactive", () => {
    const cmd = buildCommand("snapshot", ["snapshot", "-i"]);
    expect((cmd.params as any).interactive).toBe(true);
  });

  it("snapshot scoped", () => {
    const cmd = buildCommand("snapshot", ["snapshot", "-s", "#main"]);
    expect((cmd.params as any).selector).toBe("#main");
  });

  // --- Interaction ---
  it("click", () => {
    const cmd = buildCommand("click", ["click", "@e1"]);
    expect(cmd.action).toBe("click");
    expect((cmd.params as any).ref).toBe("@e1");
  });

  it("fill", () => {
    const cmd = buildCommand("fill", ["fill", "@e1", "hello"]);
    expect((cmd.params as any).ref).toBe("@e1");
    expect((cmd.params as any).text).toBe("hello");
  });

  it("type", () => {
    const cmd = buildCommand("type", ["type", "@e1", "hello"]);
    expect((cmd.params as any).ref).toBe("@e1");
    expect((cmd.params as any).text).toBe("hello");
  });

  it("select", () => {
    const cmd = buildCommand("select", ["select", "@e1", "Option A"]);
    expect((cmd.params as any).ref).toBe("@e1");
    expect((cmd.params as any).value).toBe("Option A");
  });

  it("check", () => {
    const cmd = buildCommand("check", ["check", "@e1"]);
    expect((cmd.params as any).ref).toBe("@e1");
  });

  it("hover", () => {
    const cmd = buildCommand("hover", ["hover", "@e1"]);
    expect((cmd.params as any).ref).toBe("@e1");
  });

  it("press", () => {
    const cmd = buildCommand("press", ["press", "Enter"]);
    expect((cmd.params as any).key).toBe("Enter");
  });

  // --- Data extraction ---
  it("text", () => {
    const cmd = buildCommand("text", ["text", "@e1"]);
    expect((cmd.params as any).target).toBe("@e1");
  });

  it("eval", () => {
    const cmd = buildCommand("eval", ["eval", "document.title"]);
    expect((cmd.params as any).expression).toBe("document.title");
  });

  it("screenshot with path", () => {
    const cmd = buildCommand("screenshot", ["screenshot", "out.png"]);
    expect((cmd.params as any).path).toBe("out.png");
  });

  it("screenshot --full with path", () => {
    const cmd = buildCommand("screenshot", ["screenshot", "--full", "out.png"]);
    expect((cmd.params as any).full_page).toBe(true);
    expect((cmd.params as any).path).toBe("out.png");
  });

  it("screenshot no args", () => {
    const cmd = buildCommand("screenshot", ["screenshot"]);
    expect((cmd.params as any).path).toBeUndefined();
  });

  it("pdf", () => {
    const cmd = buildCommand("pdf", ["pdf", "output.pdf"]);
    expect(cmd.action).toBe("pdf");
    expect((cmd.params as any).path).toBe("output.pdf");
  });

  // --- Scroll & Wait ---
  it("scroll down default", () => {
    const cmd = buildCommand("scroll", ["scroll", "down"]);
    expect((cmd.params as any).direction).toBe("down");
    expect((cmd.params as any).amount).toBe(500);
  });

  it("scroll up custom amount", () => {
    const cmd = buildCommand("scroll", ["scroll", "up", "300"]);
    expect((cmd.params as any).direction).toBe("up");
    expect((cmd.params as any).amount).toBe(300);
  });

  it("wait ms", () => {
    const cmd = buildCommand("wait", ["wait", "2000"]);
    expect((cmd.params as any).ms).toBe(2000);
  });

  it("wait ref", () => {
    const cmd = buildCommand("wait", ["wait", "@e1"]);
    expect((cmd.params as any).ref).toBe("@e1");
  });

  it("wait selector", () => {
    const cmd = buildCommand("wait", ["wait", "#loading"]);
    expect((cmd.params as any).selector).toBe("#loading");
  });

  it("wait --url", () => {
    const cmd = buildCommand("wait", ["wait", "--url", "*/dashboard"]);
    expect((cmd.params as any).url).toBe("*/dashboard");
  });

  // --- Tabs ---
  it("tabs", () => {
    const cmd = buildCommand("tabs", ["tabs"]);
    expect(cmd.action).toBe("tabs");
  });

  it("switch", () => {
    const cmd = buildCommand("switch", ["switch", "2"]);
    expect((cmd.params as any).index).toBe(2);
  });

  it("close-tab", () => {
    const cmd = buildCommand("close-tab", ["close-tab"]);
    expect(cmd.action).toBe("close-tab");
  });

  // --- Session ---
  it("sessions", () => {
    const cmd = buildCommand("sessions", ["sessions"]);
    expect(cmd.action).toBe("sessions");
  });

  it("install", () => {
    const cmd = buildCommand("install", ["install"]);
    expect(cmd.action).toBe("install");
  });

  it("install --with-deps", () => {
    const cmd = buildCommand("install", ["install", "--with-deps"]);
    expect((cmd.params as any).with_deps).toBe(true);
  });

  // --- Cookies ---
  it("cookies list", () => {
    const cmd = buildCommand("cookies", ["cookies"]);
    expect((cmd.params as any).op).toBe("list");
  });

  it("cookies export", () => {
    const cmd = buildCommand("cookies", ["cookies", "export", "c.json"]);
    expect((cmd.params as any).op).toBe("export");
    expect((cmd.params as any).path).toBe("c.json");
  });

  it("cookies import", () => {
    const cmd = buildCommand("cookies", ["cookies", "import", "c.json"]);
    expect((cmd.params as any).op).toBe("import");
    expect((cmd.params as any).path).toBe("c.json");
  });

  // --- Identity ---
  it("identity show (default)", () => {
    const cmd = buildCommand("identity", ["identity"]);
    expect(cmd.action).toBe("identity");
    expect((cmd.params as any).op).toBe("show");
  });

  it("identity export", () => {
    const cmd = buildCommand("identity", ["identity", "export", "ua.json"]);
    expect((cmd.params as any).op).toBe("export");
    expect((cmd.params as any).path).toBe("ua.json");
  });

  // --- Upload ---
  it("upload single file via ref", () => {
    const cmd = buildCommand("upload", ["upload", "@e1", "/tmp/a.png"]);
    expect(cmd.action).toBe("upload");
    expect((cmd.params as any).ref).toBe("@e1");
    expect((cmd.params as any).paths).toEqual(["/tmp/a.png"]);
  });

  it("upload multiple files via selector", () => {
    const cmd = buildCommand("upload", ["upload", "input[type=file]", "/tmp/a.png", "/tmp/b.png"]);
    expect((cmd.params as any).selector).toBe("input[type=file]");
    expect((cmd.params as any).paths).toEqual(["/tmp/a.png", "/tmp/b.png"]);
  });

  it("upload missing files exits", () => {
    expect(() => buildCommand("upload", ["upload", "@e1"])).toThrow("process.exit");
  });

  // --- Error cases ---
  it("unknown command exits", () => {
    expect(() => buildCommand("nonexistent", ["nonexistent"])).toThrow("process.exit");
  });

  it("open missing url exits", () => {
    expect(() => buildCommand("open", ["open"])).toThrow("process.exit");
  });

  it("click missing ref exits", () => {
    expect(() => buildCommand("click", ["click"])).toThrow("process.exit");
  });

  it("fill missing text exits", () => {
    expect(() => buildCommand("fill", ["fill", "@e1"])).toThrow("process.exit");
  });

  it("pdf missing path exits", () => {
    expect(() => buildCommand("pdf", ["pdf"])).toThrow("process.exit");
  });

  it("switch missing index exits", () => {
    expect(() => buildCommand("switch", ["switch"])).toThrow("process.exit");
  });

  // --- ID field ---
  it("all commands have id=r1", () => {
    const cmd = buildCommand("back", ["back"]);
    expect(cmd.id).toBe("r1");
  });
});

describe("parseArgs", () => {
  it("defaults", () => {
    const { flags } = parseArgs(["open", "https://example.com"]);
    expect(flags.session).toBe("default");
    expect(flags.headed).toBe(false);
    expect(flags.timeout).toBe(1800);
    expect(flags.json).toBe(false);
    expect(flags.persistent).toBeNull();
    expect(flags.proxy).toBeNull();
    expect(flags.geoip).toBe(true);
  });

  it("--no-geoip flag", () => {
    const { flags } = parseArgs(["--no-geoip", "open", "https://example.com"]);
    expect(flags.geoip).toBe(false);
  });

  it("--proxy flag", () => {
    const { flags } = parseArgs(["--proxy", "http://127.0.0.1:8080", "open", "https://example.com"]);
    expect(flags.proxy).toBe("http://127.0.0.1:8080");
  });

  it("--proxy with auth", () => {
    const { flags } = parseArgs(["--proxy", "http://user:pass@host:8080", "open", "https://example.com"]);
    expect(flags.proxy).toBe("http://user:pass@host:8080");
  });

  it("--proxy missing value exits", () => {
    expect(() => parseArgs(["--proxy"])).toThrow("process.exit");
  });
});

describe("getSocketPath", () => {
  it("default session", () => {
    expect(getSocketPath("default")).toBe("/tmp/camoufox-cli-default.sock");
  });

  it("custom session", () => {
    expect(getSocketPath("my-session")).toBe("/tmp/camoufox-cli-my-session.sock");
  });
});

describe("getPidPath", () => {
  it("default session", () => {
    expect(getPidPath("default")).toBe("/tmp/camoufox-cli-default.pid");
  });

  it("custom session", () => {
    expect(getPidPath("my-session")).toBe("/tmp/camoufox-cli-my-session.pid");
  });
});

describe("shortenSession", () => {
  it("short session unchanged", () => {
    expect(shortenSession("default")).toBe("default");
  });

  it("84-char session unchanged (boundary)", () => {
    const s = "a".repeat(84);
    expect(shortenSession(s)).toBe(s);
  });

  it("85-char session hashed", () => {
    const s = "a".repeat(85);
    const result = shortenSession(s);
    expect(result).toMatch(/^s-[0-9a-f]{16}$/);
    expect(result.length).toBeLessThan(s.length);
  });

  it("long cron session ID hashed", () => {
    const s = "agent-main-cron-2b8125b0-082b-4c2b-bdc6-7fd2193bab9a-run-11c0d125-aeeb-4357-a6d7-11b0517c944a";
    const result = shortenSession(s);
    expect(result).toMatch(/^s-[0-9a-f]{16}$/);
    expect(result.length).toBe(18);
  });

  it("deterministic (same input -> same output)", () => {
    const s = "agent-main-cron-2b8125b0-082b-4c2b-bdc6-7fd2193bab9a-run-11c0d125-aeeb-4357-a6d7-11b0517c944a";
    expect(shortenSession(s)).toBe(shortenSession(s));
  });

  it("different inputs -> different hashes", () => {
    const s1 = "agent-main-cron-aaa".padEnd(100, "a");
    const s2 = "agent-main-cron-bbb".padEnd(100, "b");
    expect(shortenSession(s1)).not.toBe(shortenSession(s2));
  });

  it("socket path stays under 108 chars", () => {
    const longSession = "x".repeat(200);
    const sockPath = getSocketPath(longSession);
    expect(sockPath.length).toBeLessThanOrEqual(108);
  });
});

describe("config file", () => {
  let dir: string;
  let cfg: string;

  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), "camoufox-cli-test-"));
    cfg = path.join(dir, "config.json");
    process.env.CAMOUFOX_CLI_CONFIG = cfg;
  });

  afterEach(() => {
    delete process.env.CAMOUFOX_CLI_CONFIG;
    fs.rmSync(dir, { recursive: true, force: true });
  });

  const write = (obj: unknown) => fs.writeFileSync(cfg, JSON.stringify(obj));

  // --- loadDefaults ---
  it("absent file -> {}", () => {
    expect(loadDefaults("default")).toEqual({});
  });

  it("default block", () => {
    write({ default: { timeout: 60, headed: true } });
    const out = loadDefaults("default");
    expect(out.timeout).toBe(60);
    expect(out.headed).toBe(true);
  });

  it("session overrides default", () => {
    write({ default: { locale: "en-US", timeout: 60 }, sessions: { work: { locale: "zh-CN" } } });
    const out = loadDefaults("work");
    expect(out.locale).toBe("zh-CN"); // session block wins
    expect(out.timeout).toBe(60); // inherited from default block
  });

  it("unknown session uses default block", () => {
    write({ default: { locale: "en-US" }, sessions: { work: { locale: "zh-CN" } } });
    expect(loadDefaults("other").locale).toBe("en-US");
  });

  it("session key excluded", () => {
    write({ default: { session: "ignored", proxy: "http://h:1" } });
    const out = loadDefaults("default") as any;
    expect(out.session).toBeUndefined();
    expect(out.proxy).toBe("http://h:1");
  });

  it("unknown key ignored", () => {
    write({ default: { bogus: 1, headed: true } });
    const out = loadDefaults("default") as any;
    expect(out.bogus).toBeUndefined();
    expect(out.headed).toBe(true);
  });

  it("persistent true -> empty-string sentinel", () => {
    write({ default: { persistent: true } });
    expect(loadDefaults("default").persistent).toBe("");
  });

  it("persistent false -> null", () => {
    write({ default: { persistent: false } });
    expect(loadDefaults("default").persistent).toBeNull();
  });

  it("persistent path kept", () => {
    write({ default: { persistent: "/tmp/p" } });
    expect(loadDefaults("default").persistent).toBe("/tmp/p");
  });

  it("invalid persistent dropped", () => {
    // A number would crash daemon launch; it must be dropped, not passed through.
    write({ default: { persistent: 123, headed: true } });
    const out = loadDefaults("default") as any;
    expect(out.persistent).toBeUndefined();
    expect(out.headed).toBe(true);
  });

  it("persistent null disables", () => {
    write({ default: { persistent: null } });
    expect(loadDefaults("default").persistent).toBeNull();
  });

  it("invalid timeout dropped", () => {
    write({ default: { timeout: "abc", headed: true } });
    const out = loadDefaults("default") as any;
    expect(out.timeout).toBeUndefined();
    expect(out.headed).toBe(true);
  });

  it("timeout bool dropped", () => {
    write({ default: { timeout: true } });
    expect("timeout" in loadDefaults("default")).toBe(false);
  });

  it("timeout float truncated", () => {
    write({ default: { timeout: 3600.9 } });
    expect(loadDefaults("default").timeout).toBe(3600);
  });

  it("invalid proxy dropped", () => {
    // A non-string proxy would crash daemon launch; it must be dropped.
    write({ default: { proxy: 123, locale: "en-US" } });
    const out = loadDefaults("default") as any;
    expect(out.proxy).toBeUndefined();
    expect(out.locale).toBe("en-US");
  });

  it("bool field wrong type dropped", () => {
    write({ default: { headed: "false", geoip: "no" } });
    const out = loadDefaults("default") as any;
    expect(out.headed).toBeUndefined();
    expect(out.geoip).toBeUndefined();
  });

  it("malformed json ignored", () => {
    fs.writeFileSync(cfg, "{not valid json");
    expect(loadDefaults("default")).toEqual({});
  });

  it("non-object top level ignored", () => {
    write([1, 2, 3]);
    expect(loadDefaults("default")).toEqual({});
  });

  // --- parseArgs integration (precedence: CLI > config > built-in) ---
  it("config supplies defaults", () => {
    write({ default: { proxy: "http://h:1", headed: true } });
    const { flags } = parseArgs(["open", "https://example.com"]);
    expect(flags.proxy).toBe("http://h:1");
    expect(flags.headed).toBe(true);
  });

  it("CLI overrides config", () => {
    write({ default: { timeout: 60 } });
    const { flags } = parseArgs(["--timeout", "999", "open", "x"]);
    expect(flags.timeout).toBe(999);
  });

  it("session block applies", () => {
    write({ sessions: { work: { locale: "zh-CN" } } });
    const { flags } = parseArgs(["--session", "work", "open", "x"]);
    expect(flags.locale).toBe("zh-CN");
    // A different session doesn't pick up the "work" block.
    const { flags: f2 } = parseArgs(["open", "x"]);
    expect(f2.locale).toBeNull();
  });
});
