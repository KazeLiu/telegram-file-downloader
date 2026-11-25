// 寸止引擎：语义与数值对齐参考实现（go / slow / stop 三相位 + 难度份额 + 预生成任务）。
// 纯函数、可播种随机，便于校验与复现。
import { anerosCommands, maleCommands, toyCommands, type EdgeCommand, type EdgeMode } from './commands.ts'

export type { EdgeCommand, EdgeMode }

export type Difficulty = 'easy' | 'normal' | 'hard' | 'hell'
export type Finale = 'draw' | 'always' | 'never' | 'ruin' | 'continuous' | 'overtime'
export type InstructionLength = 'standard' | 'long' | 'veryLong'
export type ExtendLength = 'short' | 'normal' | 'shrink'
export type RestMode = 'random' | 'fixed'
export type ToneKind = 'strong' | 'tease' | 'abuse' | 'sweet' | 'feet'
export type ToneAfter = 'never' | 'half' | 'always'
export type RedBeat = 'heartbeat' | 'both' | 'metronome'
export type Hand = 'right' | 'left'

export interface DifficultyProfile {
  chance: number
  share: Record<EdgeMode, number>
  seconds: Record<EdgeMode, [number, number]>
  stopAfterStop: boolean
}

export const difficulties: Record<Difficulty, DifficultyProfile> = {
  easy: { chance: 0.85, share: { go: 0.56, slow: 0.2, stop: 0.24 }, seconds: { go: [15, 30], slow: [8, 16], stop: [4, 8] }, stopAfterStop: false },
  normal: { chance: 0.7, share: { go: 0.38, slow: 0.2, stop: 0.42 }, seconds: { go: [12, 25], slow: [8, 16], stop: [5, 10] }, stopAfterStop: false },
  hard: { chance: 0.5, share: { go: 0.39, slow: 0.25, stop: 0.36 }, seconds: { go: [8, 18], slow: [6, 14], stop: [6, 14] }, stopAfterStop: true },
  hell: { chance: 0.3, share: { go: 0.35, slow: 0.22, stop: 0.43 }, seconds: { go: [6, 14], slow: [6, 12], stop: [8, 18] }, stopAfterStop: true }
}

export const difficultyOrder: Difficulty[] = ['easy', 'normal', 'hard', 'hell']

export const difficultyLabels: Record<Difficulty, string> = {
  easy: '简单',
  normal: '普通',
  hard: '困难',
  hell: '地狱'
}

export const difficultyHints: Record<Difficulty, string> = {
  easy: '七成时间可以动手。「不许碰」又短又少。最后获得许可的概率 85%',
  normal: '动手六成·慢两成·不许碰两成。最后获得许可的概率 70%',
  hard: '指令切换快，「不许碰」占三成。最后获得许可的概率 50%',
  hell: '能碰的时间只有三成。最后获得许可的概率 30%。只能靠多忍住几次来提高'
}

export const modeOrder: EdgeMode[] = ['go', 'slow', 'stop']

export const modeLabels: Record<EdgeMode, string> = {
  go: '可以撸',
  slow: '慢慢来',
  stop: '不许碰'
}

export const modeColors: Record<EdgeMode, string> = {
  go: '#5ee3a1',
  slow: '#f0c35a',
  stop: '#ff6b7d'
}

export const modeColorsBright: Record<EdgeMode, string> = {
  go: '#86e3bb',
  slow: '#f7d78a',
  stop: '#ff9aa6'
}

/** 镜子的「铺满背景」要叠一层模式色的暗色变体（参考站的 ao 表），不是亮色。 */
export const modeColorsDark: Record<EdgeMode, string> = {
  go: '#0c3f2c',
  slow: '#4d3400',
  stop: '#5c0d16'
}

export const finaleOrder: Finale[] = ['draw', 'always', 'never', 'ruin', 'continuous', 'overtime']

export const finaleLabels: Record<Finale, string> = {
  draw: '抽签',
  always: '必定允许',
  never: '必定禁止',
  ruin: '松手射精',
  continuous: '连续（多少次都行）',
  overtime: '加时赛'
}

