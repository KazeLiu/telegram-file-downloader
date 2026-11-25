import {
  bindCommands, buildTimeline, commandPool, decideFinale, dropOverlongCommands, filterByCategories, mulberry32, permitRate,
  pickToneLine, randomSeed, restSeconds, taskAt, toneAfterForCommand, toneForTask,
  type EdgeCommand, type EdgeMode, type Task, type ToneKind, varyBpm } from './engine.ts'
import type { EdgeSettings } from './settings.ts'
import { toneLines } from './tones.ts'

/** 一局寸止的状态机：与界面无关，只吃时间增量、吐当前该显示什么。 */
export type SessionPhase = 'run' | 'allow' | 'done'

/** 结算原因。数值语义与播放器的结束原因一致。 */
export type SessionOutcome = 'allow' | 'deny' | 'ruin' | 'lost' | 'manual'

export interface SessionFrame {
  phase: SessionPhase
  /** 第几轮（连续 / 加时会增加） */
  round: number
  /** 已经过的时间（毫秒） */
  elapsed: number
  /** 本局总时长（毫秒，加时会变长） */
  totalMs: number
  /** 当前这一条指令 */
  task: Task | null
  /** 当前显示的模式（等它平息期间恒为 stop） */
  mode: EdgeMode
  /** 当前显示的指令文本 */
  text: string
  /** 当前这一条附带的小字提示 */
  hint: string
  /** 这一条已经走过的比例 0–1 */
  taskProgress: number
  /** 这一条总共多少秒 */
  taskSeconds: number
  /** 正在「等它平息」 */
  cooling: boolean
  /** 累计忍住次数 */
  held: number
  /** 当前许可率 0–1 */
  permit: number
  /** 许可窗口剩余秒（仅在 allow 阶段有意义） */
  windowLeft: number
  /** 提示语（加时 / 新一轮） */
  note: string
  /** 口吻短句：放在指令前的一句 */
  toneBefore: string
  /** 口吻短句：放在指令后的一句 */
  toneAfter: string
  /** 这一条用的口吻（normal 表示没有口吻） */
  tone: ToneKind | 'normal'
}

export const cooldownText = '松手。等它平息。'
export const cooldownHint = '已记录忍住。下一条指令前不许碰。'

/** 随机时长的取值范围（分钟）：参考站「随机」固定在 5～20 分钟之间决定。 */
export const durationRandomMin = 5
export const durationRandomMax = 20

/** 大会话按 seed 铺一整条时间线；乳头 / 龟头专属段需要额外的指令池。 */
function makeTimeline(
  settings: EdgeSettings, pool: EdgeCommand[], seed: number, totalMs: number,
  nipple: EdgeCommand[], glans: EdgeCommand[],
) {
  const tasks = buildTimeline({
    seed,
    totalMs,
    difficulty: settings.difficulty,
    tune: settings.tune,
    length: settings.instructionLength,
    nipple: settings.nipple.on ? { times: settings.nipple.times } : undefined,
    glans: settings.glans.on ? { times: settings.glans.times } : undefined,
  })
  const bound = bindCommands(tasks, pool, nipple, glans)
  // 每次变换节奏：开启后每条绿黄指令的 BPM 在范围内重新随机（同一条始终稳定）。
  if (settings.bpmRandom.on) {
    for (const task of bound) {
      const random = mulberry32((seed ^ Math.imul(task.index + 1, 0x9e3779b1)) >>> 0)
      task.command = varyBpm(task.command, settings.bpmRandom, random)
    }
  }
  return bound
}

export class EdgeSession {
  readonly settings: EdgeSettings
  /** 本局实际分钟数（随机时长时与设置里的 minutes 不同） */
  readonly minutes: number
  private readonly pool: EdgeCommand[]
  private readonly nipplePool: EdgeCommand[]
  private readonly glansPool: EdgeCommand[]
  private random: () => number
  tasks: Task[] = []
  phase: SessionPhase = 'run'
  round = 1
  elapsed = 0
  totalMs = 0
  held = 0
  windowLeft = 0
  outcome: SessionOutcome | null = null
  /** 这次许可属于「松手射精」：文案与结算都换成松手那一套。 */
  ruined = false
  note = ''
  private coolingStart = 0
  private coolingEnd = 0
  private toneCache = new Map<number, { tone: ToneKind | 'normal'; before: string; after: string }>()
  readonly seed: number

