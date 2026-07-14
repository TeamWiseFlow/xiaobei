import { describe, it, expect, vi, afterEach } from "vitest";
import { assetsViaWeb, iterReleaseAssets } from "../src/install.js";

const RELEASES_PAGE_1 =
  '<a href="/daijro/camoufox/releases/tag/v150.0.2-beta.25">x</a>' +
  '<a href="/daijro/camoufox/releases/tag/v150.0.2-beta.25">dup</a>' +
  '<a href="/daijro/camoufox/releases/tag/v135.0.1-beta.24">x</a>';
const RELEASES_PAGE_2 = '<a href="/daijro/camoufox/releases/tag/v135.0.1-beta.23">x</a>';

const EXPANDED_25 = '<a href="/daijro/camoufox/releases/download/v150.0.2-beta.25/camoufox-150.0.2-alpha.25-lin.x86_64.zip">a</a>';
const EXPANDED_24 =
  '<a href="/daijro/camoufox/releases/download/v135.0.1-beta.24/camoufox-135.0.1-beta.24-lin.x86_64.zip">a</a>' +
  '<a href="/daijro/camoufox/releases/download/v135.0.1-beta.24/camoufox-135.0.1-beta.24-mac.arm64.zip">a</a>';
const EXPANDED_23 = '<a href="/daijro/camoufox/releases/download/v135.0.1-beta.23/camoufox-135.0.1-beta.23-lin.x86_64.zip">a</a>';

function fakeResponse(opts: { status?: number; text?: string; json?: unknown }) {
  const status = opts.status ?? 200;
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => opts.text ?? "",
    json: async () => opts.json,
  };
}

function routeFetch(routes: Record<string, ReturnType<typeof fakeResponse> | Error>) {
  const calls: Array<[string, RequestInit | undefined]> = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push([url, init]);
    for (const [prefix, resp] of Object.entries(routes)) {
      if (url.startsWith(prefix)) {
        if (resp instanceof Error) throw resp;
        return resp;
      }
    }
    throw new Error(`unexpected URL: ${url}`);
  }));
  return calls;
}

const WEB_ROUTES = {
  "https://github.com/daijro/camoufox/releases?page=1": fakeResponse({ text: RELEASES_PAGE_1 }),
  "https://github.com/daijro/camoufox/releases?page=2": fakeResponse({ text: RELEASES_PAGE_2 }),
  "https://github.com/daijro/camoufox/releases?page=": fakeResponse({ text: "<html>no releases</html>" }),
  "https://github.com/daijro/camoufox/releases/expanded_assets/v150.0.2-beta.25": fakeResponse({ text: EXPANDED_25 }),
  "https://github.com/daijro/camoufox/releases/expanded_assets/v135.0.1-beta.24": fakeResponse({ text: EXPANDED_24 }),
  "https://github.com/daijro/camoufox/releases/expanded_assets/v135.0.1-beta.23": fakeResponse({ text: EXPANDED_23 }),
};

async function collect(iter: AsyncGenerator<any>): Promise<any[]> {
  const out: any[] = [];
  for await (const item of iter) out.push(item);
  return out;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("iterReleaseAssets", () => {
  it("flattens assets across releases from the API", async () => {
    const a1 = { name: "one.zip", browser_download_url: "u1" };
    const a2 = { name: "two.zip", browser_download_url: "u2" };
    const a3 = { name: "three.zip", browser_download_url: "u3" };
    const calls = routeFetch({
      "https://api.github.com/repos/daijro/camoufox/releases": fakeResponse({
        json: [{ assets: [a1, a2] }, { assets: [a3] }],
      }),
    });
    expect(await collect(iterReleaseAssets("daijro/camoufox"))).toEqual([a1, a2, a3]);
    expect(calls).toHaveLength(1);
  });

  it("falls back to github.com pages when the API is rate-limited", async () => {
    routeFetch({
      "https://api.github.com": fakeResponse({ status: 403 }),
      ...WEB_ROUTES,
    });
    const assets = await collect(iterReleaseAssets("daijro/camoufox"));
    expect(assets.map((a) => a.name)).toEqual([
      "camoufox-150.0.2-alpha.25-lin.x86_64.zip",
      "camoufox-135.0.1-beta.24-lin.x86_64.zip",
      "camoufox-135.0.1-beta.24-mac.arm64.zip",
      "camoufox-135.0.1-beta.23-lin.x86_64.zip",
    ]);
  });

  it("falls back to github.com pages on network errors", async () => {
    routeFetch({
      "https://api.github.com": new Error("no route"),
      ...WEB_ROUTES,
    });
    const assets = await collect(iterReleaseAssets("daijro/camoufox"));
    expect(assets[0].browser_download_url).toMatch(
      /^https:\/\/github\.com\/daijro\/camoufox\/releases\/download\//,
    );
  });
});

describe("assetsViaWeb", () => {
  it("parses asset names and absolute download URLs", async () => {
    routeFetch(WEB_ROUTES);
    const assets = await collect(assetsViaWeb("daijro/camoufox"));
    expect(assets[0]).toEqual({
      name: "camoufox-150.0.2-alpha.25-lin.x86_64.zip",
      browser_download_url:
        "https://github.com/daijro/camoufox/releases/download/v150.0.2-beta.25/camoufox-150.0.2-alpha.25-lin.x86_64.zip",
    });
    expect(assets).toHaveLength(4);
  });

  it("paginates until a page has no new tags", async () => {
    const calls = routeFetch(WEB_ROUTES);
    const assets = await collect(assetsViaWeb("daijro/camoufox"));
    expect(assets[assets.length - 1].name).toBe("camoufox-135.0.1-beta.23-lin.x86_64.zip");
    const listingCalls = calls.map(([u]) => u).filter((u) => u.includes("?page="));
    expect(listingCalls).toEqual([
      "https://github.com/daijro/camoufox/releases?page=1",
      "https://github.com/daijro/camoufox/releases?page=2",
      "https://github.com/daijro/camoufox/releases?page=3",
    ]);
  });

  it("stops when pages keep repeating the same tags", async () => {
    routeFetch({
      "https://github.com/daijro/camoufox/releases?page=": fakeResponse({ text: RELEASES_PAGE_2 }),
      "https://github.com/daijro/camoufox/releases/expanded_assets/v135.0.1-beta.23": fakeResponse({ text: EXPANDED_23 }),
    });
    const assets = await collect(assetsViaWeb("daijro/camoufox"));
    expect(assets.map((a) => a.name)).toEqual(["camoufox-135.0.1-beta.23-lin.x86_64.zip"]);
  });

  it("stops requesting once the caller stops (lazy)", async () => {
    const calls = routeFetch(WEB_ROUTES);
    const iter = assetsViaWeb("daijro/camoufox");
    const first = await iter.next();
    expect(first.value.name).toBe("camoufox-150.0.2-alpha.25-lin.x86_64.zip");
    expect(calls).toHaveLength(2);
  });

  it("skips unavailable release pages", async () => {
    routeFetch({
      ...WEB_ROUTES,
      "https://github.com/daijro/camoufox/releases/expanded_assets/v150.0.2-beta.25": fakeResponse({ status: 404 }),
    });
    const assets = await collect(assetsViaWeb("daijro/camoufox"));
    expect(assets.map((a) => a.name)).toEqual([
      "camoufox-135.0.1-beta.24-lin.x86_64.zip",
      "camoufox-135.0.1-beta.24-mac.arm64.zip",
      "camoufox-135.0.1-beta.23-lin.x86_64.zip",
    ]);
  });
});
