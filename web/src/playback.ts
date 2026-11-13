export type MediaKind = 'image' | 'video' | 'mixed'
export type ImageTiming = 'time' | 'beat'
// 寸止控制器用到的取值按契约就地内联：不从 ./playback/edge 导入，避免循环依赖。
export type Difficulty = 'easy' | 'normal' | 'hard' | 'hell'
export type Ending = 'draw' | 'always' | 'never' | 'ruin' | 'continuous' | 'overtime'
export type Tone = 'firm' | 'tease' | 'degrade' | 'gentle'
export type CommandType = 'fast' | 'slow' | 'rest' | 'tease' | 'nipple' | 'glans'
export type Hand = 'right' | 'left'
export type WaitMode = 'random' | 'fixed'
export type WaitPreset = '8-16' | '10-40' | '20-60'
export type InstructionPace = 'standard' | 'long' | 'veryLong'
export type VibrateMode = 'off' | 'switch' | 'edge' | 'ending'
export type VoicePitch = 'auto' | 'low' | 'normal' | 'high'
export interface CustomCommand { text: string; type: CommandType }
export interface Gallery { id: string; path: string }
export interface PlaybackMedia { root: string; path: string; name: string; kind: 'image' | 'video'; version: string; identity?: string }
export interface Playlist {
  id: string; name: string; roots: string[]; kind: MediaKind; order: 'sequential' | 'shuffle'
  imageSeconds: number; imageTiming: ImageTiming; minutes: number; loop: boolean; bpm: number; metronome: boolean; speech: boolean; favoritesOnly: boolean
  imageCount: number; mediaVolume: number; beatVolume: number; speechVolume: number; speechRate: number; hideTime: boolean; brightness: number
  // schemaVersion 3 新增：玩法、指令与声音字段。全部可选读入，缺省补默认。
  difficulty: Difficulty; ratioFast: number; ratioSlow: number; ratioRest: number; permitBase: number
  ending: Ending; edgeWindow: number
  waitMode: WaitMode; waitPreset: WaitPreset; waitMin: number; waitMax: number; instructionPace: InstructionPace
  tones: Tone[]; hand: Hand; commandTypes: CommandType[]; props: string[]; customCommands: CustomCommand[]; disabledCommands: string[]
  heartbeat: boolean; heartbeatVolume: number; vibrate: VibrateMode; voicePitch: VoicePitch
}
export interface PlaybackPreferences { schemaVersion?: number; playlists: Playlist[]; selected: string; favorites: string[]; shownImages: string[] }
// 存储键沿用 v1：改键会让既有本机数据变成孤儿数据；版本号写在数据的 schemaVersion 字段里。
export const playbackStorageKey = 'shicun.playback.v1'
export const playbackSchemaVersion = 3
export const playbackConfigFormat = 'shicun.playback.config.v3'
export const legacyPlaybackConfigFormats: readonly string[] = ['shicun.playback.config.v1', 'shicun.playback.config.v2']
// 已展示记录上限：按最早的记录淘汰，避免长时间使用顶满 localStorage 配额。
export const shownImagesLimit = 20000
// 自定义口令的条数与单条字数上限，设置页与校验共用。
export const customCommandLimit = 30
export const customCommandTextLimit = 60