  constructor(settings: EdgeSettings, options: { nipple?: EdgeCommand[]; glans?: EdgeCommand[] } = {}) {
    this.settings = settings
    this.nipplePool = options.nipple ?? []
    this.glansPool = options.glans ?? []
    this.seed = settings.seed || randomSeed()
    this.random = mulberry32(this.seed)
    // 随机时长：每局在 5～20 分钟之间重新决定，结束前不知道有多久（也不显示剩余时间）。
    const minutes = settings.durationRandom
      ? durationRandomMin + Math.floor(this.random() * (durationRandomMax - durationRandomMin + 1))
      : settings.minutes
    this.minutes = minutes
    // 指令池要按本局时长剔除过长的指令，所以放在算出分钟数之后。
    this.pool = dropOverlongCommands(
      filterByCategories(
        commandPool(settings.disabled, settings.custom, settings.hand, undefined, { toy: settings.toy, aneros: settings.aneros }),
        settings.categories
      ),
      minutes
    )
    this.totalMs = Math.max(60_000, Math.round(minutes * 60_000))
    this.tasks = makeTimeline(settings, this.pool, this.seed, this.totalMs, this.nipplePool, this.glansPool)
  }

  get finished() { return this.phase === 'done' }

  /** 当前许可率：难度基础值（或手调）＋ 每次忍住 +5%，累计最多 +20%，封顶 100%。 */
  get permit() { return permitRate(this.settings.difficulty, this.held, this.settings.tune.chance) }

  get remainingMs() { return Math.max(0, this.totalMs - this.elapsed) }

  get task() { return taskAt(this.tasks, this.elapsed) }

  get cooling() { return this.phase === 'run' && this.elapsed < this.coolingEnd }

  /** 这一条的口吻短句；同一条始终返回同一句，便于渲染时不抖动。 */
  private toneOf(task: Task | null) {
    if (!task) return { tone: 'normal' as const, before: '', after: '' }
    const cached = this.toneCache.get(task.index)
    if (cached) return cached
    const settings = this.settings
    const tone = toneForTask(settings.tones, task.index + 1)
    let before = ''
    let after = ''
    if (tone !== 'normal' && settings.toneLine.show) {
      const command = task.command
      const touching = command?.category === 'nipple'
        || (task.mode === 'stop' && (command?.category === 'tease' || command?.category === 'pain'))
      const table = toneLines[tone] as Record<string, { before: string[]; after: string[] } | undefined>
      const lines = (touching && table.nipple) || table[task.mode] || null
      if (lines) {
        const random = mulberry32((this.seed ^ Math.imul(task.index + 1, 0x9e3779b1)) >>> 0)
        const picked = pickToneLine(lines, random, {
          before: settings.toneLine.before,
          after: toneAfterForCommand(command ?? null, settings.toneLine.after)
        })
        before = picked.before ?? ''
        after = picked.after ?? ''
      }
    }
    const value = { tone, before, after }
    this.toneCache.set(task.index, value)
    return value
  }

  frame(): SessionFrame {
    const task = this.task
    const cooling = this.cooling
    const mode: EdgeMode = cooling ? 'stop' : task?.mode ?? 'stop'
    const tone = cooling ? { tone: 'normal' as const, before: '', after: '' } : this.toneOf(task)
    const seconds = task ? task.seconds : 0
    const progress = task ? Math.min(1, Math.max(0, (this.elapsed - task.at) / Math.max(1, seconds * 1000))) : 0
    const coolSpan = Math.max(1, this.coolingEnd - this.coolingStart)
    const coolProgress = cooling ? Math.min(1, Math.max(0, (this.elapsed - this.coolingStart) / coolSpan)) : 0
    return {
      phase: this.phase,
      round: this.round,
      elapsed: this.elapsed,
      totalMs: this.totalMs,
      task,
      mode,
      text: cooling ? cooldownText : task?.command?.text ?? '',
      hint: cooling ? cooldownHint : task?.command?.hint ?? '',
      taskProgress: cooling ? coolProgress : progress,
      taskSeconds: cooling ? Math.round(coolSpan / 1000) : seconds,
      cooling,
      held: this.held,
      permit: this.permit,
      windowLeft: this.windowLeft,
      note: this.note,
      tone: cooling ? ('normal' as const) : tone.tone,
      toneBefore: cooling ? '' : tone.before,
      toneAfter: cooling ? '' : tone.after
    }
  }

