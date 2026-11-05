# 拾存：用页面管理 Telegram 收集

在群里转发一个附件，工作台自动保存、尝试解压，并回复处理结果。代理、登录、选群和下载规则都在网页设置，不需要写进 Compose。

## Docker 启动

使用本仓库带网页功能的镜像版本。在 `compose.web.yaml` 中，只修改下载挂载的左侧，例如：

```yaml
volumes:
  - "D:/TG-Resources:/downloads"
  - collector-state:/data
```

然后运行：

```powershell
docker compose -f compose.web.yaml pull
docker compose -f compose.web.yaml up -d
```

浏览器打开 `http://服务器地址:18880`，本机打开 `http://127.0.0.1:18880`。

首次启动后立即设置管理密码。请仅在可信局域网或 Tailscale 中访问，不要把端口映射到公网。HTTP 在可信网络外不保护传输内容；需要跨不可信网络访问时，使用 HTTPS 反向代理或 Tailscale。

命名卷 `collector-state` 保存 Telegram 会话、设置、管理密码和下载记录。普通 `restart`、更新镜像、`up -d` 都会保留。**不要运行 `docker compose down -v`，也不要在清理 Docker 时删除这个卷。** 保持 Compose 项目名 `tg-collector` 不变，否则 Docker 会创建另一个空数据卷。

Linux 主机需确保下载目录允许容器内 UID 10001 写入。镜像目前为 linux/amd64。

## 首次连接

1. 在“设置 → Telegram”填写小号的 API ID、API Hash 和代理，保存。
2. 容器访问 Windows 宿主机代理时，地址填 `host.docker.internal`；端口填代理实际开放的 SOCKS5 或 HTTP / Mixed 端口。宿主代理需要允许 Docker 网络访问。
3. 页面连接后，输入小号手机号、验证码；有两步验证时，再输入 Telegram 密码。验证码通常在已登录的 Telegram 客户端中接收。此流程不注册新账号。
4. 加载群列表，选择大号和小号共同所在的群，保存选群。
5. 回到概览，点击“开始收集”，等右上角显示“正在收集”，再转发一个新附件。

代理地址可以填写 IP、域名、`主机:端口`，也可以直接粘贴 `http://主机:端口` 或 `socks5://主机:端口`。完整 URL 中的协议和端口优先，保存后页面会拆分显示；没有写在地址中的端口仍从独立端口框读取。复制带入的空格和隐藏格式字符会自动清理，用户名和密码仍填写在独立输入框中。

手机号允许带空格粘贴，离开输入框和提交时自动去掉空格，后端也会在校验前清理。只有 Telegram 连接就绪后才显示手机号入口，验证码发送成功后才进入验证码步骤。

如果显示 `IncompleteReadError` / 握手连接被关闭，说明网络连接在 Telegram 握手阶段中断，并不是手机号格式错误。使用可访问 Telegram 的代理，核对 HTTP / SOCKS5 类型、端口和代理的局域网访问权限，再点击“重新连接”。连接及登录请求最多等待 60 秒；网络失败会结束未完成的登录步骤，不删除已保存的会话或下载历史，也不会自动重复发送验证码。

工作台使用 Telethon 登录用户账号，不是 Bot。小号需要能查看附件；群回执还需要发言权限。代理不完整时会报错，不会静默改为直连。

“退出管理页面”只退出网页，不会停止收集。“退出 Telegram”则停止收集并注销该 Telegram 会话；随后可以直接在页面重新走登录流程。Telegram 在其他设备撤销此会话后，页面也会显示重新登录入口。下载文件和任务历史不会随退出删除。

## 下载、解压和回执

