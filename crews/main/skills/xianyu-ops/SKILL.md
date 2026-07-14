---
name: xianyu-ops
description: 闲鱼（goofish.com）商品搜索、查看详情、私信会话管理与回复。通过 forked camoufox-cli 挌久化 session xianyu 完成。当用户要求在闲鱼上搜索商品、查看宝贝、读取或回复私信时触发。
metadata:
  openclaw:
    emoji: 🐟
---

# 闲鱼操作

通过 **camoufox-cli** 持久化 session `xianyu`（一个且只有一个持久化 session，fail-first 队列：同 session 已有命令在跑时新命令直接 fail）在闲鱼（goofish.com）上完成商品搜索、详情查看、私信管理。

> **主力后端 = `target=camoufox`**。下方命令 / 示例只针对 `target=camoufox`。
> **`target=host` / `target=node`**：只按本 skill 的「流程 + 提示事项」走——何时有头 / 何时无头 / 频率限制 / 错误处理约定是**后端无关**的，照本 skill 执行。不要照搬 `camoufox-cli ...` 命令，用你当前后端自带的浏览器工具语义调用即可。

---

## 前置条件

1. 持久化 session `xianyu` 已登录（登录态存 session profile 里）。本 skill 与 login-manager **完全无关**——自管探活 + 登录，**不导出 cookie/UA 落中央存储**。xianyu 不在 login-manager 支持的 5 平台之列。
2. 首次使用 / 登录态失效时，走自管**有头手动**登录流：
   - `camoufox-cli --session xianyu --persistent --headed --json open "https://www.goofish.com"`
   - 告知用户「**闲鱼** 浏览器已打开，请在窗口里手动扫码登录，完成后告诉我」
   - 等用户回复后 `snapshot` 零登录态就位
   - 登录后**close session**——登录态落磁盘 profile，不留进程占内存；本 skill 下次 `--session xianyu --persistent` 重起无头即恢复，用完再 close。

> **不导出 cookie/UA**——登录态只在 session profile 里闭环，不落 `~/.openclaw/logins/`。本 skill 不调用 `cookies export` / `identity export` / `cookies import`。

---

## 必做约束

- 每次操作之间保持 3-5 秒间隔，避免风控触发验证码。
- 发送私信时不要连续发送超过 10 条，每条间隔 30 秒以上。
- 出现"请先登录"、"验证码"、"安全验证"、"异常访问"等提示时，立即停止操作并告知用户需要重新登录。
- **用完即 close 持久化 session `xianyu`**——登录态 + 指纹冻结在磁盘 profile，不留进程占内存；下次操作 `--session xianyu --persistent` 重起无头即恢复。只在 session 卡死时 `camoufox-cli --session xianyu --json close` teardown。
- 同 session 已有命令在跑时，新命令 fail-first（返回 `session xianyu 正忙，请等待当前操作完成后再试`）——读到这条文本就等当前操作完成再重试，不要盲试。

---

## 登录状态检测

在页面加载后，`snapshot` 检查页面是否出现以下关键词，命中则说明需要重新登录或被风控：

```
请先登录 / 登录后     → 需要重新登录
验证码 / 安全验证 / 异常访问 / 访问过于频繁 → 被风控，停止操作
```

---

## URL 格式

| 页面 | URL |
|------|-----|
| 商品搜索 | `https://www.goofish.com/search?q={关键词}` |
| 商品详情 | `https://www.goofish.com/item?id={item_id}` |
| 私信列表 | `https://www.goofish.com/im` |
| 私信会话 | `https://www.goofish.com/im?itemId={item_id}&peerUserId={user_id}` |
| 发布页 | `https://www.goofish.com/publish` |

---

## 工作流程

### 搜索商品（mtop API + 服务端筛选）

> 在已登录 session 的页面里调 goofish 自己的 `mtop.taobao.idlemtopsearch.pc.search`（页面自带 `window.lib.mtop` 签名，无需手搓），价格区间 / 地区交给**服务端**筛 + 分页，而非抓一屏 DOM 本地过滤——更准、更稳、不漏筛。

```
python3 /<workspace 绝对路径>/crews/main/skills/xianyu-ops/scripts/xianyu_search.py \
  --query "iPhone 15" \
  [--min-price 1000] [--max-price 5000] \
  [--province 广东] [--city 深圳] \
  [--limit 30]
```

