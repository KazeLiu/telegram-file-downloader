# 寸止控制器实施契约（v3）

基线：提交 `0713e83`（运行层已复刻为覆盖视口的沉浸层，存储 `schemaVersion = 2`）。
本文是三路并行实现的唯一契约源，字段名与导出名一律以此为准，不得改动。

## 定位

本项目播放器是**寸止（edge play）控制器**：按绿／黄／红相位循环播放本机媒体与节拍，
玩家在临界点按「忍住了」累积许可率，时间到后由结局设置判定是否给许可。
不做：双人、远程指挥、摄像头、分享链接、成绩历史、广告弹窗。

## 相位映射（复用既有 `PhaseKind`）

| 语义 | 颜色 | `PhaseKind` | 时长（随机） | 动作 |
| --- | --- | --- | --- | --- |
| 可以撸 | 绿 | `fast` | 18–31 秒 × 指令时长倍率 | 跟进节拍 |
| 慢慢来 | 黄 | `slow` | 18–31 秒 × 指令时长倍率 | 降速 |
| 不许碰 | 红 | `rest` | 10–16 秒（**不乘倍率**） | 松手 |

## 新增存储字段（`Playlist`，`schemaVersion` 升到 3）

全部为可选读入、缺省补默认；旧 v1/v2 数据必须无损迁移。

| 字段 | 类型 | 默认 |
| --- | --- | --- |
| `difficulty` | `'easy' \| 'normal' \| 'hard' \| 'hell'` | `'normal'` |
| `ratioFast` / `ratioSlow` / `ratioRest` | 0–100 整数，三者合计 100 | 60 / 20 / 20 |
| `permitBase` | 30–95 整数 | 70 |
| `ending` | `'draw' \| 'always' \| 'never' \| 'ruin' \| 'continuous' \| 'overtime'` | `'draw'` |
| `edgeWindow` | 5–60 整数（秒） | 10 |
| `waitMode` | `'random' \| 'fixed'` | `'random'` |
| `waitPreset` | `'8-16' \| '10-40' \| '20-60'` | `'8-16'` |
| `waitMin` / `waitMax` | 3–120 整数，`waitMin <= waitMax` | 8 / 16 |
| `instructionPace` | `'standard' \| 'long' \| 'veryLong'` | `'standard'` |
| `tones` | `Tone[]`（`'firm' \| 'tease' \| 'degrade' \| 'gentle'`） | `['firm']` |
| `hand` | `'right' \| 'left'` | `'right'` |
| `commandTypes` | `string[]`（见 `commandTypeLabels` 键） | 全部 |
| `props` | `string[]`（`'cup' \| 'aneros'`） | `[]` |
| `customCommands` | `{ text: string; type: CommandType }[]`，≤30 条，`text` ≤60 字 | `[]` |
| `disabledCommands` | `string[]`（内置口令 id） | `[]` |
| `heartbeat` | boolean | `true` |
| `heartbeatVolume` | 0–100 整数 | 100 |
| `vibrate` | `'off' \| 'switch' \| 'edge' \| 'ending'` | `'off'` |
| `voicePitch` | `'auto' \| 'low' \| 'normal' \| 'high'` | `'auto'` |

已有字段保持不动：`minutes / loop / imageSeconds / imageTiming / bpm / imageCount / order / kind /
favoritesOnly / metronome / speech / speechRate / mediaVolume / beatVolume / speechVolume / hideTime / brightness`。

**新增字段必须同步三处**：`addedDefaults`、`validPlaylist`、`normalizePreferences`（`web/src/playback.ts`）。

## 纯逻辑模块 `web/src/playback/edge.ts`（A 负责）

只导出常量与纯函数，不依赖 Vue、不碰 `localStorage`、不 import `../playback`（避免循环依赖）。