export const finaleHints: Record<Finale, string> = {
  draw: '按难度对应的概率，决定「允许」还是「禁止」。每忍住一次概率 +5%（最多 +20%）',
  always: '时间到就允许。不用抽签',
  never: '时间到也禁止。一次都不能射',
  ruin: '可以射，但射出的瞬间松手，不碰任其流出',
  continuous: '射完不结束。接着来下一轮，想停就停',
  overtime: '没抽中也不会以禁止结束，而是加时，直到获得许可（每加时一次概率 +15%，加时 5 次后必定许可）'
}

export const rewardChoices = [5, 10, 20, 30, 45, 60]
export const durationChoices = [3, 5, 10, 15, 20, 30]
export const durationMin = 1
export const durationMax = 180
export const restMin = 3
export const restMax = 120
export const restRangeChoices: Array<[number, number]> = [[8, 16], [10, 40], [20, 60]]
export const restFixedChoices = [5, 10, 12, 20, 30, 60]
export const bpmRandomMin = 20
export const bpmRandomMax = 300
export const beatVolumeMax = 300
export const videoVolumeMax = 100
export const brightnessMin = 20
/** 指令文字的不透明度与字号下限（与参考站一致：文字最低 30%、字号最低 60%）。 */
export const textOpacityMin = 30
export const textScaleMin = 60
export const customCommandLimit = 30
export const customCommandTextLimit = 60
export const finalHoldMs = 5000
export const permitStep = 0.05
export const permitMaxGain = 0.2
export const multiRounds = 4
export const multiRoundSeconds = 25
export const instructionLengthOrder: InstructionLength[] = ['standard', 'long', 'veryLong']
export const instructionLengthLabels: Record<InstructionLength, string> = {
  standard: '标准',
  long: '较长（约 1～2 分钟）',
  veryLong: '很长（约 2～5 分钟）'
}
export const extendLengthOrder: ExtendLength[] = ['short', 'normal', 'shrink']
export const extendLengthLabels: Record<ExtendLength, string> = {
  short: '短（1～3 分钟）',
  normal: '普通（2～5 分钟）',
  shrink: '越来越短（5～10 分钟→1 分钟）'
}
/** 加时抽出的那条指令固定 6 秒。 */
export const extendLineSeconds = 6
/** 加时文案：时间到没抽中时轮流播报，超时（按到时间）用 timeout。 */
export const extendLines = ['想高潮？还不行。再忍一会儿。', '求也没用，还不给。继续。', '没有许可。加时。', '不行。再忍一下。']
export const extendTimeoutText = '时间到了。继续忍着。'
export const extendAddedText = '时间增加了'

/** 加时赛每次加时的许可率：基础值 + 每次加时 +15%，第 5 次必中。 */
export function extendChance(chance: number, times: number) {
  if (times >= 5) return 1
  return Math.min(1, chance + 0.15 * times)
}

/** 加时时长（毫秒）：短固定 1～3 分钟，普通固定 2～5 分钟，越来越短则按第几次递减。 */
export function extendMs(length: ExtendLength, times: number, random: Random) {
  const [low, high] = length === 'short'
    ? [1, 3]
    : length === 'normal'
      ? [2, 5]
      : times <= 1
        ? [5, 10]
        : times === 2
          ? [3, 5]
          : times === 3
            ? [2, 3]
            : [1, 1]
  return Math.round((low + (high - low) * random()) * 60_000)
}

