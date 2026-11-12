# 转发到群，自动保存资源

用小号登录，选择大、小号共同所在的群，保持程序运行。之后大号转发到群里的常见压缩包会自动保存到指定文件夹，不用再次发命令。

本项目基于 iljacc/telegram-file-downloader 1.1.0，保留其常驻检查和持久进度，并增加代理与网页工作台。

## 推荐：网页工作台

使用 `compose.web.yaml`，在页面完成管理密码、Telegram 登录、代理、选群和下载规则配置。支持实时进度、速度、剩余时间、历史记录、视频最高可用清晰度、常见压缩包密码解压、成功后删除原包，以及群内回执。

**[网页部署与迁移说明 → WEB_GUIDE.zh-CN.md](WEB_GUIDE.zh-CN.md)**

网页菜单中的「节奏播放」可将本地图库组合成播放列表，支持图片、视频和混合播放，以及手动切图、自动播放、喜欢收藏和全屏。[播放器使用说明](docs/PLAYBACK.zh-CN.md)。

下面保留原有命令行部署流程；其中扩展名、无网页端口和不解压的说明仅适用于 `telegram-file-downloader-service` 命令行入口。

## 先了解实际行为

- 常驻运行，正常约每 5 秒检查一次新增消息；不是瞬间响应的事件监听。
- 首次启动时，HISTORY_START_DATE 留空，跳过该次启动之前的消息。
- 此后重启会复用进度，补下载首次启动之后、程序停机期间收到的新附件，不会重新回扫首次启动前的旧内容。
- 当前压缩包模板保存常见压缩包；命令行入口不自动解压，也不上传云服务。
- 无网页端口。通过运行日志查看连接和下载状态。

推荐直接拉取已发布的 Docker 镜像常驻运行，服务器不需要编译源码。若想省去 Docker，也可以按文末的 Windows 方式运行；它是控制台程序，不是完整的 TG 聊天客户端或免安装 GUI EXE。

- Fork 仓库：https://github.com/KazeLiu/telegram-file-downloader
- Docker 镜像：ghcr.io/kazeliu/telegram-file-downloader:latest
- 发布流水线：https://github.com/KazeLiu/telegram-file-downloader/actions/workflows/publish-image.yml

## 一、Docker：准备新目录

在 KazeLiu-Server 克隆 fork，或把 GitHub 下载的源码 ZIP 解压到独立目录，例如：

```text
C:\docker\tg-group-watcher
```

如果使用 Git，可执行：

```powershell
git clone https://github.com/KazeLiu/telegram-file-downloader.git C:\docker\tg-group-watcher
```

运行镜像实际上只需 compose.ghcr.yaml 和 config 下的配置，保留整个仓库方便以后更新文档和配置模板。

不要覆盖旧的 telegram_media_downloader 目录。两个项目的登录会话格式和进度不同，不要复制旧 sessions 目录到这里。

在服务器 PowerShell 中执行：

```powershell
Set-Location C:\docker\tg-group-watcher
New-Item -ItemType Directory -Force config, data, downloads
Copy-Item .env.docker.example config\.env
notepad config\.env
```

首次创建时执行 Copy-Item 即可；已有实际配置后不要再次覆盖它。

## 二、填写小号 API 和实际代理端口

编辑 C:\docker\tg-group-watcher\config\.env：

1. TELEGRAM_API_ID：小号申请的数字 ID。
2. TELEGRAM_API_HASH：与其对应的 Hash。
3. TELEGRAM_PROXY_PORT：服务器代理实际提供的 SOCKS5 / Mixed 端口，只填数字。

代理就在 KazeLiu-Server 的 Windows 上时，保留：

```dotenv
TELEGRAM_PROXY_TYPE=socks5
TELEGRAM_PROXY_HOST=host.docker.internal
```

如果代理在路由器或另一台设备上，把 HOST 换成该设备的实际局域网 IP。仅提供 HTTP 代理的端口则将 TYPE 改为 http。不要把 HTTP-only 端口当成 SOCKS5 端口。

宿主机的代理需要允许 Docker 虚拟网络访问；仅监听 127.0.0.1 的服务可能无法从容器访问。不要为此向公网开放代理。

这个部署模板明确启用了代理，因此端口留空会直接报配置错误，不会偷偷改成直连。TELEGRAM_CHAT 先保持空白，HISTORY_START_DATE 也保持空白。

Docker 拉取 GHCR 镜像需要使用 Docker 自身的网络/代理设置。上述 TELEGRAM_PROXY 配置只负责程序连接 TG，两者不能混为一谈。

## 三、拉取镜像、登录小号并选群

```powershell
docker compose -f compose.ghcr.yaml pull
docker compose -f compose.ghcr.yaml run --rm watcher telegram-file-downloader-configure
```