```ts
export type Difficulty = 'easy' | 'normal' | 'hard' | 'hell'
export type Ending = 'draw' | 'always' | 'never' | 'ruin' | 'continuous' | 'overtime'
export type Tone = 'firm' | 'tease' | 'degrade' | 'gentle'
export type CommandType = 'fast' | 'slow' | 'rest' | 'tease' | 'nipple' | 'glans'
export interface Command { id: string; type: CommandType; text: string }

export const difficultyProfiles: Record<Difficulty, { label: string; fast: number; slow: number; rest: number; permit: number }>
export const difficultyOrder: Difficulty[]
export const endingOrder: Ending[]
export const endingLabels: Record<Ending, string>       // 抽签/必定允许/必定禁止/松手射精/连续/加时赛
export const endingHints: Record<Ending, string>
export const toneLabels: Record<Tone, string>           // 强硬/挑逗/辱骂/温柔
export const commandTypeLabels: Record<CommandType, string>  // 撸/慢/不许碰/挑逗/只玩乳头/只玩龟头
export const propLabels: Record<string, string>         // cup: 飞机杯, aneros: 前列腺按摩器
export const voicePitchLabels: Record<string, string>
export const vibrateLabels: Record<string, string>
export const waitPresets: { id: '8-16' | '10-40' | '20-60'; label: string; min: number; max: number }[]
export const instructionPaceRatios: Record<'standard' | 'long' | 'veryLong', number>  // 1 / 1.5 / 2.5
export const edgeWindowOptions: number[]                // [5,10,20,30,45,60]
export const permitStep = 5
export const permitMaxGain = 20
export const overtimeStep = 15
export const overtimeLimit = 5
export const builtinCommands: Command[]                 // 见下

export function nextPermitRate(base: number, heldCount: number): number
export function resolveEnding(ending: Ending, rate: number, random: () => number, overtimeCount?: number): 'allow' | 'deny' | 'ruin'
export function pickPhaseKind(ratioFast: number, ratioSlow: number, ratioRest: number, previous: PhaseKind | null, random: () => number): PhaseKind
export function phaseDurationMs(kind: PhaseKind, pace: 'standard' | 'long' | 'veryLong', random: () => number): number
export function waitDurationMs(mode: 'random' | 'fixed', preset: '8-16' | '10-40' | '20-60', min: number, max: number, random: () => number): number
export function commandPool(types: CommandType[], custom: { text: string; type: CommandType }[], disabled: string[]): Command[]
export function pickCommand(pool: Command[], lastId: string, random: () => number): Command | null
```

`PickPhaseKind` 规则：按三比例抽签（合计不为 100 时按归一化处理），**抽到的相位等于 `previous` 时重抽一次**，仍相同则顺延到下一个非零相位。
`phaseDurationMs`：`rest` 为 10–16 秒且**不乘** `instructionPaceRatios`；`fast`/`slow` 为 18–31 秒乘倍率。
`resolveEnding`：`always` → `'allow'`；`never` → `'deny'`；`ruin` → `random() < 0.5 ? 'ruin' : 'deny'`；
`continuous` / `overtime` / `draw` → `random() * 100 < rate ? 'allow' : 'deny'`（`overtime` 在 `overtimeCount >= overtimeLimit` 时直接 `'allow'`）。

**内置口令 `builtinCommands` 写法约束**：短句、命令式、每条 ≤18 字、不写露骨细节，
六类各 4 条，`id` 形如 `fast-1` / `rest-2`。示例口径：
`{ id: 'rest-1', type: 'rest', text: '停，手拿开' }`、`{ id: 'slow-2', type: 'slow', text: '慢下来，只用掌心' }`、
`{ id: 'fast-1', type: 'fast', text: '跟着节拍，再快一点' }`、`{ id: 'tease-1', type: 'tease', text: '只用指尖' }`。
玩家自己的内容走 `customCommands`，不在内置表里扩写。

## 运行层接线（Lead 负责）

`web/src/PlaybackPanel.vue`：

- `player` 新增 `held: number`（忍住次数）、`permit: number`（当前许可率）、`phaseEndsAt`、`allowed: boolean`、`windowLeft: number`、`overtimeCount: number`。
- 主操作按钮文案改回 **「忍住了」**，按下：`held++`、`permit = nextPermitRate(permitBase, held)`、切到 `rest` 相位并进入等待时长；按钮下方常驻小字 `按在快忍不住的前一刻。按下后松手等它平息`。
- 次级按钮 `射了` → `finish('edge')`（记为失败结束）。
- 顶栏计数由「喜欢 N」改为 **「忍住 N」**（`PlaybackTopBar` 的 `likes` prop 改名 `held`）。
- 时间到 → 若结局判定 `allow`：进入许可窗口（`edgeWindow` 秒，`PlaybackBottom` 进度条换成白色倒计时条，中央提示「现在可以了」）；
  窗口结束或 `ruin` → `finish('duration')`。判定 `deny` → `finish('deny')`。
