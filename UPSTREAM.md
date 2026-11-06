# 选型与二开基线

## 选择：iljacc/telegram-file-downloader

- 上游：https://github.com/iljacc/telegram-file-downloader
- Fork：https://github.com/KazeLiu/telegram-file-downloader
- 版本：1.1.0。
- 基线提交：b720e03，提交日期 2026-10-08。
- 许可证：MIT，原 LICENSE 保留。
- 核对范围：读取当前 checkout 的全部业务模块、Dockerfile、Compose、配置与恢复逻辑，以及现有恢复测试源码；未执行测试。

它已有本任务所需的核心行为：单个指定群、常驻检查、扩展名允许列表、首次起点留空时从当前时间开始、持久消息进度，以及停机后的增量补下载。当前实现正常每 5 秒检查一次，不是 NewMessage 事件监听。

这是一个体量较小、公开使用量也较小的项目。最近有源码更新，不等同于已经过大规模长期运行验证；本次将它作为可阅读、可修改的最小二开基线。

## 同时比较的路线

| 项目 | 已核实的相关能力 | 取舍 |
| --- | --- | --- |
| iljacc/telegram-file-downloader | 直接面向指定群新文件、Docker、持久进度 | 选为最小基线；原版缺少代理接入 |
| rfsbraz/telegram-downloader | 常驻 daemon、多来源、过滤、下载后 hook | 功能更全面；本轮不需要额外的多来源、通知等配置面 |
| 64Gram / AyuGram Desktop | 仍有 Windows 客户端版本发布，源代码可二开 | 完整客户端 fork 涉及 C++ / Qt 构建和长期合并；本轮不为单个群下载功能承担这些工作 |

Windows 客户端的自动媒体缓存不应直接等同于“指定群附件自动保存为指定目录中的普通文件”。本轮未认定这两个客户端现成配置已经满足完整流程；AyuGram 还有关于自动保存到普通目录的相关需求记录。

## 本地适配内容

1. 增加 SOCKS5 / HTTP 代理配置，登录向导和常驻下载共用解析结果；不完整的代理配置明确报错，不静默直连。
2. 增加 python-socks 的 asyncio 运行依赖。
3. 修正原生 Windows 不支持 asyncio.add_signal_handler 的入口问题；保持 Ctrl+C / SIGTERM 的正常停止路径。
4. 新增 compose.local.yaml，使用可写配置目录供登录向导保存群 ID；原 Compose 和默认 .env 入口保留。
5. 增加常见压缩包专用模板与中文操作说明；原来的可自定义扩展名用法仍保留。
6. 登录向导沿用已配置的数据目录，避免原生运行登录后找不到同一会话；群选择编号只接受显示范围内的正整数。
7. 增加 GitHub Actions 镜像发布和 compose.ghcr.yaml，服务器直接拉取 GHCR 镜像，不必自行构建。

8. 增加独立网页入口：FastAPI 与 Vue 3 工作台，持久登录与设置、代理、媒体分类、视频版本选择、下载历史、回执、已读与 7-Zip 解压。CLI 不启用这些网页扩展，原有调用方式保留。
9. 网页文档下载使用有界分片并发，默认上限 4 路，支持 1 / 2 / 4 路切换；按服务端限流时间共同等待并降低有效并发。进度回执与分片回调分离。并发基于 Telethon 的公共 iter_download；CDN 信号和迭代器初始化清理对固定版本 1.44 有少量适配，升级 Telethon 时需核对 downloads.py 的对应行为。
10. 网页接收任务与执行解耦，最多五文件各自最多四路分片，共享账号限流等待和降低后的总请求额度，并遵守 Telegram 下发的同 DC 文件队列上限；持久分片断点、暂停/继续/重试、分卷整组完整性检查、根目录扁平化与共享规则的 PSD/TXT 清理（PDF 保留）、可恢复整理记录和文件管理。自动流程与手动复选框复用同一后缀判定、清单和删除执行路径，已确认手动清单不自动扩大。新增持久滚动日志与下载请求超时；CLI 的扫描处理方式保持不变。小米云相册仅保留待接入节点。

11. 大目录文件管理复用 scandir 元数据，分页仅获取当前页属性，预览缓存根目录名称以检查重名；根目录成品不生成移动项。自动与手动整理逐文件保存紧凑游标，完成时原子合并快照；手动进度轮询读取摘要，旧确认清单保留。预览按钮有独立加载状态与旋转图标。

云上传与原生 Windows 开机自启尚未加入。网页用法见 WEB_GUIDE.zh-CN.md。

## 参考材料

- 上游当前源码：https://github.com/iljacc/telegram-file-downloader/blob/master/src/telegram_file_downloader/watcher.py
- 上游配置向导：https://github.com/iljacc/telegram-file-downloader/blob/master/src/telegram_file_downloader/configure.py
- 较全面的 daemon：https://github.com/rfsbraz/telegram-downloader
- 64Gram 发布：https://github.com/TDesktop-x64/tdesktop/releases
- AyuGram 发布：https://github.com/AyuGram/AyuGramDesktop/releases
- AyuGram 自动保存需求：https://github.com/AyuGram/AyuGramDesktop/issues/409
- AyuGram Windows 构建要求：https://github.com/AyuGram/AyuGramDesktop/blob/dev/docs/building-win.md