export const restModeOrder: RestMode[] = ['random', 'fixed']
export const restModeLabels: Record<RestMode, string> = { random: '随机', fixed: '固定' }
export const toneOrder: ToneKind[] = ['strong', 'tease', 'abuse', 'sweet', 'feet']
export const toneLabels: Record<ToneKind, string> = {
  strong: '强势',
  tease: '挑逗',
  abuse: '羞辱',
  sweet: '温柔',
  feet: '足控'
}
export const toneAfterOrder: ToneAfter[] = ['never', 'half', 'always']
export const toneAfterLabels: Record<ToneAfter, string> = { never: '不加', half: '一半', always: '每条都加' }
export const redBeatOrder: RedBeat[] = ['heartbeat', 'both', 'metronome']
export const redBeatLabels: Record<RedBeat, string> = {
  heartbeat: '只有心跳',
  both: '心跳和节拍都有',
  metronome: '只有节拍'
}
export const categoryOrder = ['edge', 'tease', 'pose', 'pain'] as const
export type CategoryKind = (typeof categoryOrder)[number]
export type Categories = Record<CategoryKind, boolean>
export const categoryLabels: Record<CategoryKind, string> = {
  edge: '寸止指令',
  tease: '挑逗',
  pose: '姿势·羞耻',
  pain: '轻度疼痛'
}
export const categoryHints: Record<CategoryKind, string> = {
  edge: '「冲到极限再停下」的指令。申报的次数会提高最后的许可率',
  tease: '只玩乳头、只摸蛋蛋、只轻轻抚摸等',
  pose: '跪坐、四肢着地、羞耻的姿势等',
  pain: '轻拍大腿、蛋蛋（不喜欢就关掉）'
}

export const presets = {
  first: { minutes: 5, difficulty: 'easy' as Difficulty, finale: 'always' as Finale, categories: { edge: false, tease: true, pose: false, pain: false } },
  standard: { minutes: 10, difficulty: 'normal' as Difficulty, finale: 'draw' as Finale, categories: { edge: true, tease: true, pose: true, pain: false } },
  long: { minutes: 20, difficulty: 'hard' as Difficulty, finale: 'draw' as Finale, categories: { edge: true, tease: true, pose: true, pain: false } }
}
export type PresetKey = keyof typeof presets
export const presetOrder: PresetKey[] = ['first', 'standard', 'long']
export const presetLabels: Record<PresetKey, string> = { first: '第一次', standard: '标准', long: '慢慢来·长时间' }

export interface Mix {
  go: number
  slow: number
  stop: number
}

export interface Tune {
  /** 许可概率（百分比）；null 表示跟随难度 */
  chance: number | null
  /** 不许碰占比（百分比）；null 表示跟随难度 */
  stop: number | null
  /** 手动三相位占比；null 表示跟随难度 */
  mix: Mix | null
}

export type Random = () => number

export function mulberry32(seed: number): Random {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let value = state
    value = Math.imul(value ^ (value >>> 15), value | 1)
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61)
    return ((value ^ (value >>> 14)) >>> 0) / 0x100000000
  }
}

export function randomSeed() {
  try {
    const value = globalThis.crypto?.getRandomValues?.(new Uint32Array(1))
    if (value) return value[0]! >>> 0
  } catch {
    // 忽略：退回到 Math.random
  }
  return Math.floor(0x100000000 * Math.random()) >>> 0
}

/** 难度区间平均秒数之和（用于把占比换算成时间占比）。 */
function spanOf(difficulty: Difficulty, mode: EdgeMode) {
  const [min, max] = difficulties[difficulty].seconds[mode]
  return min + max
}

/** 相位占比：mix 优先，其次手调 stop，最后用难度份额。 */
export function shareOf(difficulty: Difficulty, tune: Tune | null): Record<EdgeMode, number> {
  const base = difficulties[difficulty].share
  if (tune?.mix) {
    const raw = {
      go: tune.mix.go / spanOf(difficulty, 'go'),
      slow: tune.mix.slow / spanOf(difficulty, 'slow'),
      stop: tune.mix.stop / spanOf(difficulty, 'stop')
    }
    const total = raw.go + raw.slow + raw.stop
    if (total > 0) return { go: raw.go / total, slow: raw.slow / total, stop: raw.stop / total }
    return { ...base }
  }
  if (!tune || tune.stop === null) return { ...base }
  const stop = tune.stop / 100
  const rest = base.go + base.slow
  return { go: (1 - stop) * base.go / rest, slow: (1 - stop) * base.slow / rest, stop }
}

/** 时间加权占比（界面展示用）。 */
export function timeShareOf(difficulty: Difficulty, tune: Tune | null): Record<EdgeMode, number> {
  if (tune?.mix) return { go: tune.mix.go / 100, slow: tune.mix.slow / 100, stop: tune.mix.stop / 100 }
  const share = shareOf(difficulty, tune)
  const weighted = {
    go: share.go * spanOf(difficulty, 'go'),
    slow: share.slow * spanOf(difficulty, 'slow'),
    stop: share.stop * spanOf(difficulty, 'stop')
  }
  const total = weighted.go + weighted.slow + weighted.stop
  return { go: weighted.go / total, slow: weighted.slow / total, stop: weighted.stop / total }
}

