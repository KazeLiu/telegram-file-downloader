# 播放器运行层组件契约（v4，2026-11-25）

本文件登记 `web/src/playback/` 下运行层组件的接口。**任何一方不得擅自改签名**，需要改先在本文件登记。
权威玩法口径见 [寸止控制器实施契约](PLAYBACK-EDGE-CONTRACT.zh-CN.md)。

共享类型在 `web/src/playback/types.ts`：

- `PhaseKind = EdgeMode`（`'go' | 'slow' | 'stop'`，别名保留给旧调用方）
- `FinishReason = 'duration' | 'queue' | 'manual' | 'lost' | 'allow' | 'deny' | 'ruin'`
- `finishLabels` / `finishTitles`：每档结束原因的中文短句与标题
- `GuideStep { title: string; body: string }`、`PlaybackPosition { index, total, cycle }`、`LegendItem { label, tone }`

模式文案与色值不在这里，在 `engine.ts` 的 `modeLabels` / `modeColors` / `modeColorsBright`。

全部运行层组件都是纯展示组件：只在自身内部持有 UI 局部状态，**不改业务状态、不读 localStorage、不发请求**。
样式 scoped，深色底与白色文字，尺寸对齐参考站（100adults 男生版）。

## PlaybackOverlay.vue

运行层外壳：铺满视口，媒体在下，三层分区在上。

```ts
defineProps<{
  mode: EdgeMode        // 决定光晕颜色
  dim: number           // 变暗比例 20–100（100 = 完全透明）
  opacity: number       // 指令文字不透明度 30–100
  scale: number         // 指令文字大小 60–140
}>()
```

- 根 `.sd-stage`：`position: fixed; inset: 0; z-index: 60; display: flex; flex-direction: column; color: #fff; background: #0a0708`。
- `.sd-glow`：四层 `radial-gradient`（`110% 60% at 50% 0` α.7 / `110% 55% at 50% 100` α.55 / `70% 50% at 0% 50` α.24 / `70% 50% at 100% 50` α.24），色取 `modeColors[mode]`，`transition: background-image .8s ease; opacity .92`。
- `.sd-mask`：独立 `div`，`backgroundColor: rgba(0, 0, 0, min(0.45, 0.45 × (100 - dim) / 80))`，`transition: background-color .3s ease`。
  **不是 CSS `filter: brightness()`**——媒体本体不再挂 filter，变暗完全由这层 rgba 遮罩表达（对齐参考站的 `data-sundome-video-shade`）。
- 插槽：`media`（媒体本体，z-index 1）、`top`、默认插槽（中央）、`bottom`。
- `.sd-center` 挂 `radial-gradient(70% 55% at 50% 50%, rgba(0,0,0,.6), transparent)` 与文字投影，让白字在视频上也清晰；`.sd-center-inner` 用 CSS 变量 `--sd-text-opacity` / `--sd-text-scale`。

## PlaybackTopBar.vue

```ts
defineProps<{
  name: string
  position: PlaybackPosition
  remaining: string        // 已格式化，如 '9:15'；随机时长或不限时传 ''
  hideTime: boolean
  paused: boolean
  playing: boolean
  held: number             // 忍住次数
  noCrop: boolean          // = settings.fit === 'contain'
  align: 'top' | 'center' | 'bottom'   // = settings.pos
  pipAvailable: boolean
  landscapeAvailable: boolean
  volumeOpen: boolean
  fullscreen: boolean
  note: string             // 「加时第 N 次 · 时间增加了 m:ss」/「第 N 轮」，非空时替代「第 N 条指令」
}>()
defineEmits<{
  'toggle-crop': []
  'cycle-position': []
  'pip': []
  'volume': []
  'landscape': []
  'fullscreen': []
  'toggle-pause': []
  'exit': []
}>()
```

- 左：`.sd-count`（16px/800 斜体，`第 N 条指令` 或 `note`）+ `.sd-held`（`忍住 N`）；中：`.sd-clock`（18px/700 tabular-nums）；右：`fit`（`expand`/`shrink` 切换裁切）→ `pos`（**仅 `noCrop` 时出现**，`Icon name="position"`，循环 `center → top → bottom`）→ `pip` → `volume` → `landscape` → 3 个 30px 高药丸（全屏／暂停·继续／退出）。
- 按钮均带 `data-sundome-*` 属性以便和参考站对齐：`data-sundome-count` / `clock` / `fit-toggle` / `pos-toggle` / `pip-toggle` / `volume-toggle` / `landscape` / `fullscreen` / `pause` / `quit`。
- 所有按钮必须 `min-height: 0`——`web/app/assets/main.css` 有全局 `button { @apply min-h-11 }`，不覆盖会被撑到 44px。
- 图标名必须存在于 `Icon.vue`（已补 `expand`/`shrink`/`pip`/`volume`/`rotate`/`position`/`stop`/`spark`）。


