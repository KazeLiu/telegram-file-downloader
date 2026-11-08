---
title: 小米云连接与上传接入调研
date: 2026-11-06
project: telegram-file-downloader
reference_commit: 340de4a231c65fa9780c2577ad30954effb5cf07
---

# 小米云连接与上传接入调研

## 接入时补充的证据

2026-11-08，只读检查本机小米云服务 4.0.1.328 的 `resources/app.asar` 中 gallery renderer，确认日期索引先调用 `POST /gallery/user/lite/index/prepare`，准备好后调用 `GET /gallery/user/timeline?albumId=...`，响应 `dayCount` 为 `YYYYMMDD` 到数量的映射。未准备好且 `isRetriable` 时等待一秒重试一次。照片按相同的 `startDate`、`endDate` 调用 `/gallery/user/galleries`，每页 30 项，最多两个在途日期请求；页面按可见区域上下约半屏预取。

普通照片墙主要复用 galleries 返回的缩略图地址。回收站另有 `/gallery/thumbnails?ids=...&type=small`，响应为 `idTothumbnails` 数组，每项含 `id`、`thumbnails.small.data`。本项目仅在地址缓存淘汰时按编号重新获取此缩略图信息，不将其表述为官方普通墙的常规批量策略。以上是已安装客户端的接口证据；本次界面验收使用隔离模拟账号，未用真实账号验证这些新接口。

2026-11-06，经用户授权在已登录的官方网页只读查看“酷安”相册：

- `/gallery/user/album/list` 的相册记录提供 `thumbnails[0].url` 作为封面。
- `/gallery/user/galleries` 的媒体记录提供 `thumbnailInfo.data`，该次响应中带 `isUrl`，未包含缩略图加密元信息。
- 页面实际成功加载的小图域名包括 `tos.xmssdn.micloud.mi.com`、`ali.xmssdn.micloud.mi.com`、`kssh3f.xmssdn.micloud.mi.com` 和 `kssh2thumb.xmssdn.micloud.mi.com`；响应为 JPEG。仅为缩略图代理加入 `xmssdn.micloud.mi.com` 子域白名单，上传存储白名单不变。

这里只记录字段和域名，不保存带签名的图片地址、媒体名称、账号凭据或原始响应。加密缩略图仍需对应的解密能力，不用原图下载代替缩略图。