/** 百分比形式的占比（拿捏面板的三条滑杆）。 */
export function mixOf(difficulty: Difficulty, tune: Tune | null): Mix {
  if (tune?.mix) return { ...tune.mix }
  const share = timeShareOf(difficulty, tune)
  const stop = Math.min(60, 5 * Math.round(20 * share.stop))
  const slow = Math.min(100 - stop, 5 * Math.round(20 * share.slow))
  return { go: 100 - stop - slow, slow, stop }
}

/** 按 5% 步进调整某一相位，差额从其它两相位扣。 */
export function adjustMix(mix: Mix, mode: EdgeMode, value: number): Mix {
  const next = Math.max(0, Math.min(mode === 'stop' ? 60 : 100, 5 * Math.round(value / 5)))
  const others: EdgeMode[] = mode === 'go' ? ['slow', 'stop'] : mode === 'slow' ? ['go', 'stop'] : ['go', 'slow']
  const result: Mix = { ...mix, [mode]: next }
  const delta = next - mix[mode]
  if (delta > 0) {
    const first = others[0]!
    const second = others[1]!
    const take = Math.min(mix[first], delta)
    result[first] = mix[first] - take
    result[second] = mix[second] - (delta - take)
  } else if (delta < 0) {
    const first = others[0]!
    result[first] = mix[first] - delta
  }
  return result
}

/** 单条任务时长（秒）：stop 相位不听指令时长档位。 */
export function taskSeconds(difficulty: Difficulty, mode: EdgeMode, random: Random, length: InstructionLength = 'standard') {
  if (mode !== 'stop' && length === 'long') return 60 + Math.floor(61 * random())
  if (mode !== 'stop' && length === 'veryLong') return 120 + Math.floor(181 * random())
  const [min, max] = difficulties[difficulty].seconds[mode]
  return min + Math.floor(random() * (max - min + 1))
}

/** 最终许可概率：基础（或手调）+ 每次忍住 5%，累计最多 +20%，总封顶 100%。 */
export function permitRate(difficulty: Difficulty, held: number, chance: number | null = null) {
  const base = chance === null ? difficulties[difficulty].chance : chance / 100
  return Math.min(1, base + Math.min(permitMaxGain, permitStep * held))
}

export type FinaleVerdict = 'success' | 'fail' | 'ruin'

export function decideFinale(finale: Finale, difficulty: Difficulty, held: number, random: Random, chance: number | null = null, allowRuin = false): FinaleVerdict {
  if (finale === 'always' || finale === 'continuous') return 'success'
  if (finale === 'never') return 'fail'
  if (finale === 'ruin') return 'ruin'
  if (finale === 'overtime') return random() < permitRate(difficulty, held, chance) ? (allowRuin ? 'ruin' : 'success') : 'fail'
  return random() < permitRate(difficulty, held, chance) ? 'success' : 'fail'
}

/** 休息时长：固定档位或区间随机。 */
export function restSeconds(rest: { mode: RestMode; seconds: number; min: number; max: number }, random: Random) {
  if (rest.mode === 'fixed') return rest.seconds
  const min = Math.min(rest.min, rest.max)
  const max = Math.max(rest.min, rest.max)
  return min + Math.floor(random() * (max - min + 1))
}

/** 随机 BPM：慢慢来取区间下半段，可以撸取上半段，5 的整数倍。 */
export function randomBpm(range: { min: number; max: number }, mode: EdgeMode, random: Random) {
  const min = Math.min(range.min, range.max)
  const max = Math.max(range.min, range.max)
  const mid = (min + max) / 2
  const [low, high] = mode === 'slow' ? [min, mid] : [mid, max]
  return Math.min(max, Math.max(min, 5 * Math.round((low + random() * (high - low)) / 5)))
}

