# 播放器改造组件契约（2026-11-13）

本文件是并行实现的接口约定。三份子任务按此实现，`PlaybackPanel.vue` 的集成方按此接线；**任何一方不得擅自改签名**，需要改先在本文件登记。

共享类型与文案常量在 `web/src/playback/types.ts`（已存在，只读）：

- `PhaseKind = 'slow' | 'fast' | 'rest'`
- `phaseLabels` / `phaseHints` / `phaseRatios` / `phaseLegend` / `keyHints` / `finishLabels`
- `GuideStep { title: string; body: string }`
- `PlaybackPosition { index: number; total: number; cycle: number }`
- `FinishReason = 'duration' | 'queue' | 'manual'`

## 一、运行层组件（`web/src/playback/`）

全部是纯展示组件：只在自身内部持有 UI 局部状态，**不改业务状态、不读 localStorage、不发请求**。样式用 `scoped`，颜色走现有变量（`--color-primary`、`--color-primary-on-dark`、`--color-hairline`、`--color-muted`），暗色底用 `#000` / `#272729` / `#dccbd3`。

### PlaybackOverlay.vue

运行层外壳：铺满视口、四角分层、背景随阶段变色。

```ts
defineProps<{
  phase: PhaseKind
  paused: boolean
  beatIntervalMs: number   // 0 表示当前阶段没有节拍
  dim: number              // 20–100，画面暗度
}>()
```

- 根节点 `position: fixed; inset: 0; z-index: 60; background: #000;`，class 带 `playback-overlay`，并输出 `data-phase` 与 `data-paused`。
- 三层渐变叠在媒体之下，`[data-phase="slow"|"fast"|"rest"]` 只切 `opacity`，**不要动 background 做过渡**。
- 节拍光晕：`--beat-interval: calc(60s / var(--bpm))` 由 prop 写进 `el.style.setProperty`；`beatIntervalMs` 为 0 时不渲染光晕。`paused` 时 `animation-play-state: paused`。
- 插槽：`top`、`stage`、`bottom`，分别固定在顶部、中央、底部三个区域；`stage` 之外的区域不遮挡媒体点击。
- 支持 `prefers-reduced-motion`：关掉动画只保留颜色。

### PlaybackTopBar.vue

```ts
defineProps<{
  name: string
  position: PlaybackPosition
  remaining: string        // 已格式化，如 '08:12'；不限时传 ''
  hideTime: boolean
  paused: boolean
  fullscreen: boolean
  settingsOpen: boolean
  playing: boolean         // false 时暂停/退出按钮禁用
}>()
defineEmits<{
  back: []
  settings: []
  fullscreen: []
  togglePause: []
  exit: []
}>()
```

- 左：返回按钮（aria-label「返回播放列表」）+ 名称（省略号）+ `第 {{ position.cycle }} 轮 · {{ position.index + 1 }} / {{ position.total }}`。
- 右：剩余时间（`hideTime` 为真时不渲染）+ 设置 + 全屏 + 暂停／继续（按 `paused` 换图标与 aria-label）+ 退出。
- 所有按钮 `min-height/min-width: 44px`，`:focus-visible` 用 `--color-primary-on-dark`。
- 图标复用 `../Icon.vue`（`chevron`/`settings`/`fullscreen`/`pause`/`play`/`close`），图标名必须存在于 `Icon.vue`，缺的先用文字。

### PlaybackStage.vue

```ts
defineProps<{
  phase: PhaseKind
  bpm: number              // 0 表示无节拍
  paused: boolean
  finished: boolean
  loading: boolean
  error: string
}>()
```

- 中央：阶段大字（`phaseLabels[phase]`）+ `{{ bpm }} BPM`（`bpm` 为 0 或 `paused` 时不显示）+ 提示（`phaseHints[phase]`）。
- `paused` 时中央换成「已暂停」并显示「点下方继续，或按空格」；此时**不显示 BPM**。
- `finished` 时中央换成「已结束」。
- 插槽：`default`（媒体本体）、`actions`（错误时的按钮组）。`loading` 时显示「正在加载…」，`error` 非空时用 `role="alert"` 展示错误并只保留 `actions` 插槽可点。
- 媒体插槽容器 `position: absolute; inset: 0`，中央信息层 `pointer-events: none`（按钮区除外）。

