# 寸止控制器实施契约（v4）

基线：分支 `feat/playback-edge-parity`（播放器按 100adults 男生版一寸止复刻，无联机、无语音播报）。
本文是当前实现的唯一契约源：字段名、导出名、数值一律以此为准。

## 定位

本项目播放器是**寸止（edge play）控制器**：按绿／黄／红三档模式循环播本机媒体与节拍，
玩家在临界点按「忍住了」累积许可率，时间到后由结局设置判定是否给许可。

不做：双人 / 远程指挥、摄像头、分享链接、排行榜、语音播报、音频文件加载。

## 与 v3 的差异（迁移要点）

| 项 | v3（旧） | v4（当前） |
| --- | --- | --- |
| 相位 | `PhaseKind = slow \| fast \| rest` | `EdgeMode = go \| slow \| stop`（语义同上，键名换） |
| 玩法字段位置 | `Playlist` 里（`schemaVersion = 3`） | 独立 `EdgeSettings`（`shicun.edge.v1`），`Playlist` 只留媒体层 |
| 播放列表存储 | `shicun.playback.v1` + `schemaVersion = 3` | `shicun.playback.v1` + `schemaVersion = 4`（旧 v1–v3 自动升级，玩法字段丢弃） |
| 引擎模块 | `web/src/playback/edge.ts` | `web/src/playback/engine.ts`（已删除 edge.ts） |
| 指令池 | `builtinCommands` 24 条短句 | `commands.ts` 里 88 条结构化口令 + 乳头／龟头各 5 条 |
| 语音 | `voiceLines.ts` + `speechSynthesis` | 已删除，不再有任何语音 |
| 节拍音量上限 | 100 | 300（`beatVolumeMax`） |
| 一句话命令 | 24 条固定短句 | 88 条各带 `mode / category / bpm / seconds / hint` |

旧 v3 契约里 `ratioFast / permitBase / ending / edgeWindow / waitMode / waitPreset / waitMin / waitMax /
instructionPace / tones / commandTypes / props / customCommands / disabledCommands / voicePitch / vibrate`
全部作废，等价概念见下。

## 模式（`EdgeMode`）

| 语义 | 颜色 | `mode` | 时长（随机，秒） | 动作 |
| --- | --- | --- | --- | --- |
| 可以撸 | 绿 | `go` | 难度表 `seconds.go` | 手跟节拍 |
| 慢慢来 | 黄 | `slow` | 难度表 `seconds.slow` | 降速、挑逗 |
| 不许碰 | 红 | `stop` | 难度表 `seconds.stop` | 松手 |

色值：`modeColors = { go: '#5ee3a1', slow: '#f0c35a', stop: '#ff6b7d' }`，
亮一档 `modeColorsBright = { go: '#86e3bb', slow: '#f7d78a', stop: '#ff9aa6' }`。
文案 `modeLabels = { go: '可以撸', slow: '慢慢来', stop: '不许碰' }`。

## 难度表（`engine.ts` 的 `difficulties`）

```ts
interface DifficultyProfile {
  chance: number                       // 最终获得许可的基础概率（0–1）
  share: Record<EdgeMode, number>      // 相位时间占比（自己调 → 覆盖）
  seconds: Record<EdgeMode, [number, number]>  // 单条指令秒数区间
  stopAfterStop: boolean               // 是否允许「不许碰」连出
}
```

| 难度 | 许可率 | go | slow | stop | go 秒 | slow 秒 | stop 秒 | stop 连出 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `easy` 简单 | 85% | 0.56 | 0.20 | 0.24 | 15–30 | 8–16 | 4–8 | 否 |
| `normal` 普通 | 70% | 0.38 | 0.20 | 0.42 | 12–25 | 8–16 | 5–10 | 否 |
| `hard` 困难 | 50% | 0.39 | 0.25 | 0.36 | 8–18 | 6–14 | 6–14 | 是 |
| `hell` 地狱 | 30% | 0.35 | 0.22 | 0.43 | 6–14 | 6–12 | 8–18 | 是 |

