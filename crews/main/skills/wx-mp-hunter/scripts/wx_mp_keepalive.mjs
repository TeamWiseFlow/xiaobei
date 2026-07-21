/**
 * wx-mp 登录扫码间隙 keep-alive。
 *
 * 背景：camoufox-cli daemon 有 60s 空闲超时（hard max，见 cli.ts:737）。
 * `login` 截 QR 后到 `login-confirm` 开始轮询之间，若用户扫码 >60s 无任何命令，
 * daemon 自退 → 浏览器死 → scanloginqrcode 页服务端轮询死 → 手机「确认登录」无落地。
 *
 * 本脚本由 cmdLoginQr detached spawn，每 20s ping 一次 daemon（eval 1）撑过 60s 超时，
 * 直到 login-confirm 接管轮询（kill 本进程）或自身 5min 上限到。全程吞错——
 * daemon 挂了就挂了，login-confirm 会诊断。
 *
 * 用法：node wx_mp_keepalive.mjs <session> [camoufox_cli_path]
 */
import { spawn } from "node:child_process";

const session = process.argv[2] ?? "wx_mp";
const cli = process.argv[3] ?? "camoufox-cli";
const INTERVAL_MS = 20_000;
const MAX_MS = 5 * 60_000;

const start = Date.now();
while (Date.now() - start < MAX_MS) {
  try {
    // eval 1 是最轻的命令，只为重置 daemon idle timer。--json 静默输出。
    const p = spawn(cli, ["--session", session, "--persistent", "--json", "eval", "1"], {
      stdio: "ignore",
    });
    p.on("error", () => {}); // cli 不在 PATH 等忽略
    // 不等结果——发出去即达重置 idle timer 目的
  } catch {
    // 吞错继续
  }
  await new Promise((r) => setTimeout(r, INTERVAL_MS));
}