const kinds: MediaKind[] = ['image', 'video', 'mixed']
const orders: Playlist['order'][] = ['sequential', 'shuffle']
const timings: ImageTiming[] = ['time', 'beat']
const speechRates = [0.8, 1, 1.2]
const difficulties: Difficulty[] = ['easy', 'normal', 'hard', 'hell']
const endings: Ending[] = ['draw', 'always', 'never', 'ruin', 'continuous', 'overtime']
const tones: Tone[] = ['firm', 'tease', 'degrade', 'gentle']
const hands: Hand[] = ['right', 'left']
const waitModes: WaitMode[] = ['random', 'fixed']
const waitPresetOptions: WaitPreset[] = ['8-16', '10-40', '20-60']
const instructionPaces: InstructionPace[] = ['standard', 'long', 'veryLong']
const vibrateModes: VibrateMode[] = ['off', 'switch', 'edge', 'ending']
const voicePitches: VoicePitch[] = ['auto', 'low', 'normal', 'high']
const commandTypeOptions: CommandType[] = ['fast', 'slow', 'rest', 'tease', 'nipple', 'glans']
const propOptions = ['cup', 'aneros']
const toneSet = new Set<string>(tones)
const commandTypeSet = new Set<string>(commandTypeOptions)
const propSet = new Set<string>(propOptions)
// 内置口令 id 形如 fast-1 / rest-2（契约规定六类各 4 条）；只按形状校验，避免与 edge.ts 的清单互相耦合。
const builtinCommandId = /^(fast|slow|rest|tease|nipple|glans)-[1-9]\d?$/
// 难度对应的三相位默认比例：数值与 web/src/playback/edge.ts 的 difficultyProfiles 保持一致（改一处必须同步另一处）。
const difficultyRatios: Record<Difficulty, { fast: number; slow: number; rest: number }> = {
  easy: { fast: 50, slow: 30, rest: 20 },
  normal: { fast: 60, slow: 20, rest: 20 },
  hard: { fast: 55, slow: 20, rest: 25 },
  hell: { fast: 45, slow: 20, rest: 35 }
}
const ranges = {
  imageSeconds: [1, 300], minutes: [0, 180], bpm: [30, 180], imageCount: [0, 100000],
  mediaVolume: [0, 100], beatVolume: [0, 100], speechVolume: [0, 100], brightness: [20, 100],
  ratio: [0, 100], permitBase: [30, 95], edgeWindow: [5, 60], wait: [3, 120], heartbeatVolume: [0, 100]
} as const
const defaults = {
  imageSeconds: 8, minutes: 10, bpm: 100, imageCount: 0,
  mediaVolume: 100, beatVolume: 100, speechVolume: 100, brightness: 100,
  permitBase: 70, edgeWindow: 10, waitMin: 8, waitMax: 16, heartbeatVolume: 100
}
const addedDefaults = {
  imageTiming: 'time' as ImageTiming, imageCount: defaults.imageCount, mediaVolume: defaults.mediaVolume,
  beatVolume: defaults.beatVolume, speechVolume: defaults.speechVolume, speechRate: 1, hideTime: false, brightness: defaults.brightness,
  difficulty: 'normal' as Difficulty,
  ratioFast: difficultyRatios.normal.fast, ratioSlow: difficultyRatios.normal.slow, ratioRest: difficultyRatios.normal.rest,
  permitBase: defaults.permitBase, ending: 'draw' as Ending, edgeWindow: defaults.edgeWindow,
  waitMode: 'random' as WaitMode, waitPreset: '8-16' as WaitPreset, waitMin: defaults.waitMin, waitMax: defaults.waitMax,
  instructionPace: 'standard' as InstructionPace,
  tones: ['firm'] as Tone[], hand: 'right' as Hand,
  commandTypes: [...commandTypeOptions], props: [] as string[], customCommands: [] as CustomCommand[], disabledCommands: [] as string[],
  heartbeat: true, heartbeatVolume: defaults.heartbeatVolume,
  vibrate: 'off' as VibrateMode, voicePitch: 'auto' as VoicePitch
}

// 列表必须逐份拷贝：直接展开 addedDefaults 会让所有播放列表共用同一组数组。
function cloneAddedDefaults() {
  return {
    ...addedDefaults, tones: [...addedDefaults.tones], commandTypes: [...addedDefaults.commandTypes],
    props: [...addedDefaults.props], customCommands: addedDefaults.customCommands.map(item => ({ ...item })),
    disabledCommands: [...addedDefaults.disabledCommands]
  }
}

export function newPlaylist(): Playlist {
  return { id: newId(), name: '新播放列表', roots: [], kind: 'mixed', order: 'shuffle', imageSeconds: defaults.imageSeconds,
    minutes: defaults.minutes, loop: true, bpm: defaults.bpm, metronome: false, speech: false, favoritesOnly: false, ...cloneAddedDefaults() }
}