- **默认规则：** 视频、常见压缩包下载，图片不下载；自动解压打开，删除原包默认关闭。可在页面改动。
- **压缩包格式：** ZIP、RAR、7z、TAR、GZ / GZIP / TGZ、BZ2 / BZIP2 / TBZ / TBZ2、XZ / TXZ、ZST / ZSTD / TZST、LZMA / TLZ、Z / TAZ，以及 CAB、ARJ、LZH / LHA。扩展名不区分大小写，包含 `.tar.gz`、`.tar.bz2`、`.tar.xz`、`.tar.zst` 等 TAR 组合格式。
- **视频：** 从 Telegram 返回的原文档和视频候选版本中选择分辨率最高的版本，分辨率相同时选文件较大的版本。不会转码，也不能恢复发送前被 Telegram 压缩掉的画质。
- **图片：** 开启后下载最高可用尺寸；作为文档发送的图片按原文件下载。
- **解压：** 先尝试无密码，再按保存的密码列表逐个尝试。TAR 组合格式会继续展开内部 TAR，得到实际文件，而不只是留下中间 TAR。输出到独立的 `原包名_解压` 文件夹，同名自动编号。两层都在临时目录完整解压并通过路径检查后，才发布结果；不执行包内程序。
- **删除：** 只有完整解压成功，才按开关删除原压缩包。密码错误、损坏、缺卷、危险路径、链接或空间不足时保留原包，并在记录中显示原因。分卷压缩包下载后保留，请收齐后手动解压，本版不自动合并和清理分卷。
- **回执：** 回复原附件消息并更新同一条消息，约每 10 秒更新下载进度、速度和预计剩余时间；下载、解压、删除分别反馈。群禁言或限流不应阻断本地下载，页面会显示提示。
- **已读：** 表示附件已接收为任务，不表示文件已下载；以回执或下载记录判断完成。

页面历史保留接收、开始和完成时间、下载大小、进度、平均速度、耗时、清晰度与输出路径。解压失败后，可先修改密码列表，再从文件详情点击“重新尝试解压”。历史中的路径是程序内部路径，Docker 内以 `/downloads` 开头。

首次开始收集只处理启动后的消息。之后使用同一数据卷重启，会补齐首次起点之后、停机期间的新消息。已跳过的旧消息不会因修改分类开关重新下载。下载失败会保留消息进度并稍后重试；解压失败则保留原包和记录，继续处理后续附件。

升级前已经被跳过的压缩包，请在升级后重新转发到收集群；程序不会回扫已处理过的消息。

保存设置时，如果正在处理文件，页面显示等待应用；当前文件处理结束后再重新连接，不主动打断这个文件。暂停收集也遵循这个规则。

## Windows 不用 Docker

需要 Node.js 22.12+、Python 3.11+；自动解压需安装官方 7-Zip（常规安装位置会自动识别）。在项目根目录执行：

```powershell
cd web
npm ci
npm run build
cd ..
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
$env:DATA_DIR="$PWD\web-data"
$env:DOWNLOAD_DIR="D:\TG-Resources"
.\.venv\Scripts\telegram-file-downloader-web.exe
```

打开 `http://127.0.0.1:18880`。Windows 原生代理地址用 `127.0.0.1`。下次启动仍使用同一个 `DATA_DIR`。默认只监听本机；若要从 Tailscale 访问，启动前设置 `$env:WEB_HOST='0.0.0.0'` 并配置防火墙访问范围。

## 已有命令行版怎么迁移

原有 `configure`、`service`、`.env` 和 Compose 入口保留；网页功能使用独立的 `web` 入口。**网页不会自动读取或导出 `.env` 内的密钥。**

最简单的方式是停止旧下载实例，再启动网页版，在页面重新填写 API、代理并登录。新命名卷首次开始时跳过旧消息，旧下载文件保持不动。不要让两个实例同时使用一个 Telegram `.session` 文件。

如需保留本 fork 已有 Telethon 登录与增量起点：先正常停止旧实例，备份旧 `data` 目录，再把 `compose.web.yaml` 的 `collector-state:/data` 改成旧目录的绑定挂载，例如 `./data:/data`。页面重新填写同一 API 信息和选择同一群后，可复用 `telegram.session` 和 `download_history.sqlite3`。旧版没有速度/解压日志，因此不会凭空补出网页历史；网页记录从启用后开始累计。

`telegram_media_downloader` / Pyrogram 的 sessions 不兼容，不能直接迁移到本项目。

## 构建与更新

源码本地构建：

```powershell
docker build -t tg-collector:web .
```

将 `compose.web.yaml` 的 image 改为 `tg-collector:web` 后执行 `up -d`。Docker 多阶段构建会打包前端和官方 7-Zip，不依赖宿主机安装 Node 或 Python。

使用 GHCR 时，先确认仓库发布流水线已经发布包含网页入口的提交，再运行 `pull` 与 `up -d`。旧镜像没有 `telegram-file-downloader-web`，不能仅复制新的 Compose 就获得网页功能。

更新镜像不清数据卷。回滚镜像前保留数据卷备份；本版网页数据存储在独立 `console.sqlite3`，不替换原有下载进度表。