`instructionLength` 三档只放大 `go` / `slow`：`long` → 60–120 秒，`veryLong` → 120–300 秒；
`stop` **永远不吃倍率**，指令自带 `seconds` 时以指令为准。

## 存储：`web/src/playback/settings.ts`

存 key `shicun.edge.v1`，`edgeSchemaVersion = 1`。全部字段可选读入、缺失补默认，越界一律夹取。

| 字段 | 类型 | 默认 |
| --- | --- | --- |
| `seed` | `number`（0 = 每局随机） | 0 |
| `minutes` | 1–180 整数 | 10 |
| `durationRandom` | boolean（每局 5–20 分钟随机、并隐藏剩余时间） | `false` |
| `difficulty` | `'easy' \| 'normal' \| 'hard' \| 'hell'` | `'normal'` |
| `instructionLength` | `'standard' \| 'long' \| 'veryLong'` | `'standard'` |
| `finale` | `'draw' \| 'always' \| 'never' \| 'ruin' \| 'continuous' \| 'overtime'` | `'draw'` |
| `categories` | `{ edge, tease, pose, pain }: boolean` | edge/tease/pose `true`，pain `false` |
| `tune` | `{ chance: 10–100 \| null, stop: 0–60 \| null, mix: {go,slow,stop} \| null }` | 全 `null` |
| `allowRuin` | boolean（拿到许可也按松手射精收场） | `false` |
| `extendLen` | `'short' \| 'normal' \| 'shrink'`（加时赛的加时长度） | `'normal'` |
| `rewardSeconds` | 5/10/20/30/45/60 | 10 |
| `rest` | `{ mode: 'random' \| 'fixed', seconds, min, max }`，3–120 | `random / 12 / 8–16` |
| `hand` | `'right' \| 'left'`（左手会把口令里的左右手对调） | `'right'` |
| `custom` | `{ text, mode }[]`，≤30 条、每条 ≤60 字 | `[]` |
| `disabled` | `number[]`（内置口令的**下标**） | `[]` |
| `nipple` / `glans` | `{ on: boolean, times: 1–4 }`（整局中途插入几段专属指令） | `{ on: false, times: 1 }` |
| `focus` | `'none' \| 'nipple' \| 'glans'`（整局只玩一个部位：开了就不再插入中途专属段，指令池整局换成该部位专属池） | `'none'` |
| `redBeat` | `'heartbeat' \| 'both' \| 'metronome'` | `'heartbeat'` |
| `heartbeat` / `metronome` | boolean | `true` / `true` |
| `heartbeatVolume` / `beatVolume` | 0–300 整数 | 100 / 100 |
| `mediaVolume` | 0–100 整数 | 60 |
| `dim` | 0–100 整数（0 完全透明=视频原本亮度，100 最暗 0.45 遮罩；对齐参考站的 `dim`） | 55 |
| `hideRemaining` | boolean | `false` |
| `mixAudio` | boolean | `false` |
| `keepVideoOnStop` | boolean（红色时也继续放视频、不变暗） | `false` |
| `switchVideoPerCommand` | boolean（每换一条指令就切下一个视频） | `false` |
| `bpmRandom` | `{ on: boolean, min: 20–300, max: 20–300 }`（开启后每条绿黄指令的 BPM 在范围内重随机，红色固定 60 不参与） | `{ on: false, min: 60, max: 160 }` |
| `heartbeatSync` | boolean（心跳跟随 BPM；关掉后红色带 BPM 时心跳仍固定 60） | `true` |
| `vibrate` | boolean（仅手机有效） | `true` |
| `vibrateOn` | `{ command, edge, finish }: boolean` | 全 `true` |
| `toy` | boolean（飞机杯道具模式：并入 20 条道具口令，并剔除 `bareHand` / `shaft` 的手部口令） | `false` |
| `aneros` | boolean（前列腺按摩器：红色段并入 6 条夹紧口令） | `false` |
| `tones` | `Record<ToneKind, boolean>`（强势/挑逗/羞辱/温柔/足控，多选时按条轮流） | 全 `false` |
| `toneLine` | `{ show: boolean, before: boolean, after: 'never' \\| 'half' \\| 'always' }` | `{ true, true, 'half' }` |
| `fit` | `'cover' \\| 'contain'`（铺满 / 显示完整画面） | `'cover'` |
| `pos` | `'top' \\| 'center' \\| 'bottom'`（仅 `contain` 生效） | `'center'` |
| `textOpacity` | 30–100 整数（指令文字不透明度） | 100 |
| `textScale` | 60–140 整数（指令文字大小） | 100 |
| `keepVideoWhileCooling` | boolean（按“忍住了”之后的等待时间也继续放视频） | `true` |
| `videoSound` | `'off' \\| 'end' \\| 'always'`（视频声音） | `'end'` |
| `skipIntro` | boolean（视频从中间开始播放） | `false` |
| `mirror` | `{ on: boolean, place: 'bg' \\| 'corner' }`（前置摄像头，仅在播放中开启） | `{ false, 'corner' }` |

