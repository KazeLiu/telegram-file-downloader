// 寸止（edge play）控制器的纯逻辑层：只放常量与纯函数，不依赖 Vue、不碰 localStorage。
// 随机一律由调用方注入 random，缺省 Math.random，便于断言与复现。
import { phaseOrder, type PhaseKind } from './types.ts'

export type Difficulty = 'easy' | 'normal' | 'hard' | 'hell'
export type Ending = 'draw' | 'always' | 'never' | 'ruin' | 'continuous' | 'overtime'
export type Tone = 'firm' | 'tease' | 'degrade' | 'gentle'
export type CommandType = 'fast' | 'slow' | 'rest' | 'tease' | 'nipple' | 'glans'

export interface Command {
  id: string
  type: CommandType
  text: string
}

/** 难度就是绿／黄／红三段时间占比加最后的许可率，不是抽象等级。 */
export const difficultyProfiles: Record<Difficulty, { label: string; fast: number; slow: number; rest: number; permit: number }> = {
  easy: { label: '简单', fast: 50, slow: 30, rest: 20, permit: 85 },
  normal: { label: '普通', fast: 60, slow: 20, rest: 20, permit: 70 },
  hard: { label: '困难', fast: 55, slow: 20, rest: 25, permit: 55 },
  hell: { label: '地狱', fast: 45, slow: 20, rest: 35, permit: 40 },
}

export const difficultyOrder: Difficulty[] = ['easy', 'normal', 'hard', 'hell']

export const endingOrder: Ending[] = ['draw', 'always', 'never', 'ruin', 'continuous', 'overtime']

export const endingLabels: Record<Ending, string> = {
  draw: '抽签',
  always: '必定允许',
  never: '必定禁止',
  ruin: '松手射精',
  continuous: '连续',
  overtime: '加时赛',
}

export const endingHints: Record<Ending, string> = {
  draw: '按当前许可率抽签，忍住得越多越容易通过',
  always: '时间一到就直接给许可',
  never: '时间到也不给，只能忍到底',
  ruin: '给许可时掷一次，一半概率改为松手结束',
  continuous: '忍过一次就继续，可以一直玩下去',
  overtime: '抽签失败后加时，每次多 15%，第五次必定允许',
}

export const toneLabels: Record<Tone, string> = {
  firm: '强硬',
  tease: '挑逗',
  degrade: '辱骂',
  gentle: '温柔',
}

export const commandTypeLabels: Record<CommandType, string> = {
  fast: '撸',
  slow: '慢',
  rest: '不许碰',
  tease: '挑逗',
  nipple: '只玩乳头',
  glans: '只玩龟头',
}

export const propLabels: Record<string, string> = {
  cup: '飞机杯',
  aneros: '前列腺按摩器',
}

export const voicePitchLabels: Record<string, string> = {
  auto: '自动',
  low: '偏低',
  normal: '普通',
  high: '偏高',
}

export const vibrateLabels: Record<string, string> = {
  off: '关闭',
  switch: '换档时',
  edge: '临界时',
  ending: '结算时',
}

export const waitPresets: { id: '8-16' | '10-40' | '20-60'; label: string; min: number; max: number }[] = [
  { id: '8-16', label: '8～16 秒', min: 8, max: 16 },
  { id: '10-40', label: '10～40 秒', min: 10, max: 40 },
  { id: '20-60', label: '20～60 秒', min: 20, max: 60 },
]

export const instructionPaceRatios: Record<'standard' | 'long' | 'veryLong', number> = {
  standard: 1,
  long: 1.5,
  veryLong: 2.5,
}

export const edgeWindowOptions: number[] = [5, 10, 20, 30, 45, 60]

/** 每忍住一次加多少许可率。 */
export const permitStep = 5
/** 许可率最多靠忍住加成多少。 */
export const permitMaxGain = 20
/** 加时赛每次延长的时间占比（%）。 */
export const overtimeStep = 15
/** 加时到第几次必定允许。 */
export const overtimeLimit = 5