脚本内部：open 搜索页加载 mtop lib → 逐页 `camoufox-cli eval` 调 `window.lib.mtop.request` → 解析 `data.resultList` → 输出 JSON。

**服务端筛选编码**（脚本内做，agent 不用管）：
- `--min-price` / `--max-price`（元）→ `propValueStr.searchFilter = "priceRange:<min>,<max>;"`，单边用 0 / 99999999 兜底
- `--province` / `--city` → `extraFilterValue = JSON({divisionList:[{province,city}],...})`，city 可单独用
- 任一筛选生效时 `fromFilter=true`，`--limit` 最多 60

**输出**：`{ok, query, filters, count, items:[{item_id,title,price,condition,brand,location,want,url}]}`

**退出码**：0 成功 / 1 通用错（mtop 未就绪 / 响应异常 / 参数错）/ 2 登录态失效 / 3 session 正忙。

**手动 / 后端非 camoufox**：`target=host`/`target=node` 时，按上方筛选语义用当前后端的浏览器工具调 goofish 搜索接口或 DOM，筛选条件同样交服务端（拼 URL 参数或调等价 API），不要抓全量本地过滤。

### 查看商品详情

```
1. camoufox-cli --session xianyu --persistent --json open "https://www.goofish.com/item?id={item_id}"
2. sleep 2-3 加载，snapshot 检测登录状态
3. 用 eval 调 mtop 接口获取详情：
   camoufox-cli --session xianyu --persistent --json eval "window.lib.mtop.request({api:'mtop.taobao.idle.pc.detail',data:{itemId:'{item_id}'},type:'POST',v:'1.0',dataType:'json',needLogin:false,needLoginPC:false,sessionOption:'AutoLoginOnly',ecode:0}).then(r=>JSON.stringify(r)).catch(e=>JSON.stringify({error:String(e)}))"
4. 从返回的 data 中提取：
   - itemDO.title / itemDO.desc / itemDO.soldPrice / itemDO.originalPrice
   - itemDO.wantCnt / itemDO.collectCnt / itemDO.browseCnt
   - itemDO.itemLabelExtList → 找 propertyText="成色"/"品牌"/"分类" 对应的 text
   - itemDO.imageInfos → 图片 URL 列表
   - sellerDO.nick / sellerDO.sellerId / sellerDO.publishCity
   - sellerDO.xianyuSummary / sellerDO.replyRatio24h
5. 若 mtop 不可用（window.lib.mtop 未就绪），改用 snapshot 从 DOM 提取页面上的可见信息
```

### 查看私信列表

```
1. camoufox-cli --session xianyu --persistent --json open "https://www.goofish.com/im"
2. sleep 4-5 加载，snapshot 检测登录状态
3. snapshot 提取会话列表 ref：每个会话包含
   - 对方昵称、商品标题、价格、最后一条消息
   - 未读标记、未读数量
   - click 会话 ref 后从跳转 URL 中解析 itemId 和 peerUserId
4. 若需获取完整 item_id / peer_user_id，逐个 click 会话 ref，从跳转 URL 中提取
```

### 读取私信内容

```
1. 导航到会话页（两种方式）：
   - 已知 item_id + user_id：open "https://www.goofish.com/im?itemId={item_id}&peerUserId={user_id}"
   - 已在私信列表页：click 目标会话 ref
2. sleep 2-3 加载
3. snapshot 确认聊天输入框存在（can_input 为 true）
4. snapshot 提取可见消息列表
```

### 发送私信 / 回复

```
1. 导航到会话页（同"读取私信内容"步骤 1-3）
2. snapshot 拿到聊天输入框 ref
3. camoufox-cli --session xianyu --persistent --json type <输入框-ref> "消息文本"
4. snapshot 找发送按钮 ref → click
5. sleep 1-2，snapshot 确认消息已出现在聊天区域
```

---

## 错误处理

| 情况 | 处理 |
|------|------|
| 页面出现登录墙 | 停止操作，走前置条件的有头手动登录流重登 |
| 触发验证码/风控 | 停止操作，建议用户手动访问 goofish.com 完成验证后重试 |
| mtop 接口不可用 | 改用 snapshot 从 DOM 提取页面可见信息 |
| mtop 返回 SESSION_EXPIRED | 需要重新登录 |
| 商品不存在 | 检查 item_id 是否正确 |
| 聊天输入框不可用 | 确认会话页已正确加载，重试一次 |
| session 正忙（fail-first） | 等当前操作完成再重试，不要盲试 |
