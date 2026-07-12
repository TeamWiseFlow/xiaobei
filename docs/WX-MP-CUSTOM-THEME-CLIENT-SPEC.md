# wx-mp 自定义主题 — client 实现契约

> 本文件是 relay 仓写给 **client 仓维护者**的实现说明。relay 侧已落地，client 侧按本文更新即可。
> 唯一耦合面见 [API-CONTRACT.md](./API-CONTRACT.md) §wx-mp；迁移背景见 [CLIENT-MIGRATION.md](./CLIENT-MIGRATION.md) §3。
>
> 状态：relay 已实现并部署（2026-07-12）。client 侧待实现。

## 1. 背景

`generate-wenyan-theme` 技能在 client 本地生成自定义 CSS 主题文件，并把 `theme-id` 登记到 `wx-mp-publisher/SKILL.md` 主题表。`wx-mp-publisher` 经 relay 发布（`POST /api/v1/wx-mp/publish`，relay 导入 `@wenyan-md/core` 作为库渲染）。

**问题**：relay 旧端点只接受 `theme`（内置主题 id 文本），自定义 CSS 没有路径到达 relay，自定义主题在 relay 模式下静默失效。

**方案**：relay 新增 `custom_theme` multipart 文本字段（CSS 内容）。client 发布时把本地 `.css` 内容读出作为该字段上传；relay 写到 per-request 临时目录、渲染后即清理，**不持久化、不落盘、天然用户隔离**。主题登记表（id → 本地 CSS 路径映射）只存在 client 侧。

## 2. relay 侧契约（已实现）

`POST /api/v1/wx-mp/publish` multipart 新增字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `custom_theme` | text | 否 | 自定义主题 CSS 文本内容 |

- `theme`（内置 id）与 `custom_theme`（CSS 文本）同时给时，**`custom_theme` 优先**（与 wenyan-cli `--custom-theme` 一致）。
- relay 把 `custom_theme` 写到 per-request 临时目录 `custom-theme.css`，作为 `customTheme` 路径传给 `@wenyan-md/core` 的 `prepareRenderContext`（core 的 `renderWithTheme` 读磁盘路径 → `readFileContent`）。
- 请求结束 `finally` 清理临时目录，不落盘、不记日志、不按用户存主题。
- 新错误码：`INVALID_CUSTOM_THEME`（400，`custom_theme` 非字符串）。
- multer `fieldSize` 上限 2MB（主题 CSS 通常 <50KB，留足余量）。

## 3. client 侧需改动（3 个文件）

### 3.1 `crews/main/skills/wx-mp-publisher/scripts/publish_wx_mp.py`

**新增主题解析**：`theme` 位置参数三种形态 →

1. **本地 `.css` 文件路径** → 读文件内容，作为 `custom_theme` 字段上传。
2. **SKILL.md 主题表登记的自定义 id**（描述含「用户自定义」）→ 解析出对应 CSS 路径 → 同 (1)。
3. **其它**（`pie`/`lapis`/`default`/…）→ 内置主题 id，作为 `theme` 字段原样传（现行行为）。

**参考实现**（已在本机冒烟测试通过，可直接采用或按需调整）：