const rescueHint = `原始内容仍保存在浏览器存储的 ${playbackStorageKey} 里，可先复制备份，或用 recoverPreferences 抢救仍可用的条目；图库原文件不受影响。`
function damaged(detail: string) { return `本机播放数据损坏：${detail}。${rescueHint}` }
function isRecord(value: unknown): value is Record<string, unknown> { return !!value && typeof value === 'object' && !Array.isArray(value) }
function newId() { return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}` }
function pick<T extends string | number>(value: unknown, allowed: readonly T[], fallback: T): T { return allowed.includes(value as T) ? value as T : fallback }
function repairNumber(value: unknown, min: number, max: number, fallback: number) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return fallback
  return Math.min(max, Math.max(min, Math.round(value)))
}
function booleanOr(value: unknown, fallback: boolean) { return typeof value === 'boolean' ? value : fallback }
function playlistId(value: unknown) { return typeof value === 'string' && value.trim() ? value : newId() }
function playlistName(value: unknown) {
  const name = typeof value === 'string' ? value.trim().slice(0, 80) : ''
  return name || '未命名播放列表'
}
function readList(raw: unknown, name: string, salvage: boolean, issues: string[]) {
  if (raw === undefined) return []
  if (!Array.isArray(raw)) {
    if (!salvage) throw new Error(damaged(`${name} 不是列表`))
    issues.push(`${name} 不是列表，已按空列表处理`)
    return []
  }
  const list = raw.filter((item): item is string => typeof item === 'string')
  if (list.length !== raw.length) issues.push(`${name} 中有 ${raw.length - list.length} 项不是字符串，已跳过`)
  return list
}
// 读字符串列表：去掉非字符串、空白、未知项与重复项；accept 决定哪些值算已知项。
function repairList(raw: unknown, name: string, issues: string[], accept: (text: string) => boolean) {
  if (raw === undefined) return []
  if (!Array.isArray(raw)) {
    issues.push(`${name} 不是列表，已按空列表处理`)
    return []
  }
  const items: string[] = []
  let dropped = 0
  for (const item of raw) {
    const text = typeof item === 'string' ? item.trim() : ''
    if (!text || !accept(text) || items.includes(text)) { dropped += 1; continue }
    items.push(text)
  }
  if (dropped) issues.push(`${name} 中有 ${dropped} 项无法识别，已跳过`)
  return items
}
// 自定义口令：跳过空串与未知类型，超长截断，超出上限保留最早的 30 条。
function repairCommands(raw: unknown, name: string, issues: string[]): CustomCommand[] {
  if (raw === undefined) return []
  if (!Array.isArray(raw)) {
    issues.push(`${name} 不是列表，已按空列表处理`)
    return []
  }
  const commands: CustomCommand[] = []
  let dropped = 0
  let truncated = 0
  for (const item of raw) {
    const text = isRecord(item) && typeof item.text === 'string' ? item.text.trim() : ''
    if (!text || !isRecord(item) || typeof item.type !== 'string' || !commandTypeSet.has(item.type)) { dropped += 1; continue }
    if (text.length > customCommandTextLimit) truncated += 1
    commands.push({ text: text.slice(0, customCommandTextLimit), type: item.type as CommandType })
  }
  if (dropped) issues.push(`${name} 中有 ${dropped} 条口令格式不正确，已跳过`)
  if (truncated) issues.push(`${name} 中有 ${truncated} 条口令超过 ${customCommandTextLimit} 字，已截断`)
  if (commands.length > customCommandLimit) {
    issues.push(`${name} 超过 ${customCommandLimit} 条上限，已保留前 ${customCommandLimit} 条`)
    return commands.slice(0, customCommandLimit)
  }
  return commands
}

export function trimShownImages(list: string[], limit = shownImagesLimit) {
  return list.length > limit ? list.slice(list.length - limit) : list
}

function normalizePlaylist(raw: Record<string, unknown>, index: number, issues: string[]): Playlist {
  const path = `playlists[${index}]`
  const fix = <T>(key: string, rawValue: unknown, value: T): T => {
    if (rawValue !== value) issues.push(`${path}.${key} 已修正为 ${String(value)}`)
    return value
  }
  const roots = Array.isArray(raw.roots) ? raw.roots.filter((item): item is string => typeof item === 'string') : []
  if (!Array.isArray(raw.roots) || roots.length !== (raw.roots as unknown[]).length) issues.push(`${path}.roots 不是字符串列表，已整理`)
  // 先定难度，再按难度档案修三个比例；合计不为 100 时整组回落到该难度的默认比例。
  const difficulty = fix('difficulty', raw.difficulty, pick(raw.difficulty, difficulties, 'normal'))
  const profile = difficultyRatios[difficulty]
  let ratioFast = fix('ratioFast', raw.ratioFast, repairNumber(raw.ratioFast, ...ranges.ratio, profile.fast))
  let ratioSlow = fix('ratioSlow', raw.ratioSlow, repairNumber(raw.ratioSlow, ...ranges.ratio, profile.slow))
  let ratioRest = fix('ratioRest', raw.ratioRest, repairNumber(raw.ratioRest, ...ranges.ratio, profile.rest))
  if (ratioFast + ratioSlow + ratioRest !== 100) {
    issues.push(`${path} 三相位比例合计 ${ratioFast + ratioSlow + ratioRest} 不是 100，已按「${difficulty}」难度重置为 ${profile.fast}/${profile.slow}/${profile.rest}`)
    ratioFast = profile.fast
    ratioSlow = profile.slow
    ratioRest = profile.rest
  }
  let waitMin = fix('waitMin', raw.waitMin, repairNumber(raw.waitMin, ...ranges.wait, defaults.waitMin))
  let waitMax = fix('waitMax', raw.waitMax, repairNumber(raw.waitMax, ...ranges.wait, defaults.waitMax))
  if (waitMin > waitMax) {
    issues.push(`${path}.waitMin 大于 waitMax，已交换为 ${waitMax}/${waitMin}`)
    const swap = waitMin
    waitMin = waitMax
    waitMax = swap
  }
  // 已知项列表：缺字段用默认值；给了但全是未知项时也回落到默认值。
  const knownList = (key: string, accept: (text: string) => boolean, fallback: readonly string[]) => {
    const value = repairList(raw[key], `${path}.${key}`, issues, accept)
    if (value.length) return value
    if (Array.isArray(raw[key]) && raw[key].length) issues.push(`${path}.${key} 没有可用项，已恢复默认`)
    return [...fallback]
  }
  return {
    id: fix('id', raw.id, playlistId(raw.id)),
    name: fix('name', raw.name, playlistName(raw.name)),
    roots,
    kind: fix('kind', raw.kind, pick(raw.kind, kinds, 'mixed')),
    order: fix('order', raw.order, pick(raw.order, orders, 'shuffle')),
    imageSeconds: fix('imageSeconds', raw.imageSeconds, repairNumber(raw.imageSeconds, ...ranges.imageSeconds, defaults.imageSeconds)),
    imageTiming: fix('imageTiming', raw.imageTiming, pick(raw.imageTiming, timings, 'time')),
    minutes: fix('minutes', raw.minutes, repairNumber(raw.minutes, ...ranges.minutes, defaults.minutes)),
    loop: fix('loop', raw.loop, booleanOr(raw.loop, true)),
    bpm: fix('bpm', raw.bpm, repairNumber(raw.bpm, ...ranges.bpm, defaults.bpm)),
    metronome: fix('metronome', raw.metronome, booleanOr(raw.metronome, false)),
    speech: fix('speech', raw.speech, booleanOr(raw.speech, false)),
    favoritesOnly: fix('favoritesOnly', raw.favoritesOnly, booleanOr(raw.favoritesOnly, false)),
    imageCount: fix('imageCount', raw.imageCount, repairNumber(raw.imageCount, ...ranges.imageCount, defaults.imageCount)),
    mediaVolume: fix('mediaVolume', raw.mediaVolume, repairNumber(raw.mediaVolume, ...ranges.mediaVolume, defaults.mediaVolume)),
    beatVolume: fix('beatVolume', raw.beatVolume, repairNumber(raw.beatVolume, ...ranges.beatVolume, defaults.beatVolume)),
    speechVolume: fix('speechVolume', raw.speechVolume, repairNumber(raw.speechVolume, ...ranges.speechVolume, defaults.speechVolume)),
    speechRate: fix('speechRate', raw.speechRate, pick(raw.speechRate, speechRates, 1)),
    hideTime: fix('hideTime', raw.hideTime, booleanOr(raw.hideTime, false)),
    brightness: fix('brightness', raw.brightness, repairNumber(raw.brightness, ...ranges.brightness, defaults.brightness)),
    difficulty,
    ratioFast,
    ratioSlow,
    ratioRest,
    permitBase: fix('permitBase', raw.permitBase, repairNumber(raw.permitBase, ...ranges.permitBase, defaults.permitBase)),
    ending: fix('ending', raw.ending, pick(raw.ending, endings, 'draw')),
    edgeWindow: fix('edgeWindow', raw.edgeWindow, repairNumber(raw.edgeWindow, ...ranges.edgeWindow, defaults.edgeWindow)),
    waitMode: fix('waitMode', raw.waitMode, pick(raw.waitMode, waitModes, 'random')),
    waitPreset: fix('waitPreset', raw.waitPreset, pick(raw.waitPreset, waitPresetOptions, '8-16')),
    waitMin,
    waitMax,
    instructionPace: fix('instructionPace', raw.instructionPace, pick(raw.instructionPace, instructionPaces, 'standard')),
    tones: knownList('tones', text => toneSet.has(text), ['firm']) as Tone[],
    hand: fix('hand', raw.hand, pick(raw.hand, hands, 'right')),
    commandTypes: knownList('commandTypes', text => commandTypeSet.has(text), commandTypeOptions) as CommandType[],
    props: knownList('props', text => propSet.has(text), []) as string[],
    customCommands: repairCommands(raw.customCommands, `${path}.customCommands`, issues),
    disabledCommands: knownList('disabledCommands', text => builtinCommandId.test(text), []) as string[],
    heartbeat: fix('heartbeat', raw.heartbeat, booleanOr(raw.heartbeat, true)),
    heartbeatVolume: fix('heartbeatVolume', raw.heartbeatVolume, repairNumber(raw.heartbeatVolume, ...ranges.heartbeatVolume, defaults.heartbeatVolume)),
    vibrate: fix('vibrate', raw.vibrate, pick(raw.vibrate, vibrateModes, 'off')),
    voicePitch: fix('voicePitch', raw.voicePitch, pick(raw.voicePitch, voicePitches, 'auto'))
  }
}

function emptyPreferences(): PlaybackPreferences {
  return { schemaVersion: playbackSchemaVersion, playlists: [], selected: '', favorites: [], shownImages: [] }
}

/** 按字段补默认值；只有结构性损坏才抛错。salvage 为真时连结构性损坏也只跳过坏条目。 */
function normalizePreferences(data: Record<string, unknown>, salvage: boolean) {
  const issues: string[] = []
  const version = data.schemaVersion
  if (typeof version === 'number' && Number.isInteger(version) && version > playbackSchemaVersion) {
    if (!salvage) throw new Error(damaged(`数据版本 ${version} 高于当前支持的 ${playbackSchemaVersion}，请先更新页面`))
    issues.push(`数据版本 ${version} 高于当前支持的 ${playbackSchemaVersion}`)
  } else if (version !== undefined && version !== playbackSchemaVersion) issues.push(`schemaVersion ${String(version)} 已升级到 ${playbackSchemaVersion}`)

  const playlists: Playlist[] = []
  if (!Array.isArray(data.playlists)) {
    if (!salvage) throw new Error(damaged('playlists 不是列表'))
    issues.push('playlists 不是列表，已按空列表处理')
  } else data.playlists.forEach((item, index) => {
    if (!isRecord(item)) {
      if (!salvage) throw new Error(damaged(`playlists[${index}] 不是对象`))
      issues.push(`playlists[${index}] 不是对象，已跳过`)
      return
    }
    playlists.push(normalizePlaylist(item, index, issues))
  })

  const seen = new Set<string>()
  for (const item of playlists) {
    if (seen.has(item.id)) {
      const id = newId()
      issues.push(`播放列表「${item.name}」的 id 重复，已改为 ${id}`)
      item.id = id
    }
    seen.add(item.id)
  }

  const favorites = readList(data.favorites, 'favorites', salvage, issues)
  const stored = readList(data.shownImages, 'shownImages', salvage, issues)
  const shownImages = trimShownImages(stored)
  if (shownImages.length !== stored.length) issues.push(`已展示记录超出 ${shownImagesLimit} 条上限，已淘汰最早的 ${stored.length - shownImages.length} 条`)

  const requested = typeof data.selected === 'string' ? data.selected : ''
  const selected = playlists.some(item => item.id === requested) ? requested : playlists[0]?.id ?? ''
  if (data.selected !== undefined && selected !== data.selected) issues.push('selected 指向的播放列表不存在，已改为列表中的第一项')

  return { preferences: { schemaVersion: playbackSchemaVersion, playlists, selected, favorites, shownImages }, issues }
}

function parseStored(value: string): Record<string, unknown> {
  let data: unknown
  try { data = JSON.parse(value) } catch (error) { throw new Error(damaged(`内容不是有效的 JSON（${(error as Error).message}）`)) }
  if (!isRecord(data)) throw new Error(damaged('顶层不是对象'))
  return data
}

/** 读取本机存储：旧版本按字段补默认值并升级为当前版本，返回的对象带 schemaVersion = 3。 */
export function readPreferences(value: string): PlaybackPreferences {
  return normalizePreferences(parseStored(value), false).preferences
}

/** 救数据的出口：不抛错，尽量保留仍可解析的播放列表、喜欢与已展示记录，并列出改动。 */
export function recoverPreferences(value: string) {
  try {
    return normalizePreferences(parseStored(value), true)
  } catch (error) {
    return { preferences: emptyPreferences(), issues: [(error as Error).message] }
  }
}

function numberIn(value: unknown, min: number, max: number) { return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value) && value >= min && value <= max }
function knownStrings(value: unknown, known: Set<string>, min = 0) {
  return Array.isArray(value) && value.length >= min && value.every(item => typeof item === 'string' && known.has(item))
}
function validCommands(value: unknown) {
  return Array.isArray(value) && value.length <= customCommandLimit && value.every(item => {
    if (!isRecord(item)) return false
    const text = typeof item.text === 'string' ? item.text.trim() : ''
    return text.length >= 1 && text.length <= customCommandTextLimit && typeof item.type === 'string' && commandTypeSet.has(item.type)
  })
}
export function validPlaylist(item: Playlist) {
  return item && typeof item.id === 'string' && typeof item.name === 'string' && !!item.name.trim() && item.name.length <= 80
    && strings(item.roots) && kinds.includes(item.kind) && orders.includes(item.order)
    && numberIn(item.imageSeconds, ...ranges.imageSeconds) && numberIn(item.minutes, ...ranges.minutes) && numberIn(item.bpm, ...ranges.bpm)
    && timings.includes(item.imageTiming) && numberIn(item.imageCount, ...ranges.imageCount)
    && numberIn(item.mediaVolume, ...ranges.mediaVolume) && numberIn(item.beatVolume, ...ranges.beatVolume) && numberIn(item.speechVolume, ...ranges.speechVolume)
    && speechRates.includes(item.speechRate) && typeof item.hideTime === 'boolean' && numberIn(item.brightness, ...ranges.brightness)
    && typeof item.loop === 'boolean' && typeof item.metronome === 'boolean' && typeof item.speech === 'boolean' && typeof item.favoritesOnly === 'boolean'
    // 三相位比例：各自 0–100 的整数，且合计必须正好是 100。
    && difficulties.includes(item.difficulty)
    && numberIn(item.ratioFast, ...ranges.ratio) && numberIn(item.ratioSlow, ...ranges.ratio) && numberIn(item.ratioRest, ...ranges.ratio)
    && item.ratioFast + item.ratioSlow + item.ratioRest === 100
    && numberIn(item.permitBase, ...ranges.permitBase) && endings.includes(item.ending) && numberIn(item.edgeWindow, ...ranges.edgeWindow)
    && waitModes.includes(item.waitMode) && waitPresetOptions.includes(item.waitPreset)
    && numberIn(item.waitMin, ...ranges.wait) && numberIn(item.waitMax, ...ranges.wait) && item.waitMin <= item.waitMax
    && instructionPaces.includes(item.instructionPace)
    && knownStrings(item.tones, toneSet, 1) && hands.includes(item.hand)
    && knownStrings(item.commandTypes, commandTypeSet, 1) && knownStrings(item.props, propSet)
    && validCommands(item.customCommands)
    && Array.isArray(item.disabledCommands) && item.disabledCommands.every(id => typeof id === 'string' && builtinCommandId.test(id))
    && typeof item.heartbeat === 'boolean' && numberIn(item.heartbeatVolume, ...ranges.heartbeatVolume)
    && vibrateModes.includes(item.vibrate) && voicePitches.includes(item.voicePitch)
}
function strings(value: unknown): value is string[] { return Array.isArray(value) && value.every(item => typeof item === 'string') }

export function mediaUrl(item: PlaybackMedia) {
  return `/api/playback/media?${new URLSearchParams({ root: item.root, path: item.path, version: item.version })}`
}
export function mediaKey(item: PlaybackMedia) { return JSON.stringify([item.root, item.path]) }
export function imageKey(item: PlaybackMedia) { return item.identity || mediaKey(item) }
export function clockTime(milliseconds: number) {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000))
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`
}
export function nextBeatTime(previous: number, now: number, bpm: number) {
  const interval = 60000 / bpm
  const next = previous + interval
  return previous > 0 && next > now ? next : now + interval
}
export function orderedMedia(items: PlaybackMedia[], order: Playlist['order']) {
  // shortcut: streamed playback shuffles arriving batches; use a shared inventory index if uniform whole-library sampling is required.
  const result = items.slice()
  if (order === 'shuffle') for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[result[i], result[j]] = [result[j]!, result[i]!]
  }
  return result
}