导出：`edgeStorageKey`、`edgeSchemaVersion`、`defaultEdgeSettings`、`normalizeEdgeSettings(raw)`、
`readEdgeSettings(value: string | null)`、`writeEdgeSettings(settings): string`（返回错误串，空串＝成功）。

## 引擎：`web/src/playback/engine.ts`

纯常量与纯函数，不依赖 Vue、不碰 `localStorage`、不 import `../playback`。

```ts
export type Difficulty = 'easy' | 'normal' | 'hard' | 'hell'
export type Finale = 'draw' | 'always' | 'never' | 'ruin' | 'continuous' | 'overtime'
export type InstructionLength = 'standard' | 'long' | 'veryLong'
export type RestMode = 'random' | 'fixed'
export type Hand = 'right' | 'left'
export type RedBeat = 'heartbeat' | 'both' | 'metronome'
export type EdgeMode = 'go' | 'slow' | 'stop'
export type CategoryKind = 'edge' | 'tease' | 'pose' | 'pain'
export interface Mix { go: number; slow: number; stop: number }
export interface Tune { chance: number | null; stop: number | null; mix: Mix | null }
export type Random = () => number

export const difficulties: Record<Difficulty, DifficultyProfile>
export const difficultyOrder: Difficulty[]              // ['easy','normal','hard','hell']
export const difficultyLabels / difficultyHints: Record<Difficulty, string>
export const modeOrder: EdgeMode[]                      // ['go','slow','stop']
export const modeLabels / modeColors / modeColorsBright: Record<EdgeMode, string>
export const finaleOrder: Finale[]                      // 六种结局
export const finaleLabels / finaleHints: Record<Finale, string>
export const categoryOrder / categoryLabels / categoryHints
export const presets / presetOrder / presetLabels        // first / standard / long
export const instructionLengthOrder / instructionLengthLabels
export const restModeOrder / restModeLabels
export const toneOrder / toneLabels / toneAfterOrder / toneAfterLabels
export const redBeatOrder / redBeatLabels
export const rewardChoices = [5,10,20,30,45,60]
export const durationChoices = [3,5,10,15,20,30]
export const durationMin = 1 / durationMax = 180
export const restMin = 3 / restMax = 120
export const restRangeChoices = [[8,16],[10,40],[20,60]] / restFixedChoices
export const bpmRandomMin = 20 / bpmRandomMax = 300
export const beatVolumeMax = 300 / videoVolumeMax = 100 / dimMin = 0
export const textOpacityMin = 30 / textScaleMin = 60
export const customCommandLimit = 30 / customCommandTextLimit = 60
export const finalHoldMs = 5000 / permitStep = 0.05 / permitMaxGain = 0.2
export const multiRounds = 4 / multiRoundSeconds = 25

export function mulberry32(seed: number): Random
export function randomSeed(): number
export function shareOf(difficulty: Difficulty, tune: Tune | null): Record<EdgeMode, number>
export function timeShareOf(difficulty: Difficulty, tune: Tune | null): Record<EdgeMode, number>
export function mixOf(difficulty: Difficulty, tune: Tune | null): Mix
export function adjustMix(mix: Mix, mode: EdgeMode, value: number): Mix
export function taskSeconds(difficulty: Difficulty, mode: EdgeMode, random: Random, length: InstructionLength): number
export function permitRate(difficulty: Difficulty, held: number, chance: number | null): number
export function decideFinale(finale: Finale, difficulty: Difficulty, held: number, random: Random, chance: number | null, allowRuin: boolean): 'success' | 'fail' | 'ruin'
export function restSeconds(rest: EdgeRest, random: Random): number
export function randomBpm(range: { min: number; max: number }, mode: EdgeMode, random: Random): number
export function planFocus(times: number, totalMs: number, random: Random, kind: 'nipple' | 'glans'): number[]
export function pickIndex<T>(items: T[], random: Random): T | null
export function pickMode(options: PickOptions): EdgeMode | null
export function pickCommandAt(mode: EdgeMode, random: Random, previous: EdgeCommand | null, pool: EdgeCommand[]): EdgeCommand | null
export function swapHands(text: string): string
export function commandPool(disabled: number[], custom: CustomCommand[], hand: Hand, base?: EdgeCommand[]): EdgeCommand[]
export function filterByCategories(pool: EdgeCommand[], categories: Categories): EdgeCommand[]
export function buildTimeline(options: TimelineOptions): Task[]
export function bindCommands(tasks: Task[], pool: EdgeCommand[], nipplePool?: EdgeCommand[], glansPool?: EdgeCommand[]): Task[]
export function taskAt(tasks: Task[], at: number): Task | null
export function formatClock(ms: number): string   // 'm:ss'
export function toneForTask(tones: Record<ToneKind, boolean>, count: number): ToneKind | 'normal'
export function pickToneLine(lines: ToneLine, random: Random, options: { before: boolean; after: ToneAfter }): { before?: string; after?: string }
export function toneAfterForCommand(command: { category: string } | null, after: ToneAfter): ToneAfter
export function varyBpm(
  command: EdgeCommand | null,
  range: { on: boolean; min: number; max: number } | null,
  random: Random,
): EdgeCommand | null
```