  /** 推进时间；返回是否仍在进行。 */
  tick(deltaMs: number) {
    if (this.phase === 'done' || deltaMs <= 0) return !this.finished
    if (this.phase === 'allow') {
      this.windowLeft = Math.max(0, this.windowLeft - deltaMs / 1000)
      if (this.windowLeft <= 0) this.closeWindow()
      return !this.finished
    }
    this.elapsed += deltaMs
    if (this.elapsed >= this.totalMs) {
      this.elapsed = this.totalMs
      this.settle()
    }
    return !this.finished
  }

  /** 忍住了：次数 +1，并立刻切到「等它平息」。 */
  hold() {
    if (this.phase !== 'run') return false
    this.held += 1
    this.coolingStart = this.elapsed
    this.coolingEnd = this.elapsed + restSeconds(this.settings.rest, this.random) * 1000
    this.note = ''
    return true
  }

  /** 射了（没忍住）：直接判负。 */
  lose() {
    if (this.phase === 'done') return
    this.finish('lost')
  }

  /** 手动结束。 */
  stop() {
    if (this.phase === 'done') return
    this.finish(this.phase === 'allow' ? 'allow' : 'manual')
  }

  private settle() {
    const settings = this.settings
    const verdict = decideFinale(settings.finale, settings.difficulty, this.held, this.random, settings.tune.chance, settings.allowRuin)
    // 松手射精也是一种「拿到许可」：可以射，但射出的瞬间要松手。
    // 参考站这一支同样进奖励屏，只是文案换成可以射／松手。
    if (verdict === 'ruin' || verdict === 'success') {
      this.phase = 'allow'
      this.ruined = verdict === 'ruin'
      this.windowLeft = Math.max(1, Math.round(settings.rewardSeconds))
      this.coolingEnd = 0
      this.note = ''
      return
    }
    // 加时赛：没拿到许可就往后再放一段时间重抽，次数用完就判负。
    if (settings.finale === 'overtime' && this.round <= settings.overtimeRounds) {
      this.round += 1
      this.totalMs += Math.max(60_000, Math.round(this.totalMs / 4))
      this.tasks = makeTimeline(settings, this.pool, randomSeed(), this.totalMs, this.nipplePool, this.glansPool)
      this.toneCache.clear()
      this.note = `加时 ${this.round - 1}`
      this.coolingEnd = 0
      return
    }
    this.finish('deny')
  }

  /** 许可窗口走完：连续模式开下一轮，否则算成功收场。 */
  private closeWindow() {
    if (this.settings.finale === 'continuous') {
      this.round += 1
      this.elapsed = 0
      this.windowLeft = 0
      this.totalMs = Math.max(60_000, Math.round(this.settings.minutes * 60_000))
      this.tasks = makeTimeline(this.settings, this.pool, randomSeed(), this.totalMs, this.nipplePool, this.glansPool)
      this.toneCache.clear()
      this.coolingStart = 0
      this.coolingEnd = 0
      this.phase = 'run'
      this.note = `第 ${this.round} 轮`
      return
    }
    this.finish('allow')
  }

  private finish(outcome: SessionOutcome) {
    this.phase = 'done'
    this.outcome = outcome === 'allow' && this.ruined ? 'ruin' : outcome
    this.windowLeft = 0
    this.coolingStart = 0
    this.coolingEnd = 0
  }
}