## PlaybackStage.vue

```ts
defineProps<{
  mode: EdgeMode
  text: string            // 当前指令（可为多句）
  hint: string            // 该条指令专属的小字提示
  bpm: number             // 0 表示不显示节拍
  progress: number        // 0–1，当前这一条的进度
  taskSeconds: number     // 这一条总秒数，驱动倒计时条动画
  taskKey: number         // 换条时变化，用来重启动画与重置二次确认
  paused: boolean
  cooling: boolean        // 正在「等它平息」
  canHold: boolean
  held: number
  note: string
  toneBefore?: string     // 口吻前置短句，空串表示不显示
  toneAfter?: string      // 口吻后置短句，空串表示不显示
}>()
defineEmits<{ hold: []; lost: []; guide: [] }>()
```

- 结构：模式胶囊（`data-sundome-mode-label`，`letter-spacing .25em`）＋ `N BPM` 与跳动圆点 → 指令（`data-sundome-command`，`font-size: 28px`，≥640px `48px`，`font-weight: 700`，`letter-spacing: -.025em`，`text-shadow: 0 0 28px rgba(0,0,0,.35)`）→ 指令小字（`data-sundome-hint`，16px，70% 白）→ 倒计时条（`data-sundome-task-bar`，160×4px，`animation: sd-shrink linear forwards`，时长 = `taskSeconds`）→ 「忍住了」主按钮（`data-sundome-edge`，`min-width: 100px`、`padding: 12px 24px`、2px 白边、圆角 999）→ 提示「在快射的前一刻停下来了就按。按下后切换成“等它平息”」→ 「已忍住 N 次」→ `note` → 「射了」（`data-sundome-lost`，13px，55% 白，下划线）。
- 指令**按「。！？」逐句渲染**（参考站的 `Sentences`）：每句 `<span class="sd-sentence">`（`display: inline-block; max-width: 100%; word-break: keep-all; overflow-wrap: anywhere`），句子之间不切断词。
- 「射了」先弹二次确认 `data-sundome-lost-ask`（`记为中途结束的一局吗？` ＋ 白底「记录并结束」`data-sundome-lost-yes` / 描边「继续」`data-sundome-lost-no`），换条（`taskKey` 变化）时自动收起。
- `cooling` 时主按钮文案变「等它平息…」并禁用。
- 暂停时（`paused && !cooling && !asking`）在「射了」下方多给一个「查看操作说明」入口（`data-sundome-guide-open`，药丸 12px，emit `guide`），点开重看引导；关掉引导时不会重复标记「已看过」以外的状态。
- 口吻短句：`toneBefore` 渲染在指令**上方**（`data-sundome-tone="before"`，18px／≥640px 24px，700，`.85` 白），`toneAfter` 渲染在指令**下方**（`data-sundome-tone="after"`，16px／20px）；同时有前置时指令的上边距收到 12px。文字只做展示，不朗读。

## PlaybackBottom.vue

```ts
defineProps<{
  elapsed: string
  total: string
  progress: number         // 0–1
  allowed: boolean         // 许可窗口期间整条变白发光
  windowLeft: number
  hideTime: boolean
}>()
defineEmits<{ skip: [] }>()
```

- 整场进度条 8px 圆角（`transform: scaleX(progress)`），右侧 `已用 / 总时长`（11px，60% 白）；`allowed` 时进度条变纯白并显示 `许可 N 秒`。
- 图例：`modeOrder` 三色点（10px）＋ `modeLabels`；≥640px 追加 `Space 暂停 · E 忍住 · Esc 退出`。
- 右侧「换个视频」药丸（`data-sundome-video-skip`，11px/500，`border 1px rgba(255,255,255,.3)`，圆角 999，`min-height: 0`）。

## PlaybackReward.vue

拿到许可时盖的整屏奖励屏（参考站的 reward 屏）。