规则要点：

- `permitRate` = `min(1, 基础概率(或 tune.chance/100) + min(0.2, 0.05 × 忍住次数))`，即每次 +5%、累计最多 +20%、封顶 100%。
- `decideFinale`：`always` / `continuous` → `success`；`never` → `fail`；`ruin` → `ruin`；
  `draw` → `random() < permitRate(...)`；`allowRuin` 为真时 `success` 改判 `ruin`。
  `overtime` 不走这里：它在 `settle()` 里先按 `extendChance(permitRate(...), extends)` 判定，
  没中才加时（见下）。
- `extendChance(chance, times)` = `times >= 5 ? 1 : min(1, chance + 0.15 × times)`，即每次加时 +15%，
  **第 5 次加时必中**。
- `extendMs(length, times, random)`：`short` 固定 1–3 分钟、`normal` 固定 2–5 分钟；
  `shrink` 按第几次递减（1 次 5–10、2 次 3–5、3 次 2–3、4 次起 1 分钟）。
- `pickMode`：**第一段强制 `go`**；默认不连续出 `stop`（`stopAfterStop` 的难度除外）；
  自己调里 `stop` 占比 > 45% 时放开连出。
- `buildTimeline`：整局时间线**一开始就全部预生成**，按 `shareOf` 加权抽模式；
  末尾不足 `finalHoldMs` 的尾巴并进最后一段；乳头／龟头专属段按 `planFocus` 的计划时间插入，
  **两段专属之间至少隔一条普通指令**（按 `previousFocus` 判断，不是一次性布尔量）。
