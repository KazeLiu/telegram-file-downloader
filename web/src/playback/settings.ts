// 寸止玩法的全局设置：对齐参考实现的 settings 结构（去掉联机与语音播报）。
// 与播放列表分离：列表负责「放哪些媒体」，设置负责「怎么玩」。
import {
  bpmRandomMax, bpmRandomMin, dimMin, customCommandLimit, customCommandTextLimit, extendLengthOrder, restMax, restMin,
  textOpacityMin, textScaleMax, textScaleMin, videoVolumeMax,
  type Categories, type CustomCommand, type Difficulty, type ExtendLength, type Finale, type Hand, type InstructionLength,
  toneAfterOrder, toneOrder, type Mix, type RedBeat, type RestMode, type ToneAfter, type ToneKind, type Tune
} from './engine.ts'
import { mirrorPlaces, type MirrorPlace } from './mirror.ts'
import { focusAreas, type FocusArea } from './focus.ts'

export interface EdgeRest {
  mode: RestMode
  seconds: number
  min: number
  max: number
}

export interface EdgeSettings {
  /** 随机种子：整局由它决定，同一个种子可以复现同一局 */
  seed: number
  minutes: number
  durationRandom: boolean
  difficulty: Difficulty
  instructionLength: InstructionLength
  finale: Finale
  categories: Categories
  tune: Tune
  allowRuin: boolean
  /** 加时赛的加时长度：短 / 普通 / 越来越短 */
  extendLen: ExtendLength
  rewardSeconds: number
  rest: EdgeRest
  hand: Hand
  custom: CustomCommand[]
  /** 关掉的指令在 maleCommands 里的下标 */
  disabled: number[]
  /** 只玩乳头 / 只玩龟头：整局固定插入几段专属指令 */
  nipple: { on: boolean; times: number }
  glans: { on: boolean; times: number }
  /** 整局只玩一个部位：开了就不再插入中途的专属段，指令池整局换成该部位的专属池 */
  focus: FocusArea
  /** 道具模式：飞机杯（会剔除只能用手的指令）与前列腺按摩器（红色段追加夹紧指令） */
  toy: boolean
  aneros: boolean
  redBeat: RedBeat
  heartbeat: boolean
  heartbeatVolume: number
  metronome: boolean
  beatVolume: number
  mediaVolume: number
  /** 视频变暗程度 0–100：0 完全透明（原亮度），100 最暗（对齐参考站的 dim）。 */
  dim: number
  hideRemaining: boolean
  mixAudio: boolean
  /** 开始后是否提示打开悬浮小窗（参考站的 pip-want，只影响提示）。 */
  pipOffer: boolean
  /** 常看的网站（选填，只存本机）；打开小窗后可以一键跳过去。 */
  pipSite: string
  /** 每次变换节奏：绿黄指令的 BPM 在范围内每次重新随机 */
  bpmRandom: { on: boolean; min: number; max: number }
  /** 逐条 BPM 覆盖：键是口令下标，0 表示这条不打节拍（对齐参考站的 `data-sundome-bpm-input`）。 */
  bpm: Record<string, number>
  /** 心跳跟随 BPM：关掉后红色带 BPM 时心跳仍保持固定节奏 */
  heartbeatSync: boolean
  /** 切换时振动：仅限手机 */
  vibrate: boolean
  /** 振动的时机 */
  vibrateOn: { command: boolean; edge: boolean; finish: boolean }
  /** 红色（不许碰）时也继续播放视频：关掉时红色会暂停并额外变暗（参考站默认行为） */
  keepVideoOnStop: boolean
  /** 每换一条指令就换一个视频 */
  switchVideoPerCommand: boolean
  /** 视频/图片铺法：cover=铺满屏幕，contain=显示完整画面（上下留黑边） */
  fit: 'cover' | 'contain'
  /** contain 时的画面位置 */
  pos: 'top' | 'center' | 'bottom'
  /** 指令文字不透明度（30–100） */
  textOpacity: number
  /** 指令文字大小（60–100，参考站只有缩小没有放大） */
  textScale: number
  /** 按“忍住了”之后的等待时间也继续播放视频 */
  keepVideoWhileCooling: boolean
  /** 视频声音：关 / 只在最后（获得许可时）/ 一直开 */
  videoSound: 'off' | 'end' | 'always'
  /** 视频从中间开始播放：跳过试看片前半段的打招呼和采访 */
  skipIntro: boolean
  /** 口吻：每种开启后在指令前后加一句同口吻的短句 */
  tones: Record<ToneKind, boolean>
  toneLine: { show: boolean; before: boolean; after: ToneAfter }
  /** 镜子：把前置摄像头左右翻转后显示在屏幕上 */
  mirror: { on: boolean; place: MirrorPlace }
}