设置向导会读取刚才的 API 信息，回车可保留已填写值。按照提示输入小号手机号、小号收到的验证码，以及可能需要的两步验证密码。

登录后程序会列出群和频道。输入你与小号共同群前面的编号。向导会自动把真实群 ID 保存到 config\.env，不需要你手动拼接 -100。

这个步骤只做登录和选群，不启动下载。选好后执行下一步，再转发新的测试压缩包。

## 四、常驻运行

```powershell
docker compose -f compose.ghcr.yaml up -d
docker compose -f compose.ghcr.yaml logs -f watcher
```

日志中出现 Watching Telegram chat 后，再用大号往共同群转发一个体积较小的新压缩包。正常应在下一轮检查中开始下载。

- 下载目录：C:\docker\tg-group-watcher\downloads。
- 登录会话、进度和日志：C:\docker\tg-group-watcher\data。
- 未完成文件带 .part 后缀，成功后才恢复正常文件名。
- 文件保留原名称；遇到同名文件会使用编号，避免覆盖已有文件。

按 Ctrl+C 只退出日志查看，后台容器继续运行。

如需把资源放到另一目录，修改 compose.ghcr.yaml 的下载挂载源，例如把 ./downloads:/downloads 改为 "D:/TG-Resources:/downloads"，再执行 up -d。已有未完成下载时先等其结束，不要在半途中更换挂载目录。

暂停与恢复：

```powershell
docker compose -f compose.ghcr.yaml stop watcher
docker compose -f compose.ghcr.yaml up -d
```

修改代理、扩展名或选群后，重新运行 up -d 并重启 watcher，让正在运行的进程重新读取配置：

```powershell
docker compose -f compose.ghcr.yaml restart watcher
```

不要删除 data 来排查普通网络问题：这里保存了登录会话和首次启动时间，删除后会失去原有进度。程序必须运行时才能下载；Docker / Windows 停机期间的新附件会在恢复后尝试补齐，前提是文件仍在 TG 上且小号仍能访问。

### 更新镜像

```powershell
docker compose -f compose.ghcr.yaml pull
docker compose -f compose.ghcr.yaml up -d
```

推送 master 会触发 GitHub Actions 构建镜像。latest 指向最近发布版本；也可以将 Compose 中的镜像标签换成流水线发布的 sha-完整提交号，固定到某次构建。

仅开发时需要自行构建；对应入口仍是 compose.local.yaml：

```powershell
docker compose -f compose.local.yaml build
```

## 五、也可以直接在 Windows 运行

需要已安装 Python 3.11 或更高版本。将项目解压到独立目录后，在该目录 PowerShell 中执行：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
Copy-Item .env.windows.example .env
notepad .env
```

同样填写小号 API 和实际代理端口。Windows 原生运行访问本机代理时，HOST 使用 127.0.0.1，而不是 host.docker.internal。DOWNLOAD_DIR 默认 C:/TG-Resources，可改成你希望存放文件的绝对路径。

然后登录选群并运行：

```powershell
.\.venv\Scripts\telegram-file-downloader-configure.exe
.\.venv\Scripts\telegram-file-downloader-service.exe
```

保持运行窗口打开，使用 Ctrl+C 正常退出。原生方式没有设置开机自启。会话与进度默认保存在项目目录下的 data 文件夹。

## 常见问题

- 提示 PROXY_HOST / PROXY_PORT：代理配置未填完整，程序尚未尝试登录。先填写正确端口。
- 连接被拒绝或超时：检查代理类型、地址、端口，以及宿主代理是否允许 Docker 访问。不要直接换 API 或删除登录文件。
- 没看到转发前的旧文件：这是预期行为；本配置只从首次启动开始处理。
- 允许列表之外的附件被跳过：修改 ALLOWED_EXTENSIONS 后重启。之前已跳过的消息不会因为改扩展名自动重放。
- 下载一直停在某条消息：上游会在下载失败时保留进度并等待重试，不会越过该文件假装完成。查看日志中的实际异常和磁盘空间。
- Linux Docker 上目录无写权限：镜像运行用户 UID 为 10001，需确保 config、data、downloads 对该用户可写。这里没有自动修改你宿主机的权限。

## 验证状态与账号保护

镜像由 GitHub Actions 构建并推送到 GHCR，具体构建状态以仓库的发布流水线为准。服务器上的首次登录、代理连通及新压缩包落盘，仍需按上面的短流程确认。

config\.env / .env 含 API 信息，data 含可复用的账号登录会话，不要发送给别人，也不要把填写后的目录重新上传作为源码包。持续运行的是小号，大号继续用你平时的官方客户端挑选和转发资源。