/** 乳头 / 龟头专属指令在整局中的触发时间点（毫秒，升序）。 */
export function planFocus(times: number, totalMs: number, random: Random, kind: 'nipple' | 'glans') {
  const ratios = kind === 'nipple'
    ? (times === 4 ? [0.18, 0.38, 0.6, 0.8] : times === 3 ? [0.25, 0.5, 0.75] : times === 2 ? [0.3, 0.65] : [0.45])
    : (times === 4 ? [0.2, 0.4, 0.62, 0.82] : times === 3 ? [0.28, 0.56, 0.8] : times === 2 ? [0.4, 0.78] : [0.62])
  const jitter = kind === 'nipple' ? 0.16 : 0.12
  return ratios.map(ratio => Math.round(totalMs * (ratio + (random() - 0.5) * jitter))).sort((a, b) => a - b)
}

export function pickIndex<T>(items: T[], random: Random): T | null {
  if (!items.length) return null
  const index = Math.min(items.length - 1, Math.max(0, Math.floor(random() * items.length)))
  return items[index] ?? null
}

export interface PickOptions {
  /** 上一段相位；null 表示这是第一段 */
  previous: EdgeMode | null
  isFirst: boolean
  difficulty: Difficulty
  tune: Tune | null
  /** 允许出现的相位（首段只出 go 时由调用方传 ['go']） */
  modes: EdgeMode[]
  random: Random
}

/** 选下一段相位：首段强制 go，默认禁止 stop 连出。 */
export function pickMode(options: PickOptions): EdgeMode | null {
  const share = shareOf(options.difficulty, options.tune)
  let stopAfterStop = difficulties[options.difficulty].stopAfterStop
  let weights = share
  if (options.tune?.mix && !stopAfterStop) {
    if (share.stop > 0.45) stopAfterStop = true
    else {
      const ratio = share.stop / (1 - share.stop)
      const rest = share.go + share.slow
      if (rest > 0) weights = { go: (1 - ratio) * share.go / rest, slow: (1 - ratio) * share.slow / rest, stop: ratio }
    }
  }
  const forceGo = options.isFirst && options.modes.includes('go')
  const allowed = options.modes.filter(mode => !(mode === 'stop' && options.previous === 'stop' && !stopAfterStop) && (!forceGo || mode === 'go'))
  if (!allowed.length) return null
  const total = allowed.reduce((sum, mode) => sum + weights[mode], 0)
  let cursor = options.random() * total
  for (const mode of allowed) {
    cursor -= weights[mode]
    if (cursor < 0) return mode
  }
  return allowed[allowed.length - 1] ?? null
}

/** 按相位挑口令：排除上一条同文本。 */
export function pickCommandAt(mode: EdgeMode, random: Random, previous: EdgeCommand | null, pool: EdgeCommand[]): EdgeCommand | null {
  const sameMode = pool.filter(item => item.mode === mode)
  const different = sameMode.filter(item => item.text !== previous?.text)
  const candidates = different.length ? different : sameMode.length ? sameMode : pool.filter(item => item.text !== previous?.text)
  return pickIndex(candidates.length ? candidates : pool, random)
}

/** 把惯用手换成另一只手。必须一次扫完，否则「左手→右手→左手」会换回原样。 */
const handPairs: Array<[string, string]> = [
  ['左手', '右手'], ['右手', '左手'], ['左', '右'], ['右', '左']
]

export function swapHands(text: string) {
  let result = ''
  let index = 0
  while (index < text.length) {
    const pair = handPairs.find(([from]) => text.startsWith(from, index))
    if (pair) {
      result += pair[1]
      index += pair[0].length
      continue
    }
    result += text[index]
    index += 1
  }
  return result
}

export interface CustomCommand {
  text: string
  mode: EdgeMode
  bpm?: number
}

/** 道具模式的开关：飞机杯会把「只能用手」「必须握柱身」的指令剔除，Aneros 追加红色段的夹紧指令。 */
export interface PoolTools {
  /** 使用飞机杯 */
  toy?: boolean
  /** 使用前列腺按摩器 */
  aneros?: boolean
  /** 飞机杯指令池（下标从 1000 起） */
  toyBase?: EdgeCommand[]
  /** 前列腺按摩器指令池（下标从 2000 起） */
  anerosBase?: EdgeCommand[]
}