export const edgeStorageKey = 'shicun.edge.v1'
export const edgeSchemaVersion = 1

const allCategories: Categories = { edge: true, tease: true, pose: true, pain: false }

export const defaultEdgeSettings: EdgeSettings = {
  seed: 0,
  minutes: 10,
  durationRandom: false,
  difficulty: 'normal',
  instructionLength: 'standard',
  finale: 'draw',
  categories: { ...allCategories },
  tune: { chance: null, stop: null, mix: null },
  allowRuin: false,
  extendLen: 'normal',
  rewardSeconds: 10,
  rest: { mode: 'random', seconds: 12, min: 8, max: 16 },
  hand: 'right',
  custom: [],
  disabled: [],
  nipple: { on: false, times: 1 },
  glans: { on: false, times: 1 },
  focus: 'none',
  toy: false,
  aneros: false,
  redBeat: 'heartbeat',
  heartbeat: true,
  heartbeatVolume: 100,
  metronome: true,
  beatVolume: 100,
  mediaVolume: 60,
  dim: 55,
  hideRemaining: false,
  mixAudio: false,
  pipOffer: true,
  pipSite: '',
  bpmRandom: { on: false, min: 60, max: 160 },
  bpm: {},
  heartbeatSync: true,
  vibrate: true,
  vibrateOn: { command: true, edge: true, finish: true },
  keepVideoOnStop: false,
  switchVideoPerCommand: false,
  keepVideoWhileCooling: true,
  fit: 'cover',
  pos: 'center',
  textOpacity: 100,
  textScale: 100,
  videoSound: 'end',
  skipIntro: false,
  tones: { strong: false, tease: false, abuse: false, sweet: false, feet: false },
  toneLine: { show: true, before: true, after: 'half' },
  mirror: { on: false, place: 'corner' }
}

const difficulties: Difficulty[] = ['easy', 'normal', 'hard', 'hell']
const finales: Finale[] = ['draw', 'always', 'never', 'ruin', 'continuous', 'overtime']
const lengths: InstructionLength[] = ['standard', 'long', 'veryLong']
const extendLengths: ExtendLength[] = [...extendLengthOrder]
const hands: Hand[] = ['right', 'left']
const redBeats: RedBeat[] = ['heartbeat', 'both', 'metronome']
const restModes: RestMode[] = ['random', 'fixed']
const videoSounds: EdgeSettings['videoSound'][] = ['off', 'end', 'always']
const fits: EdgeSettings['fit'][] = ['cover', 'contain']
const positions: EdgeSettings['pos'][] = ['top', 'center', 'bottom']

function clampNumber(value: unknown, min: number, max: number, fallback: number) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return fallback
  return Math.min(max, Math.max(min, Math.round(value)))
}
function pickValue<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback
}
function boolOr(value: unknown, fallback: boolean) {
  return typeof value === 'boolean' ? value : fallback
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}
/** 0–100 的可空百分比（手调许可率）。 */
function nullableRate(value: unknown, min: number, max: number) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return Math.min(max, Math.max(min, Math.round(value)))
}
function readMix(value: unknown): Mix | null {
  if (!isRecord(value)) return null
  const go = nullableRate(value.go, 0, 100)
  const slow = nullableRate(value.slow, 0, 100)
  const stop = nullableRate(value.stop, 0, 60)
  if (go === null || slow === null || stop === null) return null
  const total = go + slow + stop
  if (total !== 100) return null
  return { go, slow, stop }
}
function readCategories(value: unknown): Categories {
  if (!isRecord(value)) return { ...allCategories }
  return {
    edge: boolOr(value.edge, allCategories.edge),
    tease: boolOr(value.tease, allCategories.tease),
    pose: boolOr(value.pose, allCategories.pose),
    pain: boolOr(value.pain, allCategories.pain)
  }
}
function readTones(value: unknown): Record<ToneKind, boolean> {
  const base = { ...defaultEdgeSettings.tones }
  if (!isRecord(value)) return base
  for (const kind of toneOrder) base[kind] = boolOr(value[kind], base[kind])
  return base
}
function readToneLine(value: unknown): EdgeSettings['toneLine'] {
  const base = { ...defaultEdgeSettings.toneLine }
  if (!isRecord(value)) return base
  return {
    show: boolOr(value.show, base.show),
    before: boolOr(value.before, base.before),
    after: pickValue(value.after, toneAfterOrder, base.after)
  }
}
function readMirror(value: unknown): EdgeSettings['mirror'] {
  const base = { ...defaultEdgeSettings.mirror }
  if (!isRecord(value)) return base
  return {
    on: boolOr(value.on, base.on),
    place: pickValue(value.place, mirrorPlaces, base.place)
  }
}
function readRest(value: unknown): EdgeRest {
  if (!isRecord(value)) return { ...defaultEdgeSettings.rest }
  const min = clampNumber(value.min, restMin, restMax, defaultEdgeSettings.rest.min)
  const max = clampNumber(value.max, restMin, restMax, defaultEdgeSettings.rest.max)
  return {
    mode: pickValue(value.mode, restModes, defaultEdgeSettings.rest.mode),
    seconds: clampNumber(value.seconds, restMin, restMax, defaultEdgeSettings.rest.seconds),
    min: Math.min(min, max),
    max: Math.max(min, max)
  }
}
function readCustom(value: unknown): CustomCommand[] {
  if (!Array.isArray(value)) return []
  const commands: CustomCommand[] = []
  for (const item of value) {
    if (!isRecord(item) || typeof item.text !== 'string') continue
    const text = item.text.trim().slice(0, customCommandTextLimit)
    if (!text) continue
    const mode = item.mode === 'go' || item.mode === 'slow' || item.mode === 'stop' ? item.mode : 'go'
    const bpm = typeof item.bpm === 'number' && Number.isFinite(item.bpm) ? Math.min(300, Math.max(20, Math.round(item.bpm))) : undefined
    commands.push(bpm ? { text, mode, bpm } : { text, mode })
    if (commands.length >= customCommandLimit) break
  }
  return commands
}
function readDisabled(value: unknown): number[] {
  if (!Array.isArray(value)) return []
  const seen = new Set<number>()
  for (const item of value) {
    if (typeof item === 'number' && Number.isInteger(item) && item >= 0) seen.add(item)
  }
  return [...seen].sort((a, b) => a - b)
}