```ts
defineProps<{
  ruined: boolean          // 松手射精（橙）还是普通许可（粉）
  windowLeft: number       // 剩余秒
  windowTotal: number
  multi?: boolean          // 连续（多少次都行）结局：换成多轮文案
  round?: number           // 连续结局里现在播到第几次（1 起，最多 4）
}>()
```

- 根节点 `data-sundome="reward"`、`:data-result="ruined ? 'ruin' : 'allow'"`、
  `:data-sundome-multi="multi ? 'true' : 'false'"`、`:data-sundome-reward-seconds="Math.round(windowTotal)"`。
- 眉标 `Ruined`／`Permission`（12px、`letter-spacing: .35em`）、标题 `clamp(44px, 13vw, 96px)` 斜体 800、
  正文 18px、倒计时条 `12px` 高 `max-width: 28rem`（内条白色，`width: (1-已用) × 100%`）、剩余秒 14px。
- `multi` 为真时不显示普通正文，改为 `data-sundome-multi-round`（`第{n}次 / 4`，14px/`letter-spacing: .2em`）
  与 `data-sundome-multi-line`（20px／≥640px 24px，按 `round` 取 `multiLines[(round-1) % 4]`）。
  文案常量在 `engine.ts`：`multiTitle = '可以射。多少次都行'`、`multiLines`（4 条）、
  `multiRoundLabel(round)`、`multiWindowSeconds = 100`、`multiRoundSeconds = 25`、`multiRounds = 4`。

- 根 `data-sundome="reward"`，`:data-result="ruined ? 'ruin' : 'allow'"`，`position: fixed; inset: 0; z-index: 95`。
- 背景：`ruined` → `radial-gradient(ellipse at 50% 30%, #c86a2a 0%, #6b2f0f 55%, #2a1206 100%)`，否则 `radial-gradient(ellipse at 50% 30%, #ff4d6d 0%, #a4123a 55%, #3a0612 100%)`。
- 内容：眉标（`Ruined` / `Permission`，12px/600，`letter-spacing .35em`，70% 白）→ 标题「可以射」/「可以射了」（`clamp(44px,13vw,96px)` 斜体 800）→ 正文「但射出的瞬间要松手。不碰，让它自己流」/「在进度条消失前射出来」→ 倒计时条（`height: 12px; max-width: 28rem`，白色内条）→ `剩余 N 秒`。

## PlaybackFinished.vue

结算屏（独立于运行层）。

```ts
defineProps<{
  outcome: FinishReason
  elapsed: string          // '7:12'
  durationMinutes: number
  percent: number          // 完成百分比
  held: number
  commands: number
  rounds: number
  extends?: number         // 加时次数；>0 时多显示一行「加时 N 次后获得许可」
  lostCount?: number       // 中途结束累计次数
  lostBest?: string        // 中途结束里最长的坚持时间（'5:20'）
  lostBestNow?: boolean    // 这一次是不是破了自己的纪录
}>()
defineEmits<{ again: []; exit: []; penalty: [] }>()
```

- 根 `data-sundome="done"` 带 `:data-result="copy.ruin ? 'ruin' : 'success'"`，背景同 `PlaybackReward` 的橙／粉两套。
- 文案六路：`allow|duration` → Finished／坚持到底了／撑满了时间，拿到了许可。；`ruin` → Ruined／松手收场／如果在射出的瞬间松手了，就算成功。…；`lost` → Lost／没忍住，射了／坚持了 {elapsed}，完成了设定的 {minutes} 分钟中的 {percent}%。；`manual` → Finished／就到这儿；`queue` → Finished／素材放完了；其余 → Denied／今天被禁止了／没有拿到许可。…
- 三格统计（`data-sundome-done-stat`）：时间 / 指令（`N次`）/ 忍住（`N次`）；中途结束时第一格改叫「坚持时间」。
- 中途结束额外三行：破纪录提示（`data-sundome-lost-best`）、「中途结束 N 次 · 最长坚持 m:ss（只存在这台设备里）」（`data-sundome-lost-record`）、惩罚说明（`data-sundome-lost-penalty-note`）；动作区多一个「带惩罚再来一局」（`data-sundome-lost-penalty`，emit `penalty`），会把下一局结局改成「必定禁止」后立刻重开。
- 动作区 `data-sundome-done-actions` 内还有「再来一次」（`data-sundome-again`）与「返回播放列表」。
- 连续（多少次都行）结局：成功时正文换成「如果一直到最后都没停手，就算成功。」（props 的 `multi`）。
- 按钮均需 `min-height: 0`（同上，覆盖全局 44px）。