// 内置口令：短句、命令式、每条 ≤18 字，六类各 4 条；玩家自己的内容放 customCommands。
export const builtinCommands: Command[] = [
  { id: 'fast-1', type: 'fast', text: '跟着节拍，再快一点' },
  { id: 'fast-2', type: 'fast', text: '握住，保持节奏' },
  { id: 'fast-3', type: 'fast', text: '加快，别停' },
  { id: 'fast-4', type: 'fast', text: '用整只手，跟上拍子' },

  { id: 'slow-1', type: 'slow', text: '慢下来，跟着节拍' },
  { id: 'slow-2', type: 'slow', text: '慢下来，只用掌心' },
  { id: 'slow-3', type: 'slow', text: '放慢一半，感受它' },
  { id: 'slow-4', type: 'slow', text: '一下一下，慢一点' },

  { id: 'rest-1', type: 'rest', text: '停，手拿开' },
  { id: 'rest-2', type: 'rest', text: '松手，放空' },
  { id: 'rest-3', type: 'rest', text: '手放好，别碰' },
  { id: 'rest-4', type: 'rest', text: '停住，等它平息' },

  { id: 'tease-1', type: 'tease', text: '只用指尖' },
  { id: 'tease-2', type: 'tease', text: '隔着布料轻轻碰' },
  { id: 'tease-3', type: 'tease', text: '绕一圈，别急着碰' },
  { id: 'tease-4', type: 'tease', text: '碰一下就走开' },

  { id: 'nipple-1', type: 'nipple', text: '只碰乳头，轻轻的' },
  { id: 'nipple-2', type: 'nipple', text: '用手指捻一下' },
  { id: 'nipple-3', type: 'nipple', text: '只玩乳头，别往下' },
  { id: 'nipple-4', type: 'nipple', text: '夹住，停三秒' },

  { id: 'glans-1', type: 'glans', text: '只碰龟头，慢一点' },
  { id: 'glans-2', type: 'glans', text: '用指尖绕着打圈' },
  { id: 'glans-3', type: 'glans', text: '只玩龟头，别握紧' },
  { id: 'glans-4', type: 'glans', text: '轻触，停一下再动' },
]

/** 把外部传入的 random 收进 [0, 1)，避免 1 这种越界值把下标推出范围。 */
function unitRandom(random: () => number): number {
  const value = random()
  if (!Number.isFinite(value)) return 0
  return Math.min(0.999999, Math.max(0, value))
}

/** 许可率始终是 0–100 的整数百分比。 */
function clampRate(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(100, Math.max(0, Math.round(value)))
}

/** 忍住一次加 5%，最多加 20%，总和不超过 100%。 */
export function nextPermitRate(base: number, heldCount: number): number {
  const count = Number.isFinite(heldCount) ? Math.max(0, Math.floor(heldCount)) : 0
  return clampRate(base + Math.min(count * permitStep, permitMaxGain))
}

export function resolveEnding(
  ending: Ending,
  rate: number,
  random: () => number = Math.random,
  overtimeCount = 0
): 'allow' | 'deny' | 'ruin' {
  const chance = clampRate(rate)
  switch (ending) {
    case 'always':
      return 'allow'
    case 'never':
      return 'deny'
    case 'ruin':
      return unitRandom(random) < 0.5 ? 'ruin' : 'deny'
    case 'overtime':
      if (overtimeCount >= overtimeLimit) return 'allow'
      return unitRandom(random) * 100 < chance ? 'allow' : 'deny'
    default:
      // draw 与 continuous 都按许可率抽签。
      return unitRandom(random) * 100 < chance ? 'allow' : 'deny'
  }
}