function readFocus(value: unknown, fallback: { on: boolean; times: number }) {
  if (!isRecord(value)) return { ...fallback }
  return { on: boolOr(value.on, fallback.on), times: clampNumber(value.times, 1, 4, fallback.times) }
}

function readVibrateOn(value: unknown): EdgeSettings['vibrateOn'] {
  const base = { ...defaultEdgeSettings.vibrateOn }
  if (!isRecord(value)) return base
  return {
    command: boolOr(value.command, base.command),
    edge: boolOr(value.edge, base.edge),
    finish: boolOr(value.finish, base.finish)
  }
}

function readBpmRandom(value: unknown): EdgeSettings['bpmRandom'] {
  const base = { ...defaultEdgeSettings.bpmRandom }
  if (!isRecord(value)) return base
  const min = clampNumber(value.min, bpmRandomMin, bpmRandomMax, base.min)
  const max = clampNumber(value.max, bpmRandomMin, bpmRandomMax, base.max)
  return { on: boolOr(value.on, base.on), min: Math.min(min, max), max: Math.max(min, max) }
}

/** 逐条 BPM 覆盖：键必须是非负整数口令下标，值 0–300（0 表示这条不打节拍）。 */
function readBpmMap(value: unknown): Record<string, number> {
  if (!isRecord(value)) return {}
  const result: Record<string, number> = {}
  for (const [key, raw] of Object.entries(value)) {
    if (!/^\d+$/.test(key)) continue
    if (typeof raw !== 'number' || !Number.isFinite(raw)) continue
    const rate = Math.min(300, Math.max(0, Math.round(raw)))
    if (rate > 0) result[key] = rate
  }
  return result
}

/** 容错读入：任何字段坏了都退回默认值，绝不抛错。 */
/** 常看的网站：只留 http(s)，最多 200 字。 */
function readPipSite(value: unknown): string {
  if (typeof value !== 'string') return defaultEdgeSettings.pipSite
  const text = value.trim().slice(0, 200)
  return /^https?:\/\//i.test(text) ? text : ''
}