## PlaybackVolumePopover.vue

```ts
defineProps<{
  mediaVolume: number
  beatVolume: number
  beatVolumeMax: number    // 300
  textOpacity: number
  textScale: number
  textOpacityMin: number   // 30
  textScaleMin: number     // 60
}>()
defineEmits<{ update: [payload: { key: 'mediaVolume' | 'beatVolume' | 'textOpacity' | 'textScale'; value: number }] }>()
```

- 右上卡片：`width: min(288px, calc(100vw - 24px))`、`border: 1px solid rgba(255,255,255,.15)`、`background: rgba(0,0,0,.95)`、圆角 12px。
- 四行滑杆：视频音量 0–100 / 节拍声 0–`beatVolumeMax` / 指令文字不透明度 / 指令文字大小，每行下方一行 10.5px 说明（照抄参考站文案）。
- **不含**心跳音量与视频变暗——这两项在设置面板的「声音」「其他」组。

## PlaybackGuide.vue

```ts
defineProps<{ steps: GuideStep[]; open: boolean }>()
defineEmits<{ close: [skipped: boolean] }>()
```

- 遮罩 + 居中卡片，顶部 `{{ current + 1 }} / {{ steps.length }}`。
- 按钮：「跳过」（`close(true)`）、「上一步」、末步「开始」（`close(false)`）、其余「下一步」。
- 键盘：`Esc` = 跳过，`←`/`→` 翻页；`role="dialog"` `aria-modal="true"`。
- 步数由 `steps` 决定，**不要写死**。

## guideSteps.ts

导出 `guideSteps: GuideStep[]`（10 步，文案对齐参考站：照着指示做（绿黄红三色）、忍住了、射了、视频快进／快退 10 秒、换个视频、视频大小、悬浮小窗、音量、横屏、暂停・退出）与
`readGuideSeen()` / `markGuideSeen()`（localStorage 键 `shicun.edge.guide.v2`，读写失败一律当没看过）。

## sound.ts

`class SoundEngine`：`ensure()` / `suspend()` / `resume()` / `close()` + `beat(mode, options)` / `cue(options)` / `heartbeat(options)`。
全部用 WebAudio 振荡器实时合成，**没有音频文件、没有语音播报**。详见实施契约。

## 二、本机存储（`web/src/playback.ts` 与 `web/src/playback/settings.ts`）

- 媒体层：`shicun.playback.v1`，`schemaVersion = 4`，`format = shicun.playback.config.v4`；`Playlist` **只剩媒体字段**，旧 v1–v3 存档升级时丢弃已作废的玩法字段。
- 玩法层：`shicun.edge.v1`，`edgeSchemaVersion = 1`，`EdgeSettings` 见实施契约。
- 本机成绩：`shicun.edge.stats.v1`（`web/src/playback/history.ts`，`sessions/success/ruin/fail/edges/minutes/longest`，只存本机、不上传）。
- 引导已读标记：`shicun.edge.guide.v2`（`web/src/playback/guideSteps.ts`）。
- `readPreferences` 遇到旧版本按字段补默认值后升级；结构性损坏才抛错，其余补齐并返回 `issues`。
- 新增字段必须同时出现在接口、默认值、`validPlaylist` / `normalizeEdgeSettings` 三处。
- `shownImages` 上限 20000 条，超出按最早记录淘汰。

## 三、设置页（`PlaybackSettings.vue`）

- 入口不变：`defineModel<EdgeSettings>({ required: true })` + `defineProps<{ runtime?: boolean; media?: Playlist }>()`。
- 单卡片：卡片头（标题 + 实时摘要行）+ 搜索框 + 分组标签 + 分组内容；摘要行由 `summary.ts` 的 `settingsSummary(settings)` 生成。
- 五组：玩法 / 指令 / 视频·图片 / 声音 / 其他，`runtime` 时隐藏「视频·图片」。每组都有「恢复本组」二次确认。
- 摘要行格式形如 `10 分钟 · 普通 · 抽签 · 指令 88 种 · 许可率 70% · 不许碰 5–10 秒 · 节拍声开`。
- 「其他」组含镜子（前置摄像头）：开关先弹同意卡（`mirrorText.consentTitle/consentBody`），点「允许使用摄像头」才 `getUserMedia`；
  失败按 `classifyMirrorError` 出中文提示并保持关闭；开启后可选位置（`铺满背景（调暗）` / `右下角小窗`）。