- 结局运行中可再次延长：`overtime` 结局在 `deny` 后加时（每次 +15%，第 5 次必定允许），中央显示「加时 N」。
- `finish(reason)` 的 `FinishReason` 扩展为 `'duration' | 'queue' | 'manual' | 'edge' | 'deny' | 'allow'`，
  对应完成卡文案：`edge` → 「这次没忍住」、`deny` → 「一直忍到结束，没给许可」、`allow` → 「许可已给出」。

## 设置页五组（B 负责）

`web/src/PlaybackSettings.vue` 分组按参考站语义重排为 **玩法 / 指令 / 内容 / 声音 / 其他**，
`runtime` 模式下只显示 声音 / 内容以外的播放相关项按既有规则隐藏（保持现有 `runtime` 分支语义，不新增入口）。

| 组 | 字段 |
| --- | --- |
| 玩法 | 总时长 `minutes`、难度 `difficulty`、自己调三比例 `ratioFast/ratioSlow/ratioRest` + `permitBase`（折叠）、结局 `ending`、许可窗口 `edgeWindow`、忍住后等待 `waitMode/waitPreset/waitMin/waitMax`、指令时长 `instructionPace` |
| 指令 | 口吻 `tones`（多选）、类型开关 `commandTypes`、惯用手 `hand`、道具 `props`、自定义口令 `customCommands`（增删，≤30）、逐条启停 `disabledCommands`（折叠列出 `builtinCommands`，按类型分组） |
| 内容 | 内容类型 `kind`、播放顺序 `order`、每轮图片数 `imageCount`、图片间隔 `imageSeconds`、切图节奏 `imageTiming`、快速节拍 `bpm`、循环 `loop`、仅播放喜欢 `favoritesOnly` |
| 声音 | 节拍器 `metronome` + `beatVolume`、心跳 `heartbeat` + `heartbeatVolume`、语音 `speech` + `speechVolume` + `speechRate` + `voicePitch`、媒体音量 `mediaVolume`、振动 `vibrate` |
| 其他 | 隐藏时间 `hideTime`、画面亮度 `brightness` |

摘要行 `web/src/playback/summary.ts` 的 `playbackSummary` 追加：难度、结局、许可率，例如
`10分钟 · 普通 · 抽签 · 许可率 70%· 口令 88 条` 的空段省略规则不变。

## 验收

- `cd web && pnpm exec vue-tsc -b`、`pnpm run build` 均 exit 0。
- `node web\checks\playback.ts`、`node web\checks\playback-loader.ts` 保持 exit 0。
- 新增 `node web\checks\edge.ts`：覆盖 `nextPermitRate` 上限、`pickPhaseKind` 不连续同相位、`phaseDurationMs` 的 rest 不乘倍率、`resolveEnding` 六种结局分支、`waitDurationMs` 随机档落在区间内、`pickCommand` 不重复上一条。

## 实现偏差（以本节为准）

契约落笔后按实现修正了三处，后续改动请以这里为准：

1. **结束原因扩到 7 值**：`FinishReason` 为 `duration | queue | manual | allow | deny | ruin | edge`。许可窗口走完记 `allow`（「许可已给出」）、忍到结束没给许可记 `deny`（「一直忍到结束，没给许可」）、松手射精记 `ruin`、手点「射了」记 `edge`（「这次没忍住」）。本文前面提到的「窗口结束与 ruin 记 duration、deny 记 deny」作废。
2. **不加 `player.phaseEndsAt`**：运行层继续用 `phaseElapsed / phaseDuration`。暂停时 `phaseElapsed` 冻结，时间戳方案会在恢复后漂移。
3. **`allow` 中央提示走台词表**：优先 `pickVoiceLine('ending-allow')`，取不到才回退「现在可以了」。