- `bindCommands`：指令自带 `seconds` 时改写该段时长并把后续 `at` 顺移。
- 节拍 BPM 优先用**指令自带 `bpm`**，缺省回落到播放列表的 `bpm`。
- `toneForTask`：开着几种口吻就按「第几条指令」轮流用（`((count-1) % n + n) % n`），没开返回 `normal`。
- `pickToneLine`：前置短句直接取；后置按 `always = 1` / `half = 0.5` / `never = 0` 的概率决定给不给。
- `toneAfterForCommand`：`category === 'edge'` 的寸止指令**强制不加后置短句**，免得把「松手」冲淡。
- `varyBpm`：`bpmRandom.on` 且指令带 `bpm` 且不是红色时，用 `randomBpm(range, mode, random)` 换一个 BPM；红色与无 BPM 的指令原样返回。

## 指令池：`web/src/playback/commands.ts`

```ts
export interface EdgeCommand {
  text: string
  mode: EdgeMode
  category: 'basic' | 'edge' | 'tease' | 'pose' | 'pain' | 'nipple' | 'glans' | 'custom'
  bpm?: number         // 该条的手速节拍（可选）
  seconds?: number     // 该条的固定时长（可选，覆盖难度秒数）
  edge?: boolean       // 「冲到极限再停下」型寸止指令
  hint?: string        // 该条专属提示
}
```

- `maleCommands`：88 条（男生版主池，照官方中文文案），`basic` / `edge` / `tease` / `pose` / `pain` 混合。
- `nippleCommands`：5 条，全部 `stop` + `category: 'nipple'`。
- `glansCommands`：5 条，全部 `slow` + `category: 'glans'`。
- `filterByCategories` 里 `basic` 与 `custom` **恒定允许**，其余看 `categories` 开关。

## 口吻：`web/src/playback/tones.ts`

```ts
export interface ToneLine { before: string[]; after: string[] }
export type ToneLines = Record<EdgeMode, ToneLine>
export interface AbuseLines extends ToneLines { nipple: ToneLine }

export const strongLines / teaseLines / abuseLines: ToneLines / AbuseLines
export const sweetLines / feetLines: ToneLines
export const toneLines: Record<ToneKind, ToneLines | AbuseLines>
export const toneNotes: Record<ToneKind, string>   // 设置面板里的一句话说明
```

- 五种口吻：`strong` 强势、`tease` 挑逗、`abuse` 羞辱（多一组乳头专用短句）、`sweet` 温柔、`feet` 足控。
- 每种口吻按 `go` / `slow` / `stop` 各备一组前置、一组后置短句，文案照官方中文原文。
- 只做文字，**不做语音播报**；`abuse` 命中 `touching`（乳头指令，或 `stop` 下的挑逗／轻度疼痛）时优先用 `nipple` 那一组。

## 局内状态机：`web/src/playback/session.ts`

```ts
export interface SessionFrame {
  phase: SessionPhase
  round: number
  elapsed: number
  totalMs: number
  task: Task | null
  mode: EdgeMode
  text: string
  hint: string
  /** 口吻前置短句，`toneLine.before` 关掉或本轮没开时为空串 */
  toneBefore: string
  /** 口吻后置短句，同上 */
  toneAfter: string
  tone: ToneKind | 'normal'
  taskProgress: number
  taskSeconds: number
  cooling: boolean
  held: number
  permit: number
  windowLeft: number
  note: string
}

export type SessionPhase = 'run' | 'allow' | 'done'
export type SessionOutcome = 'allow' | 'deny' | 'ruin' | 'lost' | 'manual'
export interface SessionFrame {
  phase, round, elapsed, totalMs, task, mode, text, hint,
  taskProgress, taskSeconds, cooling, held, permit, windowLeft, note
}
export class EdgeSession {
  constructor(settings: EdgeSettings, options?: { nipple?: EdgeCommand[]; glans?: EdgeCommand[] })
  readonly settings
  readonly ruined: boolean
  readonly outcome: SessionOutcome | null
  get finished / permit / remainingMs / task / cooling
  frame(): SessionFrame
  tick(deltaMs: number): boolean   // 返回是否仍在进行
  hold(): boolean                  // 忍住了：次数 +1 并立刻切「等它平息」
  lose(): void                     // 射了：直接判负（outcome = 'lost'）
  stop(): void                     // 手动结束（allow 阶段记 'allow'，否则 'manual'）
}
export const cooldownText = '松手。等它平息。'
export const cooldownHint = '已记录忍住。下一条指令前不许碰。'
```

