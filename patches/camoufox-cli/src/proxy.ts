export interface ProxySettings {
  proxy: {
    server: string;
    username?: string;
    password?: string;
  };
}

export function parseProxySettings(proxyUrl: string): ProxySettings {
  if (!proxyUrl.includes("://")) {
    throw new Error(
      `Invalid proxy URL: ${proxyUrl}. Expected format: http(s)://host:port`
    );
  }

  const parsed = new URL(proxyUrl);
  const scheme = parsed.protocol.slice(0, -1).toLowerCase();
  if (scheme !== "http" && scheme !== "https") {
    throw new Error(
      `Unsupported proxy scheme: ${scheme}. Only http:// and https:// proxies are supported.`
    );
  }
  if (!parsed.hostname) {
    throw new Error(
      `Invalid proxy URL: ${proxyUrl}. Expected format: ${scheme}://host:port`
    );
  }

  const hostPort = parsed.port ? `${parsed.hostname}:${parsed.port}` : parsed.hostname;
  const proxy: ProxySettings["proxy"] = { server: `${scheme}://${hostPort}` };
  const username = parsed.username ? decodeURIComponent(parsed.username) : "";
  const password = parsed.password ? decodeURIComponent(parsed.password) : "";

  if (parsed.username) {
    proxy.username = username;
    proxy.password = password;
  }

  return { proxy };
}