export function commandPool(
  disabled: number[], custom: CustomCommand[], hand: Hand,
  base: EdgeCommand[] = maleCommands, tools: PoolTools = {},
) {
  const blocked = new Set(disabled)
  const dress = (item: EdgeCommand) => (hand === 'left' ? { ...item, text: swapHands(item.text) } : { ...item })
  const indexed = (list: EdgeCommand[], offset: number) =>
    list.map((item, index) => ({ index: offset + index, item })).filter(entry => !blocked.has(entry.index))
  let entries = indexed(base, 0)
  if (tools.aneros) entries = [...entries, ...indexed(tools.anerosBase ?? anerosCommands, 2000)]
  if (tools.toy) {
    // 参考实现：开飞机杯时把「只能用手直接做」与「必须握柱身」的指令整条剔除，再接上飞机杯专属指令。
    entries = [
      ...entries.filter(entry => !entry.item.bareHand && !entry.item.shaft),
      ...indexed(tools.toyBase ?? toyCommands, 1000),
    ]
  }
  const extra: EdgeCommand[] = custom
    .map(item => ({ text: item.text.trim(), mode: item.mode, category: 'custom' as const, ...(item.bpm ? { bpm: item.bpm } : {}) }))
    .filter(item => item.text.length > 0)
  return [...entries.map(entry => dress(entry.item)), ...extra]
}

/** 指令自带秒数超过 30×分钟数时整条剔除（对齐参考实现），免得极长指令吃掉整局；全被剔除时原样返回。 */
export function dropOverlongCommands(pool: EdgeCommand[], minutes: number) {
  const limit = 30 * Math.max(1, minutes)
  const kept = pool.filter(item => !item.seconds || item.seconds <= limit)
  return kept.length ? kept : pool
}

/** 按分类过滤口令（只有 basic 与 custom 恒定允许）。 */
export function filterByCategories(pool: EdgeCommand[], categories: Categories) {
  return pool.filter(item => item.category === 'basic' || item.category === 'custom' || categories[item.category as CategoryKind])
}

export interface Task {
  index: number
  at: number
  seconds: number
  mode: EdgeMode
  /** 绑定到这条任务的指令 */
  command: EdgeCommand | null
  /** 该段是否以「忍住了」结束（edge 指令 / 自己按下） */
  edge: boolean
  /** 乳头 / 龟头专属段 */
  focus: 'nipple' | 'glans' | null
}

export interface TimelineOptions {
  seed: number
  totalMs: number
  difficulty: Difficulty
  tune: Tune | null
  length: InstructionLength
  modes?: EdgeMode[]
  nipple?: { times: number }
  glans?: { times: number }
}

/**
 * 预生成整局时间线（与参考实现一致）：相位、时长全部先算好，便于进度条与「换一项」。
 * 末尾不足 finalHoldMs 的尾巴并进最后一段，避免出现闪一下的残段。
 */
export function buildTimeline(options: TimelineOptions): Task[] {
  const random = mulberry32(options.seed)
  const modes = options.modes?.length ? options.modes : modeOrder
  const total = options.totalMs
  const nipplePlans = options.nipple ? planFocus(options.nipple.times, total, random, 'nipple') : []
  const glansPlans = options.glans ? planFocus(options.glans.times, total, random, 'glans') : []
  const tasks: Task[] = []
  let cursor = 0
  let previous: EdgeMode | null = null
  let previousFocus: 'nipple' | 'glans' | null = null
  while (cursor < total) {
    let mode: EdgeMode
    let seconds: number
    let focus: 'nipple' | 'glans' | null = null
    // 专属段按计划时间插入；两段之间至少隔一条普通指令，避免连着两次。
    const canFocus = previousFocus === null
    if (canFocus && nipplePlans.length && cursor >= nipplePlans[0]!) {
      nipplePlans.shift()
      mode = 'stop'
      focus = 'nipple'
      seconds = 20 + Math.floor(11 * random())
    } else if (canFocus && glansPlans.length && cursor >= glansPlans[0]!) {
      glansPlans.shift()
      mode = 'slow'
      focus = 'glans'
      seconds = 20 + Math.floor(11 * random())
    } else {
      mode = pickMode({ previous, isFirst: tasks.length === 0, difficulty: options.difficulty, tune: options.tune, modes, random }) ?? modes[0]!
      seconds = taskSeconds(options.difficulty, mode, random, options.length)
    }
    let span = seconds * 1000
    if (total - (cursor + span) < finalHoldMs) span = total - cursor
    tasks.push({ index: tasks.length, at: cursor, seconds: span / 1000, mode, command: null, edge: false, focus })
    cursor += span
    previous = mode
    previousFocus = focus
  }
  return tasks
}