独立页面的连接和读取沿用下文的固定快照。写入参考[小米官方云相册前端](https://cdn.web-global.fds.api.mi-img.com/mcfe--micloud-web-gallery/static/static/js/main.f7a44e87.chunk.js)和[分块 Worker](https://cdn.web-global.fds.api.mi-img.com/mcfe--fds-static-files/worker/cryptojs-upload.0cfed567.js)：

- 回收使用 `POST /gallery/info/delete`，提交单个媒体 `id`；不调用清空或永久删除接口。小米的[删除手册](https://i.mi.com/guide/zh-CN/gallery/delete)说明删除会同步到已开启相册同步的设备。
- 普通上传以相册 ID 为 `groupId`，先 `POST /gallery/user/full` 创建媒体记录。使用整文件 SHA-1 和每个 4 MiB 分块的 SHA-1、MD5 申请存储参数，把原始分块发给小米返回的 HTTPS 存储节点，最后 `POST /gallery/user/full/{id}/storage` 提交。存储请求不携带账号 Cookie。上传仍需用实际账号确认文件出现在指定相册。
- 官方网页代码中的改名请求只用于相册。安卓客户端的[媒体改名逻辑](https://github.com/nckmml/ANXGallery/blob/392f7a28a34556b6784979dd5eddcd9e4ceaaa69/src/ANXGallery/sources/com/miui/gallery/cloud/EditCloudItemName.java)属于另一套[移动同步接口](https://github.com/nckmml/ANXGallery/blob/392f7a28a34556b6784979dd5eddcd9e4ceaaa69/src/ANXGallery/sources/com/miui/gallery/cloud/HostManager.java)，现有网页票据能否访问尚无证据。页面只允许上传前指定名称，不用重新上传再删除替代原地改名。

## 原始调研

**推荐先独立实现“扫码登录 → 换取服务票据 → 读取相册 → 选择目标相册”。** XiaomiAlbumSyncer 能提供这条连接链路的参考；上传到指定相册还缺少写入协议，需要单独取得证据后实现。

本次工作集中在 `D:\code\telegram-file-downloader`。参考源码与归档位于 `references/XiaomiAlbumSyncer/`，固定版本和获取地址见 [来源记录](../../references/XiaomiAlbumSyncer/REFERENCE.md)。本次只读源码，未登录小米账号、未调用小米接口，也未改变现有“待接入”节点。

## 能借鉴什么，不能直接解决什么

| 能力 | 源码结论 | 对当前需求的意义 |
|---|---|---|
| 扫码取得账号凭据 | 已实现，后端保存 `userId` 与 `passToken`，见[扫码流程][1]与[凭据写入][4] | 推荐的连接入口，不必让用户复制浏览器 Cookie |
| 手动填写凭据 | 已实现，只写入凭据，不通过[账号查询接口][5]返回 | 可作为人工连接方式，不能把凭据放进普通配置响应 |
| 换取服务票据 | 已实现，[按账号缓存 `serviceToken`][2] | 凭据仍有效时，容器重启后可重新连接 |
| 获取相册与相册内容 | 已实现[分页读取][3] | 可以列出已有目标相册，并保存其 ID |
| 本地图片上传、加入指定相册 | 该快照的[小米适配器][3]未实现 | 不能把下载函数反过来调用当上传 |
| 账号实际可用性 | 需要真实账号验证 | 扫码成功后，还要验证云相册读取权限 |

## 1. 源码确认的登录链路

这条实现使用网页会话和 Cookie，没有开放平台 API Key 配置。以下路径来自固定源码快照，接口变化时需要重新核对。

### 扫码取得持久凭据

后端维护临时 Cookie，初始化 `deviceId` 和 `sdkVersion`，随后：

1. 向 `https://account.xiaomi.com/pass/serviceLogin` 发起 GET，请求的服务标识是 `sid=i.mi.com`，并携带 `_json=true`、`_locale=zh_CN`。
2. 从响应取得 `qs`、`callback`、`_sign`、`serviceParam`，传给 `https://account.xiaomi.com/longPolling/loginUrl`。这个地址不在 `/pass` 下。
3. 响应提供二维码地址 `qr`、长轮询地址 `lp` 和超时时间。后端等待 `lp`，用户在小米设备上扫码确认。
4. 从响应 JSON 或累计 Cookie 中取得 `userId`、`passToken`，按账号更新持久凭据，并使旧服务票据缓存失效。

账号响应的 `&&&START&&&` 前缀先移除再解析。应用状态为 `WAITING / SUCCESS / EXPIRED / FAILED`；等待状态也可能包含“已扫码但尚未确认”。成功表示凭据已写入，不等于已经验证相册访问。依据：[扫码实现][1]、[账号写入逻辑][4]。

### 前后端如何等待

| 项目 | 参考实现的取值或行为 |
|---|---|
| 后端长轮询 | 读超时 75 秒，整次请求超时 90 秒 |
| 二维码默认窗口 | 300 秒；等待期限取远端超时与此值的较小者，再加 15 秒 |
| 临时会话保留上限 | 330 秒 |
| 无前端查询 | 超过 30 秒视为放弃 |
| 长轮询间隔 | 一次请求结束后等待 500 毫秒 |
| 前端查询 | 上一次结束后再等 2 秒，不叠加请求 |
| 终态 | 返回一次后释放临时会话与其 Cookie |

这些数字是参考实现的策略，不是小米对接口有效期的保证。依据：[后端扫码管理器][1]、[前端轮询逻辑][6]。

参考项目自身提供 `POST /api/account/qr-login` 和 `GET /api/account/qr-login/{sessionId}`，两者都要求先登录其管理页面；这不是小米对外提供的接口路径。见[扫码控制器][7]。

## 2. 持久凭据如何变成云服务会话

| 字段 | 作用 | 接入时的存放建议 |
|---|---|---|
| `userId` | 小米账号标识 | 与凭据一起保存在后端；按需脱敏展示 |
| `passToken` | 重新取得服务票据的关键凭据 | 持久保存到 `/data`，只写入，不回传原文 |
| `serviceToken` | 访问云服务接口使用的票据 | 先采用内存缓存，重启后重新换取 |
| `deviceId` | 登录流程的设备标识 | 同一轮换票流程保持一致 |

`TokenManager` 的换票步骤是：

1. GET `https://i.mi.com/api/user/login`，带时间戳、编码后的 `followUp` 和语言参数；Cookie 带 `userId`、`deviceId`、`passToken`。
2. 读取 `data.loginUrl`，使用同组 Cookie 请求该地址，取得 `Location` 响应头。
3. 请求 `Location`，从 `Set-Cookie` 提取 `serviceToken`。

参考 HTTP 客户端关闭自动重定向，因此不能开启自动跟随后仍照抄上述响应头读取方式。相册请求最终携带 `userId` 与 `serviceToken` Cookie。依据：[换票流程][2]、[HTTP 与认证 Cookie 实现][8]。

缓存按账号复用，超过 10 分钟主动重取，这是客户端刷新策略。换票未取得服务票据时，参考实现报告凭据失效并去重告警；重新扫码更新凭据后清除旧缓存。见[票据管理器][2]。

接入时应区分网络失败、需要用户验证和凭据失效，不把超时直接标记为“已退出账号”，也不反复自动触发扫码。参考项目建议先在小米云网页版访问一次相册，按页面要求完成信任设备验证。见[上游账号说明][9]。

## 3. 如何读取并选择目标相册

默认云服务基址为 `https://i.mi.com`，见[上游默认配置][13]；参考项目通过[地址配置组件][10]管理地址。

| 云端路径 | 作用 | 关键字段 |
|---|---|---|
| GET `/gallery/user/album/list` | 分页读取相册 | 从第 0 页开始，每页 10 项，`isShared=false`；读取 `data.albums`、`data.isLastPage` |
| GET `/gallery/user/galleries` | 分页读取某相册内容 | 使用 `albumId`，图片页大小 200 |
| GET `/gallery/user/timeline` | 读取相册时间线 | `albumId`、`indexHash`、按日数量 |
| GET `/gallery/album/full`、`/gallery/allitems` | 下载同步的水位与增量记录 | `incrementalTag`、`syncTag`；不是上传接口 |

相册对象保存 `albumId`、名称和数量；目标绑定应保存账号与远端相册 ID，不用相册名称代替 ID。参考返回列表还人为加入了 ID 为 `-1` 的“录音”项，不能把它当作图片上传目标。见[相册读取实现][3]。

连接验证应以真实相册列表响应为准：HTTP 状态正常后，还要检查业务码、必要数据和分页结束标志。不要用空列表掩盖登录失效或接口结构变化。依据：[相册实现][3]、[业务错误约定][11]。

## 4. 上传仍缺什么证据

已逐个核对 `XiaoMiApi` 方法，并在后端主源码中搜索 `upload`、`multipart`、`putObject`、`kss`、上传及相册写入相关名称。当前小米能力集中在读取与下载，没有本地文件上传、创建相册、将媒体加入相册的方法。

其中 `downloadAsset` 虽然包含 POST，但它将下载元信息发给签名下载地址，并把响应体保存到本地；这一步不能作为上传协议使用。见[下载方法][3]。

后续实现上传前，需要在用户授权的真实账号上，观察小米云网页上传一张临时图片的完整请求链，确认：

- 目标相册的写入权限与真正传递的相册标识。
- 申请上传、传输文件、提交媒体记录、关联相册是否分为多步，以及各步真实字段。
- 是否要求文件摘要、分片、签名、额外 Cookie 或防重放参数；只按实际协议计算需要的摘要。
- 超时后如何查询结果，避免“服务端已成功、客户端未收到响应”时重复上传。
- 哪个响应或回查结果能证明文件确实进入指定相册，而不仅是存储端接收了字节。
- 格式、大小、账号地区、空间与配额限制，失败后本地文件如何保留。

本次未取得这些请求，因此不填写猜测的上传 URL、签名公式或字段，也不把“可登录”写成“已能上传”。

## 5. 接到现有项目时的推荐做法

保留当前 Python/FastAPI + Vue 结构，独立实现小米连接管理；不为了登录再部署一整套 Kotlin/JVM 下载器。参考项目标记为 GPL-3.0，源码保留[原许可证][12]；借鉴协议与交互时保留来源，直接复用其代码前单独处理许可证要求。

| 现有位置 | 当前事实 | 后续接入建议 |
|---|---|---|
| `web.py` | 管理认证和同源 API 保护已存在 | 在同一认证下新增小米连接、状态、相册查询入口；路径与 Telegram 分开 |
| `console_store.py` | SQLite 保存设置，公开响应排除秘密字段 | 小米凭据只在后端持久保存；公开状态只给已连接、账号摘要、目标相册和错误类别 |
| `web_runtime.py` | 保存现有设置会安排 Telegram 连接重建 | 小米配置不走 Telegram 的重连链路，避免中断下载 |
| `compose.web.yaml` | `collector-state:/data` 已持久化 | 沿用此卷，不要求把账号凭据写到 Compose；更新仍用 `docker compose -f compose.web.yaml ...` |
| `media_pipeline.py`、`WorkflowSteps.vue` | `cloud` 保持 `pending` / 待接入 | 上传协议验证成功后，再将这一节点接到独立云端队列 |
| 整理操作清单 | 知道本次资源涉及哪些文件 | 上传使用本次保留文件清单，不自动重扫整个根目录，也不扫描 `.tg-trash` |

上述是接入建议，当前没有新增这些 API 或改变工作流。

### 页面与连接状态

建议页面依次呈现：未连接 → 生成二维码 → 等待确认 → 验证云相册 → 已连接。选择相册后持久保存账号标识和相册 ID；凭据失效时提供重新扫码入口，不清除 Telegram 登录与下载记录。

当前 CSP 的图片来源只允许同源和 `data:`。直接显示参考项目返回的外域二维码 URL 会被拦截，宜由后端按当前扫码会话代理二维码图片，再给前端同源地址，而不是放开所有外域图片。

Telegram 的代理要求继续保留。小米 HTTP 连接应独立判断路由，不自动把 Telegram 的代理当作小米网络设置，也不在失败时悄悄切换出口。

### 凭据和日志

- Cookie、`passToken`、`serviceToken` 及二维码长轮询 URL 不进入日志、下载记录或普通配置响应。参考源码部分错误分支会打印响应头/正文，这种诊断方式不照搬。相关位置：[扫码异常分支][1]、[换票异常分支][2]。
- 给返回的登录、回跳和轮询地址校验 HTTPS 与已确认的小米域名，再发送凭据；不要向任意响应 URL 转发 Cookie。
- 管理页面限可信局域网或 Tailscale；需要跨不可信网络访问时使用 HTTPS。持久卷和备份同样按凭据保护。

### 上传与人工筛图的顺序

当前用户会在图片管理中人工剔除线稿。实施上传阶段时，需要确定是否让“人审完成”成为上传前置步骤；否则自动上传可能先于人工回收发生。这是后续上传阶段的交互决定，本次不改动已确定的本地自动整理流程。

## 6. 下一步完成标准

1. 用户确认账号网页版可进入云相册后，授权验证扫码、持久凭据和相册读取；重建容器后可重新换票，失效时能重新扫码。
2. 独立验证一张临时图片上传并出现在指定相册，记录经过脱敏的字段说明和成功判据。
3. 再接入工作流，处理逐文件状态、超时后的结果确认与重复触发；云端失败保留本地文件，并可单独重试。

当前文档完成的是源码调研和接入设计，真实登录、相册读取、上传及账号限制均未实测。

## 固定版本来源

以下链接均指向本次快照，后续开发可按问题直接定位：

| 要查看的问题 | 源码入口 |
|---|---|
| 二维码、状态与超时 | [QrLoginManager][1] |
| 服务票据换取、缓存和失效 | [TokenManager][2] |
| 相册读取与下载边界 | [XiaoMiApi][3] |
| 前端如何停止和续接轮询 | [PassTokenCard][6] |
| 重定向和认证 Cookie | [okHttpHelper][8] |
| 账号查询不回传凭据 | [ProviderAccountController][5] |

[1]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/server/src/main/kotlin/com/coooolfan/xiaomialbumsyncer/xiaomicloud/QrLoginManager.kt
[2]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/server/src/main/kotlin/com/coooolfan/xiaomialbumsyncer/xiaomicloud/TokenManager.kt
[3]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/server/src/main/kotlin/com/coooolfan/xiaomialbumsyncer/xiaomicloud/XiaoMiApi.kt
[4]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/server/src/main/kotlin/com/coooolfan/xiaomialbumsyncer/service/ProviderAccountService.kt
[5]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/server/src/main/kotlin/com/coooolfan/xiaomialbumsyncer/controller/ProviderAccountController.kt
[6]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/web/src/components/settings/PassTokenCard.vue#L132-L187
[7]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/server/src/main/kotlin/com/coooolfan/xiaomialbumsyncer/controller/QrLoginController.kt
[8]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/server/src/main/kotlin/com/coooolfan/xiaomialbumsyncer/utils/okHttpHelper.kt
[9]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/README.md#L145-L163
[10]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/server/src/main/kotlin/com/coooolfan/xiaomialbumsyncer/config/XiaomiApiProperties.kt
[11]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/server/src/main/kotlin/com/coooolfan/xiaomialbumsyncer/utils/extendFunctions.kt#L34-L40
[12]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/LICENSE
[13]: https://github.com/Coooolfan/XiaomiAlbumSyncer/blob/340de4a231c65fa9780c2577ad30954effb5cf07/server/src/main/resources/app.yml#L37-L39