export function playbackCycle(items: PlaybackMedia[], options: Playlist, shownImages: string[]) {
  const imageKeys = new Set(items.filter(item => item.kind === 'image').map(imageKey))
  const shown = new Set(shownImages)
  const available = [...imageKeys].filter(key => !shown.has(key)).length
  const count = Math.min(options.imageCount || available || imageKeys.size, imageKeys.size)
  const reset = available < count
  let selected = 0
  const queue = orderedMedia(items.filter(item => item.kind !== 'image' || reset || !shown.has(imageKey(item))), options.order)
    .filter(item => item.kind !== 'image' || selected++ < count)
  return { queue, shownImages: trimShownImages(reset ? shownImages.filter(key => !imageKeys.has(key)) : shownImages), reset }
}

export function exportConfiguration(playlists: Playlist[], selected: string) {
  return JSON.stringify({ format: playbackConfigFormat, schemaVersion: playbackSchemaVersion, selected, playlists: playlists.map(item => ({ ...item, roots: [] })) }, null, 2)
}

export function importConfiguration(value: string) {
  let data: unknown
  try { data = JSON.parse(value) } catch { throw new Error('请选择拾存导出的播放配置 JSON 文件。') }
  const config = isRecord(data) ? data : null
  const format = config?.format
  if (!config || typeof format !== 'string' || (format !== playbackConfigFormat && !legacyPlaybackConfigFormats.includes(format))
    || !Array.isArray(config.playlists) || !config.playlists.length || !config.playlists.every(isRecord)) throw new Error('请选择拾存导出的播放配置 JSON 文件。')
  const playlists = config.playlists.filter(isRecord).map(item => ({ ...item, roots: [] }))
  return normalizePreferences({ playlists, selected: config.selected, favorites: [], shownImages: [] }, false).preferences
}