/** 按三比例抽签；抽到与上一段相同则重抽一次，仍相同就顺延到下一个非零相位。 */
export function pickPhaseKind(
  ratioFast: number,
  ratioSlow: number,
  ratioRest: number,
  previous: PhaseKind | null,
  random: () => number = Math.random
): PhaseKind {
  const weightOf = (value: number): number => (Number.isFinite(value) ? Math.max(0, value) : 0)
  const weights: Record<PhaseKind, number> = {
    fast: weightOf(ratioFast),
    slow: weightOf(ratioSlow),
    rest: weightOf(ratioRest),
  }
  const total = weights.fast + weights.slow + weights.rest

  const drawOnce = (): PhaseKind => {
    if (total <= 0) return 'fast'
    let point = unitRandom(random) * total
    for (const kind of phaseOrder) {
      point -= weights[kind]
      if (point < 0) return kind
    }
    // 浮点误差兜底：取最后一个非零相位。
    return nonZeroPhases().at(-1) ?? 'fast'
  }

  const nonZeroPhases = (): PhaseKind[] => phaseOrder.filter(kind => weights[kind] > 0)

  // 顺延：沿 phaseOrder 从 previous 往后找第一个非零相位；全零时只保证不与 previous 相同。
  const shiftPast = (kind: PhaseKind): PhaseKind => {
    const pool = nonZeroPhases()
    if (!pool.length) return kind === 'fast' ? 'slow' : 'fast'
    const start = phaseOrder.indexOf(kind)
    for (let step = 1; step <= phaseOrder.length; step++) {
      const next = phaseOrder[(start + step) % phaseOrder.length]!
      if (weights[next] > 0) return next
    }
    return pool[0]!
  }

  const first = drawOnce()
  if (first !== previous) return first
  const second = drawOnce()
  if (second !== previous) return second
  return shiftPast(previous)
}

/** 阶段时长：rest 固定 10–16 秒且不乘指令时长倍率，fast/slow 为 18–31 秒乘倍率。 */
export function phaseDurationMs(
  kind: PhaseKind,
  pace: 'standard' | 'long' | 'veryLong',
  random: () => number = Math.random
): number {
  if (kind === 'rest') return Math.round(10_000 + unitRandom(random) * 6_000)
  const ratio = instructionPaceRatios[pace] ?? 1
  return Math.round((18_000 + unitRandom(random) * 13_000) * ratio)
}

/** 等待时长（毫秒）：随机档用预设区间，固定档用用户给的最短／最长。 */
export function waitDurationMs(
  mode: 'random' | 'fixed',
  preset: '8-16' | '10-40' | '20-60',
  min: number,
  max: number,
  random: () => number = Math.random
): number {
  const presetRange = waitPresets.find(item => item.id === preset) ?? waitPresets[0]!
  const clampSeconds = (value: number, fallback: number): number => {
    if (!Number.isFinite(value)) return fallback
    return Math.min(120, Math.max(3, value))
  }
  let low = clampSeconds(mode === 'fixed' ? min : presetRange.min, presetRange.min)
  let high = clampSeconds(mode === 'fixed' ? max : presetRange.max, presetRange.max)
  if (low > high) [low, high] = [high, low]
  return Math.round((low + unitRandom(random) * (high - low)) * 1000)
}

/** 按启用的类型拼出可用口令池：内置在前、自定义在后，禁用的内置 id 不进池。 */
export function commandPool(
  types: CommandType[],
  custom: { text: string; type: CommandType }[],
  disabled: string[]
): Command[] {
  const allowed = new Set(types)
  const blocked = new Set(disabled)
  const pool = builtinCommands.filter(command => allowed.has(command.type) && !blocked.has(command.id))
  custom.forEach((item, index) => {
    if (!allowed.has(item.type)) return
    pool.push({ id: `custom-${index + 1}`, type: item.type, text: item.text })
  })
  return pool
}

/** 从口令池随机取一条，且尽量不与上一条相同（池里只剩一条时只能重复）。 */
export function pickCommand(pool: Command[], lastId: string, random: () => number = Math.random): Command | null {
  if (!pool.length) return null
  if (pool.length === 1) return pool[0]!
  const lastIndex = pool.findIndex(command => command.id === lastId)
  const index = Math.floor(unitRandom(random) * (pool.length - 1))
  const picked = lastIndex >= 0 && index >= lastIndex ? index + 1 : index
  return pool[picked]!
}