```python
# 模块级常量（与现有 SCRIPT_DIR 同处）
SKILL_MD = SCRIPT_DIR.parent / "SKILL.md"
CREW_WORKSPACE = SCRIPT_DIR.parent.parent.parent  # crews/main


def _resolve_registered_theme_path(theme_id: str) -> Path | None:
    """从 SKILL.md 主题表查登记的自定义主题 id，返回 CSS 文件路径或 None。"""
    if not SKILL_MD.exists():
        return None
    pattern = re.compile(rf"^\| `{re.escape(theme_id)}` \|.*用户自定义")
    for line in SKILL_MD.read_text(encoding="utf-8").splitlines():
        if not pattern.match(line):
            continue
        m = re.search(r"文件：`([^`]+)`", line)
        if not m:
            return None
        p = Path(m.group(1))
        if p.is_file():
            return p
        alt = CREW_WORKSPACE / m.group(1)
        if alt.is_file():
            return alt
        return None
    return None


def resolve_theme(theme_arg: str | None) -> tuple[str, str] | None:
    """返回 ('theme', id) / ('custom_theme', css_text) / None。"""
    if not theme_arg:
        return None
    p = Path(theme_arg)
    if theme_arg.endswith(".css") and p.is_file():
        return ("custom_theme", p.read_text(encoding="utf-8"))
    css_path = _resolve_registered_theme_path(theme_arg)
    if css_path is not None:
        return ("custom_theme", css_path.read_text(encoding="utf-8"))
    return ("theme", theme_arg)
```

**main() 接线**（替换现行 `if args.theme: fields["theme"] = args.theme`）：

```python
theme_field = resolve_theme(args.theme)
if theme_field is not None:
    fields[theme_field[0]] = theme_field[1]
```

**argparse help 更新**：

```python
parser.add_argument(
    "theme", nargs="?", default=None,
    help="主题：内置 id（pie/lapis/default/…）/ 本地 .css 路径 / SKILL.md 登记的自定义 id",
)
```

**日志建议**：custom_theme 时打印字节数与「随请求上传 relay 不持久化」，方便排障。

### 3.2 `crews/main/skills/wx-mp-publisher/SKILL.md`

- `theme` 参数说明改为三种形态（内置 id / 本地 `.css` 路径 / 登记的自定义 id）。
- 主题表末尾保留一行自定义主题占位（供 `generate-wenyan-theme` 追加）：

  ```markdown
  | `<custom-theme>` | 用户自定义主题占位（由 `generate-wenyan-theme` 生成后更新，文件：`<custom-theme>.css`） | 用户明确指定参考该主题时优先采用；相似内容可优先建议 |
  ```

- 加一句声明：**自定义主题不持久化**——relay 无状态多租户中转，不存任何用户主题；CSS 随请求上传、per-request 临时目录渲染后清理，天然按用户隔离。登记表只是 client 侧 id → 本地 CSS 路径映射。

### 3.3 `crews/main/skills/generate-wenyan-theme/SKILL.md`

「生成主题注册规则」与「与 wx-mp-publisher 配合使用」两段：

- 明确登记表是 **client 侧 id → 本地 CSS 路径映射**，relay 不存主题。
- 发布命令统一用 `python3 ./skills/wx-mp-publisher/scripts/publish_wx_mp.py article.md <theme>`（不是旧的 `publish-wx-mp.sh`，也不是 wenyan-cli）。
- 说明发布时脚本读 CSS 内容作 `custom_theme` 字段随 multipart 上传 relay，relay 写 per-request 临时目录调 `@wenyan-md/core` 渲染、请求结束即清理，**不持久化、不落盘、不按用户存主题**。

## 4. 验证

1. **relay 侧**（已通过）：`cd services/tx-relay/wx-mp-proxy && node --test` → 21/21 pass，含 3 个 `custom_theme` 新用例。
2. **client 侧**（实现后自测）：
   - 内置 id：`resolve_theme("pie")` → `('theme', 'pie')`
   - 本地 `.css`：`resolve_theme("/tmp/t.css")` → `('custom_theme', '<文件内容>')`
   - 登记 id：在 SKILL.md 主题表加一行 `| \`myt\` | 用户自定义：…（文件：\`./myt.css\`） | … |` 后 `resolve_theme("myt")` → `('custom_theme', '<内容>')`
   - 端到端：用自定义主题发布一篇测试稿，确认 relay 日志无 `INVALID_CUSTOM_THEME`、返回 `media_id`、公众号草稿箱样式生效。
3. **回归**：不传 theme / 传内置 id 两种路径行为不变。

## 5. 非目标

- **不做** relay 侧持久主题库（`/wx-mp/themes` CRUD、按用户落盘、配额、清理）。CSS 极小、client 本就持有文件、无状态原则一致、用户隔离自动达成。若将来确有跨设备共享且不靠 workspace 同步的需求，再开 Phase 2 另行设计。
- relay 不改 `theme` 字段语义（仍是内置 id 文本），不破坏现有调用方。
