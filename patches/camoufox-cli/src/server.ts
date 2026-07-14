/** Unix socket server for the camoufox-cli daemon. */

import * as net from "node:net";
import * as fs from "node:fs";
import { BrowserManager } from "./browser.js";
import { execute } from "./commands.js";
import { parseCommand, serializeResponse, errorResponse } from "./protocol.js";
import { getSocketPath, getPidPath } from "./cli.js";

export class DaemonServer {
  private session: string;
  private headless: boolean;
  private timeout: number;
  private socketPath: string;
  private pidPath: string;
  private manager: BrowserManager;
  private server: net.Server | null = null;
  private lastActivity = Date.now();
  private watchdogTimer: ReturnType<typeof setInterval> | null = null;
  // Fail-first queue: a session runs one command at a time. A command that
  // arrives while another is mid-flight fails immediately with guidance text
  // (no hidden queueing/waiting) — see spec §1.1. `close` bypasses this so a
  // stuck session can always be torn down.
  private busy = false;
  // Active client connections. Tracked so `close` can force-destroy them and
  // the server's 'close' event fires promptly even when an in-flight command
  // is hung on something that doesn't react to browser teardown — notably
  // `wait <ms>`, whose `page.waitForTimeout` is a standalone setTimeout that
  // neither rejects on context close nor releases the event loop. Without this,
  // `wait 999999999` + `close` leaves the daemon lingering (socket/pid leak).
  private activeConnections = new Set<net.Socket>();
  // When true (daemon entry point), shutdown() ends with process.exit(0) so a
  // stray timer from an interrupted command can't keep the detached daemon
  // alive. In-process tests pass false and let the event loop drain naturally.
  private forceExit: boolean;

  constructor(opts: { session?: string; headless?: boolean; timeout?: number; persistent?: string | null; proxy?: string | null; geoip?: boolean; locale?: string | null; forceExit?: boolean }) {
    this.session = opts.session ?? "default";
    this.headless = opts.headless ?? true;
    this.timeout = opts.timeout ?? 1800;
    this.socketPath = getSocketPath(this.session);
    this.pidPath = getPidPath(this.session);
    this.manager = new BrowserManager(opts.persistent ?? null, opts.proxy ?? null, opts.geoip ?? true, opts.locale ?? null);
    this.forceExit = opts.forceExit ?? false;
  }

  async start(): Promise<void> {
    this.cleanupStale();
    this.writePid();
    // Idle timeout watchdog
    this.watchdogTimer = setInterval(() => {
      if (Date.now() - this.lastActivity > this.timeout * 1000) {
        process.stderr.write(`[camoufox-cli] Idle timeout (${this.timeout}s), shutting down\n`);
        this.server?.close();
      }
    }, 10000);

    // Signal handlers
    process.on("SIGTERM", () => { this.server?.close(); });
    process.on("SIGINT", () => { this.server?.close(); });

    this.server = net.createServer({ allowHalfOpen: true }, (conn) => this.handleConnection(conn));

    await new Promise<void>((resolve, reject) => {
      this.server!.listen(this.socketPath, () => resolve());
      this.server!.on("error", reject);
    });

    process.stderr.write(`[camoufox-cli] Daemon listening session=${this.session}\n`);

    // Wait until server closes
    await new Promise<void>((resolve) => {
      this.server!.on("close", resolve);
    });

    await this.shutdown();
  }

  private handleConnection(conn: net.Socket): void {
    this.activeConnections.add(conn);
    conn.on("close", () => { this.activeConnections.delete(conn); });
    conn.on("error", () => { this.activeConnections.delete(conn); });

    let data = "";
    let handled = false;

    const processData = async () => {
      if (handled) return;
      const nlIdx = data.indexOf("\n");
      if (nlIdx < 0) return;
      handled = true;

      this.lastActivity = Date.now();
      const line = data.slice(0, nlIdx).trim();
      if (!line) { conn.destroy(); return; }

      let command: { id?: string; action?: string; params?: Record<string, unknown> };
      try {
        command = parseCommand(line);
      } catch (e: any) {
        conn.end(Buffer.from(JSON.stringify({ id: "?", success: false, error: String(e) }) + "\n"));
        return;
      }

      const action = command.action ?? "";
      const cmdId = (command.id as string) || "?";

      // `close` is the recovery escape hatch — always allowed, even while a
      // previous command is mid-flight (it tears the daemon down anyway).
      if (action !== "close" && this.busy) {
        conn.end(serializeResponse(
          errorResponse(cmdId, `session ${this.session} 正忙，请等待当前操作完成后再试`),
        ));
        return;
      }

      this.busy = true;
      try {
        if (action === "open") {
          (command.params as Record<string, unknown>).headless ??= this.headless;
        }

        const response = await execute(this.manager, command as any);
        conn.end(serializeResponse(response));

        if (action === "close") {
          // Stop accepting new connections, then force-destroy every OTHER
          // active connection so the server's 'close' event fires even if a
          // prior command is stuck on a timer that won't release (e.g. wait
          // <ms>). This connection is left alone — conn.end() above already
          // half-closes it after flushing the response to the client.
          this.server?.close();
          for (const c of this.activeConnections) {
            if (c === conn) continue;
            try { c.destroy(); } catch {}
          }
        }
      } catch (e: any) {
        conn.end(Buffer.from(JSON.stringify({ id: cmdId, success: false, error: String(e) }) + "\n"));
      } finally {
        this.busy = false;
      }
    };

    conn.on("data", (chunk) => {
      data += chunk.toString();
      processData();
    });

    conn.on("end", () => { processData(); });
  }

  private cleanupStale(): void {
    if (fs.existsSync(this.socketPath)) {
      if (fs.existsSync(this.pidPath)) {
        try {
          const pid = parseInt(fs.readFileSync(this.pidPath, "utf-8").trim(), 10);
          process.kill(pid, 0); // Check if alive
          process.stderr.write(`[camoufox-cli] Daemon already running (pid ${pid})\n`);
          process.exit(1);
        } catch {
          // Stale pid, clean up
        }
      }
      fs.unlinkSync(this.socketPath);
    }
  }

  private writePid(): void {
    fs.writeFileSync(this.pidPath, String(process.pid));
  }

  private async shutdown(): Promise<void> {
    if (this.watchdogTimer) clearInterval(this.watchdogTimer);
    await this.manager.close();
    if (this.server) {
      try { this.server.close(); } catch {}
    }
    for (const c of this.activeConnections) {
      try { c.destroy(); } catch {}
    }
    for (const p of [this.socketPath, this.pidPath]) {
      try { fs.unlinkSync(p); } catch {}
    }
    // A command interrupted mid-flight (e.g. wait <ms>) may have left a
    // standalone setTimeout keeping the event loop alive. The detached daemon
    // must exit deterministically so its socket/pid are reclaimed.
    if (this.forceExit) process.exit(0);
  }
}
