# 平台运行库分发

TikTok、快手、X、微博和 YouTube 五平台工具使用固定的 `xiaobei-platform-backend` 分发包。`runtime-profile.json` 记录包版本、SHA-512、平台注册表校验值、业务资源 SHA-256、依赖和发布资源地址。包内仅保留平台业务与 Relay 签名适配，安装器不再修改包内模块。签名材料仅部署到 Relay，客户端没有本地签名回退。

## 安装与预下载

项目统一依赖安装器调用 `platform-runtime/scripts/install-runtime.mjs`，不要在技能执行期间临时安装依赖。

安装器按下列顺序查找完整分发包：

1. `XIAOBEI_PLATFORM_RUNTIME_ARCHIVE` 指定的文件。
2. `XIAOBEI_CACHE_DIR` 下的固定文件名；未设置时为 `~/.xiaobei/cache/xiaobei-platform-backend-0.3.1.tgz`。
3. 技能私有安装缓存中的同名文件。
4. 配置锁定的小贝发布资源。

命中本地文件后先校验完整性，校验不符立即停止，不绕过错误继续下载其他文件。预下载包保留原文件名即可，不需要修改业务技能的配置。

解包后继续核对五平台范围、依赖清单、注册表和适配协议。客户端必须保留 `static/x/graphql.json`、`static/tiktok/Tiktok_Request.json`、`static/kuaishou/fixtures/live_ws_proto.json` 和 `live_ws_maps.json`，供请求装配、私信与直播编解码使用；这些业务资源不随签名脚本一起裁剪。安装器按 `businessAssets` 逐份核对 SHA-256，缺失或内容变化即停止。

依赖安装与原生模块检查在临时目录完成；全部通过后才替换运行库和标记，替换失败恢复旧目录。既有会话、浏览器身份、发布收据和业务数据库不随依赖替换迁移或清理。

## 发布资源准备

客户端发布前，维护者必须把与配置 SHA-512 一致的包放到锁定发布资源中，或随安装包预置到上述缓存。尚未上传资源时，使用已准备的本地包完成构建和安装验收，不宣称在线获取已通过。

包内 `runtime-contract.json` 定义状态目录环境变量、错误类型导出、原始响应符号与 `signingMode: relay`。适配代码读取该协议，不在公开配置中绑定底层实现名称。版本或签名模式不匹配时拒绝加载，不回退旧本地签名包。依赖只保留传输、协议、配置、schema 与二维码编码，不安装视觉识别或 ONNX；图片转码复用统一 ffmpeg/ffprobe。

五平台计算接口为 `POST /api/v1/sign/platforms/v1`，使用既有 `X-OFB-Key`。环境复用 `OFB_KEY` 与 `RELAY_BASE_URL`；签名输入与结果只在请求周期内处理，不落盘、不记录正文。平台 HTTP 始终从客户端发出。快手验证码求解与 YouTube BotGuard 未开放，Relay 没有对应操作。发布客户端前先部署兼容签名服务及私有材料，再准备锁定运行包资源；仅本机离线验收不能代表生产已部署。
