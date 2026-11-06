# 满 15 天后转入 Windows 回收站

项目继续只发布 Linux Docker 镜像。联动回收由容器完成；Windows 系统回收站的操作由同一台 Windows 宿主机上的 PowerShell 脚本执行，不需要安装原生 Python 服务，也不需要网页密码或小米凭据。

## 先配置宿主机路径

只使用镜像部署时，可以直接从更新后的容器取出配套文件，不用在宿主机克隆源码。把容器名替换成实际名称：

```powershell
docker cp tg-collector-watcher-1:/app/host-tools .\host-tools
Set-Location .\host-tools
```

保留仓库中的 `scripts/Move-ExpiredRecycle.ps1` 和 `scripts/WindowsRecycle.cs`，两者放在同一个固定目录。示例配置复制一次即可，已有配置不要覆盖：

```powershell
Copy-Item .\scripts\windows-recycle.example.json .\windows-recycle.json
notepad .\windows-recycle.json
```

`container` 填实际容器名，可通过 `docker compose -f compose.web.yaml ps` 查看。`mounts` 左侧是 Compose 中的容器挂载路径，右侧是对应的 Windows 宿主机目录。例如 Compose 使用 `D:/TG-Resources:/downloads`、`D:/照片备份:/backups` 时：

```json
{
  "container": "tg-collector-watcher-1",
  "mounts": {
    "/downloads": "D:\\TG-Resources",
    "/backups": "D:\\照片备份"
  }
}
```

不使用 `/backups` 就删除该行；不要把下载目录配置成数据卷的目录。脚本只支持可写的 Docker bind mount，以及支持 Windows 回收站的本机固定磁盘；不处理 UNC、网络盘或 Docker 命名卷中的文件。每个绑定目录中的 `.tg-trash` 必须在映射范围内。

## 查看清单，再安装每日任务

先查看到期清单，不调用 Windows 删除接口：

```powershell
powershell.exe -NoProfile -STA -File .\scripts\Move-ExpiredRecycle.ps1 -Config .\windows-recycle.json -ListOnly
```

确认路径后安装到**当前 Windows 用户**，每日 09:00 和该用户登录时检查：

```powershell
powershell.exe -NoProfile -STA -File .\scripts\Move-ExpiredRecycle.ps1 -Config .\windows-recycle.json -InstallTask
```

任务使用当前用户的交互会话与回收站，不使用 SYSTEM，也不在无人登录时永久删除文件。该用户需要能运行 Docker 命令。电脑关机、用户未登录或 Docker 未运行时，文件留在项目回收站，恢复条件后由下一次任务补处理。需要立即处理已到期的文件时，运行同一命令但不带 `-ListOnly` 或 `-InstallTask`。

如果宿主机的执行策略阻止脚本，按自己的管理策略审核并允许这份脚本；安装命令不会改系统执行策略。要取消任务：

```powershell
Unregister-ScheduledTask -TaskName 'Telegram Collector Recycle Handoff' -Confirm:$false
```

删除定时任务不会删除任何回收文件。更新镜像后也要更新宿主机的两份脚本；保持配置文件及其旁边的 `windows-recycle.log`。

## 15 天怎样计算

- 以移入项目回收站的时间和该文件最后修改时间中的较晚者计时，满 15 × 24 小时后才进入清单。
- 浏览列表、查看缩略图或检查任务不重置计时。
- 在网页还原后再次回收会生成新记录，重新计算 15 天。
- 此规则处理所有项目回收来源，不会删除普通下载文件，也不会清空 Windows 或小米云回收站。
- 转入 Windows 后仍占磁盘空间，后续保留期限由该用户的 Windows 回收站与存储策略决定。

## 失败时保留文件，交接有记录

脚本先通过 `docker exec` 领取到期记录，再读取容器新写入的随机交接标记，确认配置的 Windows 目录确实是同一个挂载。只操作该记录对应的文件，不扫描其他宿主机目录。领取期间网页不能同时还原该项。

Windows 端使用 [IFileOperation 的 recycle-only 标志](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperation-setoperationflags)，并在 [PreDeleteItem 回调](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperationprogresssink-predeleteitem)中拒绝未标记为回收的操作。接口未确认进入回收站、磁盘不支持、权限不足或文件变化时，不改用永久删除。

脚本在 `.tg-trash/handoff` 保存原路径及 Windows 交接凭据，随后通知容器完成记录。网页回收站中的“查看已转入 Windows 的记录”保留原文件名与对应的回收编号。配置文件旁的 `windows-recycle.log` 记录成功和失败；定时任务失败返回非零退出码。

如果 Windows 已完成回收但容器确认失败，下次运行会根据凭据补交确认，不重复删除。若操作中途退出且没有留下成功凭据，网页显示“交接待确认”；先核对 Windows 回收站、交接文件和日志，不要直接删除数据库或回收文件。

## 从 Windows 找回文件

Windows 回收站内保留的是项目回收编号，例如 `a1b2…`，不是原始文件名。先在网页“回收站 → 查看已转入 Windows 的记录”按原路径找到编号，再在 Windows 回收站还原该编号。文件会回到原来的 `.tg-trash/files` 中。

随后在同一条网页记录上点“系统还原后恢复原路径”，恢复原文件名与目录；同名文件已存在时仍不会覆盖。小米云文件需在小米云回收站另行还原。

若文件已回到 `.tg-trash/files`，但网页仍是“交接待确认”，可在确认该编号和目录后解除交接，再回网页还原：

```powershell
docker exec tg-collector-watcher-1 python -m telegram_file_downloader.windows_recycle cancel --root downloads --id 实际回收编号
```

绑定目录的 `root` 不是 `downloads`，需使用 `-ListOnly` 输出中的根目录编号。解除交接只在文件仍存在时生效，不会移动或删除文件；随后立即在网页还原，避免下次到期任务再次领取。