- `hold()` 之后进入冷却段（时长取 `restSeconds(rest)`），冷却期间 `frame().mode` 恒为 `stop`、
  文案换成 `cooldownText`、`taskProgress` 走冷却进度。
- 时间到 → `settle()`：`success` 与 `ruin` **都进 `allow` 阶段**（奖励屏），后者 `ruined = true`；
  否则 `finish('deny')`。
- `overtime` 结局：`settle()` 里先按 `extendChance(permitRate(...), extends)` 判定这一次能否直接给许可，
  中了就进许可窗口，没中则 `extend()`——`extends += 1`、`totalMs = elapsed + extendMs(extendLen, extends)`、
  立刻插一条 6 秒红色指令（文案取自 `extendLines`，`note = '加时第 N 次 · 时间增加了 m:ss'`），
  其余时段用新的随机种子重建时间线。**加时赛永远不会以 `deny` 收场**。
- 许可窗口走完 `closeWindow()`：一律 `finish('allow')`（`ruined` 则 outcome 记为 `'ruin'`）。
  **连续（多少次都行）结局不再重复开下一轮**——它把许可窗口固定成 100 秒
  （`multiWindowSeconds`），窗口里每 25 秒切到下一条「再来一次」文案（`multiRound` 1→4），
  窗口走完按成功收场。参考实现的口径：`rewardSeconds(multi) = 100`、
  `round = min(MULTI_ROUNDS - 1, floor(已用秒 / MULTI_ROUND_SECONDS))`。

## 音效：`web/src/playback/sound.ts`

`class SoundEngine`，全部用 WebAudio 振荡器实时合成，**不加载任何音频文件**：

- `beat(mode, options)`：峰值 `0.5 × beatVolume/100 × duck`；`go` 880 Hz、`slow` 520 Hz；
  5 ms 升、60 ms 指数降、`stop(now + 0.07)`。
- `cue(options)`：660 / 990 Hz 双音，峰值 `0.4 × beatVolume/100 × duck`，间隔 0.14 秒。
- `heartbeat(options)`：58 → 38 Hz 两次 thump（0.9 / 0.55），间隔 0.17 秒。
- 另有空 buffer keepAlive（22050 Hz）用于保持 AudioContext。
- 上限 `beatVolumeMax = 300`（v3 只有 100，是「声音过小」的根因之一）。

## 运行层接线（`web/src/PlaybackPanel.vue`）

- 两套存储分开：媒体层走 `playback.ts`（`shicun.playback.v1`，`schemaVersion = 4`），
  玩法层走 `settings.ts`（`shicun.edge.v1`）。
- `tick()` 固定 `100 ms` 一拍，只做三件事：`session.tick(delta)`、`frame = session.frame()`、同步 `held`；
  `session.phase === 'done'` 时 `finish(outcome)`。
- `hold()` → `session.hold()` + `sound.cue()`；「射了」→ `session.lose()`；
  `PlaybackStage` 的「射了」先弹二次确认（`记为中途结束的一局吗？` / `记录并结束` / `继续`）。
- `pulse(now)`：模式变化时重置节拍；`stop` 阶段按 `redBeat` 决定心跳 / 节拍 / 两者，固定 60 BPM。
- `frame.phase === 'allow'` 时渲染整屏奖励屏 `PlaybackReward`（ruin 橙 / 允许粉两套 radial-gradient、
  白色倒计时条、`剩余 N 秒`）。