### PlaybackBottom.vue

```ts
defineProps<{
  elapsed: string
  total: string            // 不限时传 ''
  progress: number         // 0–100
  hideTime: boolean
}>()
```

- 上部：进度条（`hideTime` 或 `total` 为空时不渲染）+ `{{ elapsed }} / {{ total }}`。
- 中部：`phaseLegend` 图例（小圆点 + 文字，`hideTime` 不影响）。
- 底部：插槽 `controls`（主控制按钮），右侧小字 `keyHints` 键盘提示（窄屏隐藏）。
- 全局只读常量直接 `import`，**不要在组件里重复写文案**。

### PlaybackFinished.vue

```ts
defineProps<{
  reason: string           // 直接用 finishLabels 的结果
  elapsed: string
  position: PlaybackPosition
}>()
defineEmits<{ restart: []; close: [] }>()
```

- 独立结束卡（不是运行层的一部分）：居中卡片，标题「本次播放结束」，正文 `reason`、`本次播放 {{ elapsed }}`、`完成第 {{ position.cycle }} 轮 · {{ position.index + 1 }} / {{ position.total }} 项`。
- 按钮：「再来一次」（primary）、「返回播放列表」。
- `role="status"` + `aria-live="polite"`，卡片可聚焦。

### PlaybackGuide.vue

```ts
defineProps<{ steps: GuideStep[]; open: boolean }>()
defineEmits<{ close: [skipped: boolean] }>()
```

- 遮罩 + 居中卡片，顶部 `{{ current + 1 }} / {{ steps.length }}`，标题 `steps[current].title`，正文 `steps[current].body`。
- 按钮：「跳过」（`close(true)`）、「上一步」（首步禁用或隐藏）、末步「开始」（`close(false)`）、其余「下一步」。
- 键盘：`Esc` = 跳过，`←`/`→` 翻页；焦点进入卡片，`role="dialog"` `aria-modal="true"`。
- **步数由 `steps` 数组决定，不要写死 5。**

### guideSteps.ts

导出 `guideSteps: GuideStep[]`（本项目 5 步：怎么切图、三档颜色各是什么、怎么暂停与继续、键盘与手势、怎么结束）与 `readGuideSeen(): boolean` / `markGuideSeen(): void`（localStorage 键 `shicun.playback.guide.v1`，读失败一律当没看过）。

## 二、本机存储（`web/src/playback.ts`）

- 加 `schemaVersion`，当前值 `2`；`readPreferences` 遇到旧版本按字段补默认值后升级，**升级不丢数据**。
- 新增字段必须同时出现在 `Playlist` 接口、`addedDefaults`、`validPlaylist` 三处（这是已知的连带修改点）。
- 校验失败仍抛出可读错误，但错误文案要说明「哪些字段」并且**不再把「重置」当唯一出路**：能补默认值的字段补齐，只有结构性损坏才抛错。
- `shownImages` 加容量上限（例如 20000 条或按字符数），超出时按最早记录淘汰。
- 导出/导入的 `format` 版本同步升级，旧文件仍能导入。

## 三、设置页（`PlaybackSettings.vue`）

- 保持 `defineModel<Playlist>({ required: true })` 与 `runtime?: boolean` 两个入口不变，**调用方不改**。
- 改成单卡片：卡片头（标题 + 实时摘要行）+ 搜索框 + 分组标签 + 分组内容，摘要行随编辑实时变化。
- 摘要行由 `web/src/playback/summary.ts` 的 `playbackSummary(item: Playlist): string` 生成，格式形如 `10 分钟 · 仅图片 · 每张 8 秒 · 全部未展示图片 · 节拍器关`。
- 分组仍为「播放／媒体（runtime 时隐藏）／声音／显示」，保持现有搜索关键字能力。