/** 给时间线逐条绑定指令；指令自带 seconds 时改写该段时长并顺移后续时间点。 */
export function bindCommands(tasks: Task[], pool: EdgeCommand[], nipplePool: EdgeCommand[] = [], glansPool: EdgeCommand[] = []) {
  let previous: EdgeCommand | null = null
  for (const task of tasks) {
    const random = mulberry32((task.index + 1) * 0x9e3779b1)
    const picked: EdgeCommand | null = task.focus === 'nipple' && nipplePool.length
      ? pickCommandAt('stop', random, previous, nipplePool)
      : task.focus === 'glans' && glansPool.length
        ? pickCommandAt('slow', random, previous, glansPool)
        : pickCommandAt(task.mode, random, previous, pool)
    if (picked && typeof picked.seconds === 'number' && picked.seconds !== task.seconds) {
      const delta = (picked.seconds - task.seconds) * 1000
      task.seconds = picked.seconds
      for (const later of tasks) if (later.index > task.index) later.at += delta
    }
    task.command = picked
    task.edge = !!picked?.edge
    previous = picked
  }
  return tasks
}

/** 二分查找当前时间点所在的任务。 */
export function taskAt(tasks: Task[], at: number): Task | null {
  if (!tasks.length || at < 0) return tasks[0] ?? null
  let low = 0
  let high = tasks.length - 1
  while (low < high) {
    const mid = (low + high + 1) >> 1
    if (tasks[mid]!.at <= at) low = mid
    else high = mid - 1
  }
  const task = tasks[low]!
  return at < task.at + 1000 * task.seconds ? task : null
}

export function formatClock(milliseconds: number) {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000))
  return `${Math.floor(seconds / 60)}:${(seconds % 60).toString().padStart(2, '0')}`
}

/** 挑一条口令里的一句话：用预生成的随机数做索引，结果可复现。 */
function pickLine(lines: string[], random: Random) {
  return lines.length ? lines[Math.min(lines.length - 1, Math.floor(random() * lines.length))] : undefined
}

/** 当前该用哪种口吻：按「第几条指令」轮流用开启的几种。 */
export function toneForTask(tones: Record<ToneKind, boolean>, count: number): ToneKind | 'normal' {
  const active = toneOrder.filter(kind => tones[kind])
  if (!active.length) return 'normal'
  return active[(((count - 1) % active.length) + active.length) % active.length]!
}

/** 挑出口吻短句；`before` 与 `after` 各自独立随机。 */
export function pickToneLine(
  lines: { before?: string[]; after?: string[] },
  random: Random,
  options: { before: boolean; after: ToneAfter }
) {
  const before = options.before ? pickLine(lines.before ?? [], random) : undefined
  const afterChance = options.after === 'always' ? 1 : options.after === 'half' ? 0.5 : 0
  const after = afterChance > 0 && random() < afterChance ? pickLine(lines.after ?? [], random) : undefined
  return { ...(before ? { before } : {}), ...(after ? { after } : {}) }
}

/** 寸止类指令不加后置短句，避免把「松手」冲淡。 */
export function toneAfterForCommand(command: { category: string } | null, after: ToneAfter): ToneAfter {
  return command?.category === 'edge' ? 'never' : after
}

/** 每次变换节奏：开启后每条绿黄指令的 BPM 在范围内重新随机（红色固定 60，不参与）。 */
export function varyBpm(
  command: EdgeCommand | null,
  range: { on: boolean; min: number; max: number } | null,
  random: Random,
) {
  if (!command || !range || !range.on || !command.bpm || command.mode === 'stop') return command
  return { ...command, bpm: randomBpm(range, command.mode, random) }
}