- 音量弹层 `PlaybackVolumePopover` 四行：视频音量 / 节拍声（0–300）/ 指令文字不透明度（30–100）/
  指令文字大小（60–140）。
- `settings.keepVideoOnStop`：红色且未进许可窗口时暂停视频；遮罩浓度不变，视频本体透明度按 `1 - 0.2 * dim` 降低（对齐参考站）；
  `settings.switchVideoPerCommand`：`taskKey` 前进时切下一个媒体。
- `FinishReason = 'duration' | 'queue' | 'manual' | 'lost' | 'allow' | 'deny' | 'ruin'`，
  `PlaybackFinished` 按 outcome 出 Finised / Ruined / Denied / Lost 四套文案与三格统计（时间 / 指令 / 忍住）。

## 设置页五组（`web/src/PlaybackSettings.vue`）

分组：**玩法 / 指令 / 视频·图片 / 声音 / 其他**（`runtime` 模式下隐藏「视频·图片」）。

| 组 | 字段 |
| --- | --- |
| 玩法 | 推荐预设 `presets`、只玩乳头 / 龟头 `nipple` `glans`、道具模式 `toy` `aneros`、时长 `minutes` + `durationRandom`、难度 `difficulty`、自己调 `tune`（许可概率 / 三相位 mix）、结局 `finale` + `allowRuin`、`rewardSeconds`、`rest`、`instructionLength`、图例与规则句 |
| 指令 | 分类 `categories`、惯用手 `hand`、口吻 `tones` + `toneLine(show/before/after)`、自定义口令 `custom`（≤30 条 / 60 字）、逐条启停 `disabled`（按 `modeOrder` 分组列 `maleCommands`） |
| 视频·图片 | 直接绑 `Playlist`：`kind / order / imageCount / imageTiming / imageSeconds / bpm(20–300) / loop / favoritesOnly` + `keepVideoOnStop` + `switchVideoPerCommand` + `keepVideoWhileCooling` + `videoSound` + `skipIntro` + `fit` / `pos` + `textOpacity` / `textScale` |
| 声音 | `metronome` + `beatVolume(0–300)`、`mediaVolume(0–100)`、`heartbeat` + `heartbeatVolume(0–300)` + `redBeat` + `heartbeatSync`、`bpmRandom(on/min/max)`、`vibrate` + `vibrateOn(command/edge/finish)` |
| 其他 | `hideRemaining`、`dim(0–100)`、`mixAudio`、`mirror(on/place)` + 前置摄像头同意卡、连续天数（`shicun.edge.days.v1`）、本机成绩行（`shicun.edge.stats.v1`）、历史成绩入口（`shicun.edge.history.v1` + `shicun.edge.tally.v1`） |

### 单部位模式（`web/src/playback/focus.ts`）

`focus` 非 `none` 时，整局只出该部位的专属指令，并且**不再插入**中途的「只玩乳头 / 只玩龟头」时间（那两个开关同时变灰）。

| 导出 | 说明 |
| --- | --- |
| `focusAreas` | `['none', 'nipple', 'glans']` |
| `focusLabels` | `none`=不限制 / `nipple`=只玩乳头 / `glans`=只玩龟头 |
| `focusNotes` | 选中后显示在设置项下方的说明（乳头：从头到尾只出乳头指令，最后允许前下面一下都不许碰；龟头：从头到尾只出龟头指令，不许握柱身） |
| `focusSectionsOff` | `单部位模式下不会使用`（两个专属段开关上的灰字） |
| `focusAllowBelow` | `现在可以摸下面了。`（只玩乳头拿到许可时，奖励屏下方多这一句） |