export function normalizeEdgeSettings(raw: unknown): EdgeSettings {
  if (!isRecord(raw)) return { ...defaultEdgeSettings, categories: { ...allCategories }, tune: { ...defaultEdgeSettings.tune }, rest: { ...defaultEdgeSettings.rest }, custom: [], disabled: [] }
  const tune = isRecord(raw.tune) ? raw.tune : {}
  return {
    seed: typeof raw.seed === 'number' && Number.isFinite(raw.seed) ? Math.abs(Math.floor(raw.seed)) >>> 0 : 0,
    minutes: clampNumber(raw.minutes, 1, 180, defaultEdgeSettings.minutes),
    durationRandom: boolOr(raw.durationRandom, defaultEdgeSettings.durationRandom),
    difficulty: pickValue(raw.difficulty, difficulties, defaultEdgeSettings.difficulty),
    instructionLength: pickValue(raw.instructionLength, lengths, defaultEdgeSettings.instructionLength),
    finale: pickValue(raw.finale, finales, defaultEdgeSettings.finale),
    categories: readCategories(raw.categories),
    tune: {
      chance: nullableRate(tune.chance, 10, 100),
      stop: nullableRate(tune.stop, 0, 60),
      mix: readMix(tune.mix)
    },
    allowRuin: boolOr(raw.allowRuin, defaultEdgeSettings.allowRuin),
    extendLen: pickValue(raw.extendLen, extendLengths, defaultEdgeSettings.extendLen),
    rewardSeconds: clampNumber(raw.rewardSeconds, 5, 60, defaultEdgeSettings.rewardSeconds),
    rest: readRest(raw.rest),
    hand: pickValue(raw.hand, hands, defaultEdgeSettings.hand),
    custom: readCustom(raw.custom),
    disabled: readDisabled(raw.disabled),
    nipple: readFocus(raw.nipple, defaultEdgeSettings.nipple),
    glans: readFocus(raw.glans, defaultEdgeSettings.glans),
    focus: pickValue(raw.focus, focusAreas, defaultEdgeSettings.focus),
    toy: boolOr(raw.toy, defaultEdgeSettings.toy),
    aneros: boolOr(raw.aneros, defaultEdgeSettings.aneros),
    redBeat: pickValue(raw.redBeat, redBeats, defaultEdgeSettings.redBeat),
    heartbeat: boolOr(raw.heartbeat, defaultEdgeSettings.heartbeat),
    heartbeatVolume: clampNumber(raw.heartbeatVolume, 0, 300, defaultEdgeSettings.heartbeatVolume),
    metronome: boolOr(raw.metronome, defaultEdgeSettings.metronome),
    beatVolume: clampNumber(raw.beatVolume, 0, 300, defaultEdgeSettings.beatVolume),
    mediaVolume: clampNumber(raw.mediaVolume, 0, videoVolumeMax, defaultEdgeSettings.mediaVolume),
    dim: clampNumber(raw.dim, dimMin, 100, defaultEdgeSettings.dim),
    hideRemaining: boolOr(raw.hideRemaining, defaultEdgeSettings.hideRemaining),
    mixAudio: boolOr(raw.mixAudio, defaultEdgeSettings.mixAudio),
    pipOffer: boolOr(raw.pipOffer, defaultEdgeSettings.pipOffer),
    pipSite: readPipSite(raw.pipSite),
    bpmRandom: readBpmRandom(raw.bpmRandom),
    bpm: readBpmMap(raw.bpm),
    heartbeatSync: boolOr(raw.heartbeatSync, defaultEdgeSettings.heartbeatSync),
    vibrate: boolOr(raw.vibrate, defaultEdgeSettings.vibrate),
    vibrateOn: readVibrateOn(raw.vibrateOn),
    keepVideoOnStop: boolOr(raw.keepVideoOnStop, defaultEdgeSettings.keepVideoOnStop),
    switchVideoPerCommand: boolOr(raw.switchVideoPerCommand, defaultEdgeSettings.switchVideoPerCommand),
    keepVideoWhileCooling: boolOr(raw.keepVideoWhileCooling, defaultEdgeSettings.keepVideoWhileCooling),
    fit: pickValue(raw.fit, fits, defaultEdgeSettings.fit),
    pos: pickValue(raw.pos, positions, defaultEdgeSettings.pos),
    textOpacity: clampNumber(raw.textOpacity, textOpacityMin, 100, defaultEdgeSettings.textOpacity),
    textScale: clampNumber(raw.textScale, textScaleMin, textScaleMax, defaultEdgeSettings.textScale),
    videoSound: pickValue(raw.videoSound, videoSounds, defaultEdgeSettings.videoSound),
    skipIntro: boolOr(raw.skipIntro, defaultEdgeSettings.skipIntro),
    tones: readTones(raw.tones),
    toneLine: readToneLine(raw.toneLine),
    mirror: readMirror(raw.mirror)
  }
}

export function readEdgeSettings(value: string | null): EdgeSettings {
  if (!value) return normalizeEdgeSettings(null)
  try {
    return normalizeEdgeSettings(JSON.parse(value))
  } catch {
    return normalizeEdgeSettings(null)
  }
}

export function writeEdgeSettings(settings: EdgeSettings) {
  try {
    localStorage.setItem(edgeStorageKey, JSON.stringify({ ...settings, schemaVersion: edgeSchemaVersion }))
    return ''
  } catch {
    return '无法保存设置到本机，请检查浏览器存储空间或隐私设置。'
  }
}