指令池在 `web/src/playback/commands.ts`：`focusNippleCommands`（18 条，`mode` 覆盖 go / slow / stop，其中 2 条 `category: 'edge'` 保留寸止语义）、`focusGlansCommands`（16 条，同结构）。`EdgeSession` 构造时按 `settings.focus` 直接把 `this.pool` 换成对应池（不经过分类过滤与道具合并），`allowBelow` getter 只在 `phase === 'allow'` 且 `focus === 'nipple'` 且非 `ruined` 时给文案。

### 镜子（`web/src/playback/mirror.ts`）

沿用参考站语义：`mirror.on` 且**只在播放中**打开前置摄像头，画面 `scaleX(-1)` 左右翻转。
`place = 'bg'` 铺满背景并叠一层模式色暗化（alpha `0.45 × dim/100`）；`place = 'corner'` 是右下角 80px（≥640px 为 128px）圆角小窗。
`mirrorPlaceFor(place, playingVideo)` 在播放视频时强制 `'corner'`。

```ts
export const mirrorPlaces = ['bg', 'corner'] as const
export const MIRROR_CONSTRAINTS: MediaStreamConstraints   // { video: { facingMode: 'user' }, audio: false }
export const mirrorPlaceLabels / mirrorErrorLabels / mirrorText
export function mirrorSupport(): MirrorError | null        // 非安全上下文或缺 mediaDevices → 'unsupported'
export function classifyMirrorError(error: unknown): MirrorError   // denied / none / unsupported / busy
export function stopStream(stream: MediaStream | null): void
export function mirrorPlaceFor(place: MirrorPlace, playingVideo: boolean): MirrorPlace
```

设置页点开关先弹同意卡（`mirrorText.consentTitle / consentBody`），点「允许使用摄像头」才真正 `getUserMedia`；
失败按 `classifyMirrorError` 出中文提示并保持关闭。播放结束、返回列表、重开一局、组件卸载都会 `stopStream`。


摘要行 `web/src/playback/summary.ts` 的 `settingsSummary(settings)` 输出形如
`10 分钟 · 普通 · 抽签 · 指令 88 种 · 许可率 70% · 不许碰 5–10 秒 · 节拍声开`，
另有 `enabledCommandCount(settings)` 供别处复用。

## 验收

```bash
cd web
npx nuxt typecheck                                  # 必须 exit 0
for f in checks/*.ts; do node --experimental-strip-types "$f"; done
npm run build                                       # nuxt typecheck && nuxt generate
```

`web/checks/engine.ts` 覆盖：难度表、`mulberry32` 首值、`shareOf/timeShareOf/mixOf/adjustMix`、
`taskSeconds`（stop 不吃长档）、`permitRate` 封顶、`decideFinale` 六路 + `allowRuin`、
`restSeconds/randomBpm/planFocus/pickIndex`、`pickMode`（首段必 go、不连出 stop、mix>45% 放开）、
`pickCommandAt` 不重复上条、`swapHands`、指令池 88 条与字段范围、`buildTimeline`（首段 go、
`at` 递增、末段铺到结尾且 ≥5 秒、同种子复现）、`bindCommands` 顺移、`taskAt`、`formatClock`、
`defaultEdgeSettings`、`normalizeEdgeSettings` 全字段夹取、`writeEdgeSettings/readEdgeSettings`、
`EdgeSession`（开局 go、hold 进冷却、permit 递增、lose / never / always / ruin 四路收场）。

`web/checks/playback.ts` 覆盖 v4 媒体层：`playbackSchemaVersion === 4`、`newPlaylist()` 默认值、
**25 个旧玩法字段不得出现在 `Playlist` 上**、`validPlaylist` 逐字段边界、v3 存档升级到 4、
`mediaUrl/mediaKey/clockTime/nextBeatTime/orderedMedia/playbackCycle`、
`exportConfiguration/importConfiguration`。

## 已知不做

- 联机 / 远程操控 / 双人链接 / 角色音（`sundome_remote`、`/api/rgate/*`、`/rws/lobby` 一律不接）。
- 语音播报（`speechSynthesis`、`voiceLines.ts` 已删除）。
- 道具模式的 AV 棒（女性版）、分享到 X。
