<script setup lang="ts">
// 寸止播放器：设置 → 播放 → 结算三段。
// 播放层的视觉与交互对齐参考实现（模式光晕、中央指令、任务条、忍住了、射了、底栏图例）。
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { api } from './api'
import Icon from './Icon.vue'
import PlaybackSettings from './PlaybackSettings.vue'
import PlaybackBottom from './playback/PlaybackBottom.vue'
import PlaybackFinished from './playback/PlaybackFinished.vue'
import PlaybackReward from './playback/PlaybackReward.vue'
import PlaybackGuide from './playback/PlaybackGuide.vue'
import PlaybackOverlay from './playback/PlaybackOverlay.vue'
import PlaybackStage from './playback/PlaybackStage.vue'
import PlaybackTopBar from './playback/PlaybackTopBar.vue'
import PlaybackVolumePopover from './playback/PlaybackVolumePopover.vue'
import { guideSteps, markGuideSeen, readGuideSeen } from './playback/guideSteps'
import type { FinishReason } from './playback/types'
import { beatVolumeMax, formatClock, modeColors, modeColorsDark, modeLabels, textOpacityMin, textScaleMin } from './playback/engine'
import { glansCommands, nippleCommands } from './playback/commands'
import { EdgeSession, type SessionFrame } from './playback/session'
import { edgeStorageKey, readEdgeSettings, writeEdgeSettings, type EdgeSettings } from './playback/settings'
import { addLost, addSession, lostPct, lostStorageKey, readLost, readStats, statsStorageKey, writeLost, writeStats, type LostRecord } from './playback/history'
import { addDay, daysStorageKey, readDays, writeDays, type EdgeDays } from './playback/days'
import {
  countResult, pushRecord, readRecords, readTally, recordOutcome, recordsStorageKey, tallyStorageKey, writeRecords, writeTally,
  type ResultRecord
} from './playback/records'
import {
  MIRROR_CONSTRAINTS, classifyMirrorError, mirrorErrorLabels, mirrorPlaceFor, mirrorSupport, mirrorText, stopStream,
  type MirrorError
} from './playback/mirror'
import { SoundEngine, applyAudioSession } from './playback/sound'
import { loadPlaybackQueue, PlaybackImageBuffer } from './playbackLoader'
import {
  clockTime, exportConfiguration, imageKey, importConfiguration, mediaKey, mediaUrl, newPlaylist, orderedMedia,
  playbackCycle, playbackStorageKey, readPreferences, trimShownImages, validPlaylist,
  type Gallery, type PlaybackMedia, type PlaybackPreferences, type Playlist,
} from './playback'

const preferences = reactive<PlaybackPreferences>({ playlists: [], selected: '', favorites: [], shownImages: [] })
const setupModel = reactive({ galleries: [] as Gallery[], loading: false, starting: false, error: '', storageError: '', storageBlocked: false, ready: false })
const settings = ref<EdgeSettings>(readEdgeSettings(null) ?? readEdgeSettings(null) as EdgeSettings)
const playlist = computed(() => preferences.playlists.find(item => item.id === preferences.selected))
const queue = shallowRef<PlaybackMedia[]>([])
const options = ref<Playlist>()
const session = shallowRef<EdgeSession | null>(null)
const frame = ref<SessionFrame | null>(null)
const screen = ref<'setup' | 'playing' | 'finished'>('setup')
const paused = ref(false)
const ready = ref(false)
const error = ref('')
const note = ref('')
const finishedReason = ref<FinishReason>('manual')
const round = ref(1)
const held = ref(0)
const zoomLevel = ref(1)
const fullscreenOn = ref(false)
/** 铺法跟随设置：cover=铺满屏幕，contain=显示完整画面。 */
const noCrop = computed(() => settings.value.fit === 'contain')
function toggleCrop() { settings.value.fit = settings.value.fit === 'contain' ? 'cover' : 'contain' }
/** contain 时的画面位置（上/中/下）。 */
function cyclePosition() {
  const order: Array<'top' | 'center' | 'bottom'> = ['center', 'top', 'bottom']
  settings.value.pos = order[(order.indexOf(settings.value.pos) + 1) % order.length] ?? 'center'
}
const volumeOpen = ref(false)
const landscapeAvailable = ref(false)
const guideOpen = ref(false)
const pendingStart = ref(false)
const runtimeSettings = ref(false)
const settingsError = ref('')
const imageElapsed = ref(0)
const imageSeconds = ref(8)
const imageSource = ref('')
const queueLoading = ref(false)
const queueError = ref('')
const importInput = ref<HTMLInputElement>()
const settingsButton = ref<HTMLButtonElement>()
const runtimePanel = ref<HTMLElement>()
const playerElement = ref<HTMLElement>()
const imageViewport = ref<HTMLElement>()
const video = ref<HTMLVideoElement>()

const imageBuffer = new PlaybackImageBuffer()
const sound = new SoundEngine()
let request = new AbortController()
let queueRequest = new AbortController()
let timer: ReturnType<typeof setInterval>
let previousTick = 0
let nextBeat = 0
let nextHeart = 0
let disposed = false
let pendingAdvance = false
let imageLoad = 0
let availableMedia: PlaybackMedia[] = []
let immersive = false
let pointer: { id: number; x: number; y: number; left: number; top: number; moved: boolean } | undefined
let suppressClick = false
let lastMode = ''
let lastTask = -1
let statsDone = false
/** 中途结束（射了）的记录：次数与最长坚持，只存本机。 */
const lostRecord = ref<LostRecord>({ count: 0, bestMs: 0 })
/** 连续天数：设置页顶部要显示「已连续 N 天」，这里读一次供外部查看。 */
const days = ref<EdgeDays>(readDays(typeof localStorage === 'undefined' ? null : localStorage.getItem(daysStorageKey)))
const lostBestNow = ref(false)
/** 红色（不许碰）时由我们主动暂停视频，避免被 videoPaused 当成用户暂停整局。 */
let videoHold = false
/** Document PiP 小窗句柄（关掉后置空）。 */
let pipWindow: Window | null = null

const current = computed(() => queue.value[0] ?? null)
const favorite = computed(() => !!current.value && preferences.favorites.includes(mediaKey(current.value)))
const active = computed(() => screen.value === 'playing' && !paused.value && ready.value && !error.value)
/** 悬浮小窗能力：优先用 Document PiP 放我们自己画的迷你播放器，否则退回视频自身的 PiP。 */
type PipMode = 'doc' | 'video' | null
function detectPip(): PipMode {
  try {
    if ('documentPictureInPicture' in window) return 'doc'
    const proto = HTMLVideoElement.prototype as HTMLVideoElement & { webkitSetPresentationMode?: unknown }
    const ok = (document.pictureInPictureEnabled && 'requestPictureInPicture' in proto) || 'webkitSetPresentationMode' in proto
    return ok ? 'video' : null
  } catch { return null }
}
const pipMode = computed<PipMode>(() => (current.value?.kind === 'video' ? detectPip() : null))
const pipAvailable = computed(() => pipMode.value !== null)
/** 开始后提示打开悬浮小窗（参考站的 pip-want）。 */
const pipOfferOpen = ref(false)
const pipOfferDone = ref(false)
const pipSiteLabel = computed(() => {
  const site = settings.value.pipSite
  if (!site) return ''
  try { return new URL(site).host || site } catch { return site }
})
const mode = computed(() => frame.value?.mode ?? 'stop')
const commandText = computed(() => frame.value?.text ?? '')
const commandHint = computed(() => frame.value?.hint ?? '')
const beatBpm = computed(() => frame.value?.task?.command?.bpm ?? 0)
/** 图片「按 BPM · 每拍一张」：慢速取快速节拍的 60%，红色（不许碰）不切图。 */
const imageBeatMode = computed(() => options.value?.kind === 'image' && options.value.imageTiming === 'beat')
const imageBeatBpm = computed(() => {
  const base = options.value?.bpm || 100
  return mode.value === 'slow' ? Math.max(20, Math.round(base * 0.6)) : base
})
const taskProgress = computed(() => frame.value?.taskProgress ?? 0)
const taskSeconds = computed(() => frame.value?.taskSeconds ?? 0)
const taskKey = computed(() => frame.value?.task?.index ?? -1)
const cooling = computed(() => frame.value?.cooling ?? false)
const taskCategory = computed(() => {
  if (cooling.value) return 'basic'
  return frame.value?.task?.command?.category ?? 'basic'
})
const allowed = computed(() => frame.value?.phase === 'allow')
const windowLeft = computed(() => Math.max(0, Math.ceil(frame.value?.windowLeft ?? 0)))
const totalMs = computed(() => frame.value?.totalMs ?? 0)
const elapsedMs = computed(() => frame.value?.elapsed ?? 0)
const progressPercent = computed(() => (totalMs.value ? Math.min(1, elapsedMs.value / totalMs.value) : 0))
// 随机时长结束前不让人知道有多久，所以这种情况下也一并藏起剩余时间。
const hideClock = computed(() => settings.value.hideRemaining || settings.value.durationRandom)
const remainingText = computed(() => (hideClock.value ? '' : formatClock(Math.max(0, totalMs.value - elapsedMs.value))))
const summary = computed(() => {
  const item = playlist.value
  if (!item) return ''
  return [({ mixed: '混合', image: '仅图片', video: '仅视频' } as const)[item.kind], item.order === 'shuffle' ? '随机顺序' : '文件名顺序',
    item.kind === 'video' ? '' : item.kind === 'image' && item.imageTiming === 'beat' ? `每拍一张 · 快速 ${item.bpm} BPM` : `每张 ${item.imageSeconds} 秒`,
    item.kind === 'video' ? '' : item.imageCount ? `每轮 ${item.imageCount} 张` : '全部未展示图片',
    settings.value.durationRandom ? '随机时长' : `${settings.value.minutes} 分钟`, settings.value.metronome ? '节拍声开' : '节拍声关'].filter(Boolean).join(' · ')
})
const canHold = computed(() => screen.value === 'playing' && !paused.value && !error.value && !allowed.value && !runtimeSettings.value && !cooling.value)

/** 结算屏用的两个数：撑过设定时间的百分比、走过多少条指令。 */
const finishedPercent = computed(() => (totalMs.value > 0 ? Math.min(100, Math.round((elapsedMs.value / totalMs.value) * 100)) : 0))
const commandCount = computed(() => (frame.value?.task ? frame.value.task.index + 1 : 0))
/** 许可窗口总长（秒），用于奖励屏倒计时条。 */
const windowTotal = computed(() => {
  if (frame.value?.multi) return Math.max(1, Math.round(frame.value.windowTotal || 0))
  return Math.max(1, Math.round(session.value?.settings.rewardSeconds ?? settings.value.rewardSeconds))
})
/** 连续（多少次都行）结局：奖励屏换成多轮文案。 */
const multi = computed(() => Boolean(frame.value?.multi) && allowed.value)
/** 连续结局现在播到第几次「再来一次」。 */
const multiRound = computed(() => Math.max(1, Math.round(frame.value?.multiRound ?? 1)))
/** 只玩乳头且拿到许可时，奖励屏下方多一句「现在可以摸下面了」。 */
const allowBelow = computed(() => session.value?.allowBelow ?? '')
/** 这次许可是不是「松手射精」。 */
const ruined = computed(() => session.value?.ruined ?? finishedReason.value === 'ruin')
/** 这一局是不是连续（多少次都行）结局——结算屏在成功时换成多轮正文。 */
const finishedMulti = computed(() => settings.value.finale === 'continuous')

const textOpacity = computed(() => settings.value.textOpacity)
const textScale = computed(() => settings.value.textScale)
/** 红色（不许碰）且没开「红色也播放视频」时，画面额外压暗一档（参考站行为）。 */
const videoDimmed = computed(() => {
  if (allowed.value) return false
  // 按“忍住了”之后的等待时间：参考站默认也继续播放（playInCooldown）。
  if (cooling.value) return !settings.value.keepVideoWhileCooling
  return mode.value === 'stop' && !settings.value.keepVideoOnStop
})
/**
 * 播放层遮罩浓度：对齐参考站的 `dim`（越大越暗，0 完全透明）。
 * 红色暂停时参考站不改遮罩浓度，只把视频本体透明度降到 `1 - 0.2 * dim`，所以这里不再乘系数。
 */
const dimLevel = computed(() => Math.min(100, Math.max(0, settings.value.dim)))
/** 视频本体透明度：参考站 play 态 `1 - 0.2 * dim`，拿到许可时恢复 1。 */
const mediaOpacity = computed(() => (allowed.value ? 1 : 1 - 0.2 * (dimLevel.value / 100)))

/** 相位切到红色/离开红色时同步视频：关掉「红色也播放」就暂停并压暗，绿黄恢复播放。 */
function syncVideoPhase() {
  if (screen.value !== 'playing') return
  const element = video.value
  if (!element) return
  if (videoDimmed.value) {
    if (!element.paused) { videoHold = true; element.pause() }
    return
  }
  if (videoHold) { videoHold = false; if (!paused.value && !error.value && !runtimeSettings.value) void playVideo() }
}

/** 十六进制转 rgba：把 modeColors 的色值喂给光晕与进度条。 */
function beatIntervalFor(bpm: number) { return bpm > 0 ? 60000 / bpm : 0 }

function persistEdge() {
  const problem = writeEdgeSettings(settings.value)
  if (problem) setupModel.storageError = problem
}
watch(settings, persistEdge, { deep: true })

/** 换一条指令就换一个视频（参考站的可选项）。只在当前播放的是视频时生效。 */
function maybeSwitchVideo(previous: number, next: number) {
  if (!settings.value.switchVideoPerCommand) return
  if (previous < 0 || next <= previous) return
  if (screen.value !== 'playing' || paused.value || error.value || runtimeSettings.value || allowed.value) return
  if (current.value?.kind !== 'video') return
  step(1)
}
watch([mode, allowed, cooling], syncVideoPhase)

/** 视频声音：关 / 只在最后（获得许可时）/ 一直开。 */
const videoMuted = computed(() => {
  const choice = settings.value.videoSound
  if (choice === 'off') return true
  if (choice === 'end') return !allowed.value
  return false
})
const videoLevel = computed(() => Math.min(1, Math.max(0, settings.value.mediaVolume / 100)))

function syncVideoSound() {
  const element = video.value
  if (!element) return
  element.muted = videoMuted.value
  element.volume = videoLevel.value
}

function videoLoaded(event: Event) {
  if (event.currentTarget !== video.value) return
  const element = video.value
  if (!element) return
  /* 对齐参考站：长视频直接从正文开始；开了「从中间开始」再往后跳一截。 */
  if (Number.isFinite(element.duration) && element.duration > 25 && element.currentTime < 1) {
    const target = settings.value.skipIntro && element.duration > 40
      ? element.duration * (0.3 + 0.2 * Math.random())
      : Math.min(12, 0.15 * element.duration)
    try { element.currentTime = target } catch { /* 部分格式不允许跳转，忽略 */ }
  }
  syncVideoSound()
  void playVideo()
}

/* ---- 镜子：前置摄像头左右翻转。画面只在本机使用，暂停 / 结束 / 离开页面就关掉 ---- */
const mirrorStream = shallowRef<MediaStream | null>(null)
const mirrorError = ref<MirrorError | null>(null)
const mirrorVideo = ref<HTMLVideoElement>()
/** 播放视频时镜子固定收到右下角，避免挡住画面。 */
const mirrorPlace = computed(() => mirrorPlaceFor(settings.value.mirror.place, current.value?.kind === 'video'))
const mirrorVisible = computed(() => settings.value.mirror.on && screen.value === 'playing' && !paused.value && !mirrorError.value)
/** 铺满背景时叠一层模式色遮罩（参考站用暗色变体，浓度跟随变暗设置）。 */
const mirrorDim = computed(() => {
  const level = Math.min(100, Math.max(0, dimLevel.value))
  const alpha = Math.min(0.45, (0.45 * level) / 100)
  return rgbaOf(modeColorsDark[mode.value], alpha)
})

function rgbaOf(hex: string, alpha: number) {
  const value = hex.replace('#', '')
  const full = value.length === 3 ? value.split('').map(char => char + char).join('') : value
  const r = parseInt(full.slice(0, 2), 16)
  const g = parseInt(full.slice(2, 4), 16)
  const b = parseInt(full.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`
}

function attachMirror() {
  const element = mirrorVideo.value
  const stream = mirrorStream.value
  if (!element || !stream) return
  if (element.srcObject !== stream) element.srcObject = stream
  const playback = element.play?.()
  if (playback && typeof playback.catch === 'function') playback.catch(() => {})
}

function stopMirror() {
  stopStream(mirrorStream.value)
  mirrorStream.value = null
  const element = mirrorVideo.value
  if (element) element.srcObject = null
}

function failMirror(reason: MirrorError) {
  mirrorError.value = reason
  stopMirror()
  settings.value.mirror.on = false
  note.value = mirrorErrorLabels[reason]
}

async function startMirror() {
  if (mirrorStream.value) return
  const problem = mirrorSupport()
  if (problem) { failMirror(problem); return }
  try {
    const stream = await navigator.mediaDevices.getUserMedia(MIRROR_CONSTRAINTS)
    // 期间可能被关掉（或整局结束），拿到流先检查再挂上
    if (!settings.value.mirror.on || screen.value !== 'playing') { stopStream(stream); return }
    mirrorStream.value = stream
    mirrorError.value = null
    await nextTick()
    attachMirror()
  } catch (error) {
    failMirror(classifyMirrorError(error))
  }
}

watch(mirrorVisible, visible => {
  if (visible) void startMirror()
  else stopMirror()
})

/* ---- 双击 / 连点快进：视频右半快进、左半后退，700ms 内同侧累加 ---- */
const seekFlash = ref<{ side: number; total: number; x: number; y: number; key: number } | null>(null)
let tapPoint: { time: number; x: number; y: number; side: number } | null = null
let seekChain: { side: number; until: number; total: number } | null = null
let seekTimer = 0

function showSeekFlash(side: number, total: number) {
  const rect = video.value?.getBoundingClientRect()
  const known = !!rect && rect.width > 0
  const x = known ? rect.left + rect.width * (side > 0 ? 0.75 : 0.25) : window.innerWidth * (side > 0 ? 0.75 : 0.25)
  const tall = known && rect.height > window.innerHeight * 0.6
  const y = known ? rect.top + rect.height * (tall ? 0.15 : 0.5) : window.innerHeight * 0.15
  seekFlash.value = { side, total, x, y, key: Date.now() }
  window.clearTimeout(seekTimer)
  seekTimer = window.setTimeout(() => { seekFlash.value = null }, 850)
}

function seekBy(seconds: number) {
  const element = video.value
  if (!element || !Number.isFinite(element.duration) || element.duration <= 0) return
  const next = element.currentTime + seconds
  try { element.currentTime = Math.min(Math.max(0, next), Math.max(0, element.duration - 0.25)) } catch { /* 忽略 */ }
}

function seekStep(side: 1 | -1) {
  const now = performance.now()
  const total = seekChain && seekChain.side === side && now < seekChain.until ? seekChain.total + 10 : 10
  seekChain = { side, until: now + 700, total }
  seekBy(side * 10)
  showSeekFlash(side, total)
}

function tapSeek(event: PointerEvent) {
  if (event.pointerType === 'mouse' && event.button !== 0) return
  const target = event.target as HTMLElement | null
  if (target?.closest('button,a,input,select,textarea,label,summary,[role="button"],[role="slider"],[role="radio"],[data-sundome-no-seek]')) {
    tapPoint = null
    return
  }
  const rect = video.value?.getBoundingClientRect()
  if (!rect || rect.width === 0 || event.clientX < rect.left || event.clientX > rect.right
    || event.clientY < rect.top || event.clientY > rect.bottom) {
    tapPoint = null
    return
  }
  const side = event.clientX < rect.left + rect.width / 2 ? -1 : 1
  const now = performance.now()
  if (seekChain && now < seekChain.until && seekChain.side === side) {
    seekChain.total += 10
    seekChain.until = now + 700
    seekBy(side * 10)
    showSeekFlash(side, seekChain.total)
    return
  }
  const previous = tapPoint
  if (previous && now - previous.time < 320 && previous.side === side
    && Math.hypot(event.clientX - previous.x, event.clientY - previous.y) < 48) {
    tapPoint = null
    seekChain = { side, until: now + 700, total: 10 }
    seekBy(side * 10)
    showSeekFlash(side, 10)
    return
  }
  seekChain = null
  tapPoint = { time: now, x: event.clientX, y: event.clientY, side }
}

watch([videoMuted, videoLevel], syncVideoSound)
watch(taskKey, maybeSwitchVideo)
// 「边听音乐边玩」是 iPhone 才有的行为：设 ambient 时不会打断别的 App 的音乐。
watch([() => settings.value.mixAudio, () => settings.value.metronome, () => settings.value.heartbeat], ([mix, beat, heart]) => {
  if (screen.value !== 'playing') return
  applyAudioSession(mix, beat || heart)
})

const scheduleEdge = ref<EdgeSettings>()
watch(() => playlist.value?.id, () => { /* 保留列表选择 */ })

function warmImages() {
  if (screen.value !== 'playing') return
  const items = queue.value.filter(item => item.kind === 'image').slice(0, 20)
  void imageBuffer.fill(items)
}
async function loadCurrentImage() {
  const item = current.value, version = ++imageLoad
  imageSource.value = ''
  if (item?.kind !== 'image' || screen.value !== 'playing') return
  ready.value = false
  try {
    const url = await imageBuffer.show(item)
    if (version !== imageLoad || disposed || screen.value !== 'playing') return
    imageSource.value = url; warmImages()
  } catch (problem) {
    if (version !== imageLoad || disposed || (problem as Error).name === 'AbortError') return
    pause(); error.value = (problem as Error).message
  }
}

function persist() {
  if (!setupModel.ready || setupModel.storageBlocked) return
  if (!preferences.playlists.every(validPlaylist)) {
    setupModel.storageError = '播放列表有尚未填完的名称或设置，修正后会自动保存。'; return
  }
  try { localStorage.setItem(playbackStorageKey, JSON.stringify(preferences)); setupModel.storageError = '' }
  catch { setupModel.storageError = '无法保存到本机，请检查浏览器存储空间或隐私设置；当前编辑仍可用于播放。' }
}
watch(preferences, persist, { deep: true })

function restoreDefaults() {
  if (!playlist.value || !confirm('恢复当前列表的播放参数？名称、图库、喜欢和已展示记录会保留。')) return
  const { id, name, roots } = playlist.value
  Object.assign(playlist.value, newPlaylist(), { id, name, roots })
}
function downloadConfiguration() {
  if (!preferences.playlists.every(validPlaylist)) { setupModel.error = '请先修正播放列表中未填完的设置，再导出。'; return }
  const url = URL.createObjectURL(new Blob([exportConfiguration(preferences.playlists, preferences.selected)], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url; link.download = 'shicun-playback.json'; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function uploadConfiguration(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file) return
  setupModel.error = ''
  try {
    if (file.size > 2 * 1024 * 1024) throw new Error('播放配置文件不能超过 2 MB。')
    const result = importConfiguration(await file.text())
    if (!confirm(`导入 ${result.playlists.length} 个播放列表并替换当前列表？图库需重新选择，喜欢和已展示记录会保留。`)) return
    preferences.playlists = result.playlists; preferences.selected = result.selected
  } catch (problem) { setupModel.error = `导入失败：${(problem as Error).message}` }
  finally { input.value = '' }
}
async function openSettings() {
  pause(); runtimeSettings.value = true; settingsError.value = ''
  await nextTick(); runtimePanel.value?.focus()
}
function closeSettings() {
  runtimeSettings.value = false; settingsButton.value?.focus()
  previousTick = performance.now()
}
function createPlaylist() {
  const item = newPlaylist()
  item.name = `播放列表 ${preferences.playlists.length + 1}`
  preferences.playlists.push(item); preferences.selected = item.id
}
function deletePlaylist() {
  if (!playlist.value || !confirm(`删除播放列表“${playlist.value.name}”？图库原文件会保留。`)) return
  preferences.playlists = preferences.playlists.filter(item => item.id !== preferences.selected)
  preferences.selected = preferences.playlists[0]?.id || ''
}
function resetPreferences() {
  if (!confirm('重置本机的播放列表、设置和喜欢收藏？图库原文件会保留。')) return
  setupModel.storageBlocked = false
  preferences.playlists = []; preferences.selected = ''; preferences.favorites = []; preferences.shownImages = []
  createPlaylist(); persist()
}
async function loadGalleries() {
  setupModel.loading = true; setupModel.error = ''
  try {
    const result = await api<{ items: Gallery[] }>('/playback/galleries', undefined, 'GET', request.signal)
    setupModel.galleries = result.items
  } catch (problem) { if (!disposed) setupModel.error = (problem as Error).message }
  finally { if (!disposed) setupModel.loading = false }
}
function galleryName(gallery: Gallery) {
  return gallery.id === 'downloads' ? '下载图库' : gallery.path.split(/[\\/]/).filter(Boolean).pop() || gallery.path
}
function checkGallery(id: string, checked: boolean) {
  if (!playlist.value) return
  playlist.value.roots = checked ? [...playlist.value.roots, id] : playlist.value.roots.filter(root => root !== id)
}

async function start() {
  if (!playlist.value || setupModel.starting) return
  if (!readGuideSeen() && !pendingStart.value) { pendingStart.value = true; guideOpen.value = true; return }
  setupModel.error = ''
  const item = playlist.value
  if (!item.roots.length) { setupModel.error = '请至少勾选一个图库。'; return }
  if (!validPlaylist(item)) { setupModel.error = '请填写列表名称，并检查图片间隔（1–300 秒）、快速节拍（20–300 BPM）等数值是否合法。'; return }
  setupModel.starting = true
  queueRequest.abort(); queueRequest = new AbortController()
  const signal = queueRequest.signal
  queueLoading.value = true; queueError.value = ''; pendingAdvance = false
  availableMedia = []; imageBuffer.clear(); note.value = ''
  options.value = { ...item, roots: item.roots.slice() }
  imageSeconds.value = item.imageSeconds
  applyAudioSession(settings.value.mixAudio, settings.value.metronome || settings.value.heartbeat)
  void sound.ensure()
  try {
    await loadPlaybackQueue(options.value, signal, async (batch, done) => {
      if (disposed || signal.aborted) return
      const items = item.favoritesOnly ? batch.filter(media => preferences.favorites.includes(mediaKey(media))) : batch
      availableMedia.push(...items)
      queueLoading.value = !done
      if (screen.value === 'setup') {
        if (!availableMedia.length) {
          if (done) setupModel.error = item.favoritesOnly ? '所选图库中没有符合类型的喜欢收藏，可关闭“仅播放喜欢”。' : '所选图库中没有符合类型的媒体，请调整图库或媒体类型。'
          return
        }
        const cycle = playbackCycle(availableMedia, item, preferences.shownImages)
        if (!done && (cycle.reset || cycle.queue.length < Math.min(20, item.imageCount || 20))) return
        queue.value = cycle.queue; preferences.shownImages = cycle.shownImages
        runtimeSettings.value = false
        if (cycle.reset) note.value = '未展示图片不足一轮，已开始新的图片周期。'
        beginSession()
      } else if (screen.value === 'playing') {
        const added = orderedMedia(items.filter(media => media.kind !== 'image' || !preferences.shownImages.includes(imageKey(media))), item.order)
        if (added.length) queue.value = [...queue.value, ...added]
      }
      advancePending()
    })
  } catch (problem) {
    if (!disposed && !signal.aborted) {
      if (screen.value === 'setup') setupModel.error = (problem as Error).message
      else { queueError.value = '媒体清单读取中断，请返回列表重新开始。'; pause(); error.value = queueError.value }
    }
  } finally { if (!disposed && signal === queueRequest.signal) { setupModel.starting = false; queueLoading.value = false } }
}

function beginSession() {
  const instance = new EdgeSession(settings.value, { nipple: nippleCommands, glans: glansCommands })
  session.value = instance
  frame.value = instance.frame()
  screen.value = 'playing'
  paused.value = document.hidden
  ready.value = false
  error.value = ''
  round.value = 1
  held.value = 0
  zoomLevel.value = 1
  imageElapsed.value = 0
  lastMode = frame.value.mode
  lastTask = frame.value.task?.index ?? -1
  statsDone = false
  previousTick = performance.now()
  nextBeat = 0
  void nextTick(() => {
    playerElement.value?.focus()
    void loadCurrentImage()
    void playVideo()
    if (settings.value.pipOffer && pipMode.value) {
      pipOfferOpen.value = true
      pipOfferDone.value = false
    }
  })
}

function pause() {
  if (screen.value !== 'playing') return
  paused.value = true; video.value?.pause()
  nextBeat = 0
}
async function resume() {
  if (screen.value !== 'playing' || error.value || runtimeSettings.value) return
  paused.value = false; note.value = ''; previousTick = performance.now()
  advancePending()
  await sound.ensure()
  if (current.value?.kind === 'video') await playVideo()
}
async function playVideo() {
  const element = video.value
  if (!element || screen.value !== 'playing' || paused.value || error.value) return
  try { await element.play() }
  catch (problem) {
    if (disposed || element !== video.value || (problem as Error).name === 'AbortError') return
    pause(); note.value = '视频尚未开始，请点击继续播放；若仍无法播放，请检查浏览器支持的格式。'
  }
}

function finish(reason: FinishReason) {
  queueRequest.abort(); queueLoading.value = false; pendingAdvance = false
  imageLoad++; imageBuffer.clear()
  stopMirror()
  pause()
  buzz([60, 40, 60, 40, 120], 'finish')
  recordStats(reason)
  recordDay()
  recordResult(reason)
  finishedReason.value = reason
  screen.value = 'finished'
  error.value = ''
  sound.suspend()
}

/** 结算时把这一局记进本机成绩：参考站只统计成功、松手、禁止三种结局。 */
function recordStats(reason: FinishReason) {
  if (statsDone) return
  statsDone = true
  const instance = session.value
  if (!instance) return
  let stored: string | null = null
  try { stored = localStorage.getItem(statsStorageKey) } catch { return }
  const next = addSession(readStats(stored), reason, instance.minutes, instance.held)
  writeStats(next)
  recordLost(reason)
}

/** 记一次今天玩过了：连续天数（参考站 sundome:days 的口径）。 */
function recordDay() {
  let stored: string | null = null
  try { stored = localStorage.getItem(daysStorageKey) } catch { return }
  const result = addDay(readDays(stored))
  writeDays(result.next)
  days.value = result.next
}

/** 「射了」单独记一档：中途结束次数与最长坚持（对齐参考站的 lost 存储）。 */
function recordLost(reason: FinishReason) {
  if (reason !== 'lost') return
  const instance = session.value
  if (!instance) return
  let stored: string | null = null
  try { stored = localStorage.getItem(lostStorageKey) } catch { return }
  const result = addLost(readLost(stored), instance.elapsed)
  writeLost(result.next)
  lostRecord.value = result.next
  lostBestNow.value = result.isBest
}
/**
 * 把这一局写进「历史成绩」：累计 +1，并插一条详细记录（最近 30 条）。
 * 结局映射与参考站一致：allow/duration→success、ruin→ruin、lost→lost，其余→fail。
 */
function recordResult(reason: FinishReason) {
  const instance = session.value
  if (!instance) return
  let storedTally: string | null = null
  let storedRecords: string | null = null
  try {
    storedTally = localStorage.getItem(tallyStorageKey)
    storedRecords = localStorage.getItem(recordsStorageKey)
  } catch { return }
  const counted = countResult(readTally(storedTally), reason)
  writeTally(counted.next)
  const record: ResultRecord = {
    t: Date.now(),
    o: recordOutcome(reason),
    m: instance.minutes,
    c: Math.max(0, commandCount.value),
    e: instance.held,
    d: settings.value.difficulty,
    n: counted.nth
  }
  if (reason === 'lost') record.ms = Math.max(0, Math.round(instance.elapsed))
  if (instance.extends > 0) record.x = instance.extends
  if (settings.value.tune.mix) record.k = true
  writeRecords(pushRecord(readRecords(storedRecords), record))
}

function advancePending() {
  if (!pendingAdvance || screen.value !== 'playing' || runtimeSettings.value
    || (queueLoading.value && queue.value.length <= 1)) return
  step(1)
}

function step(delta: number) {
  if (screen.value !== 'playing' || runtimeSettings.value) return
  if (pendingAdvance) note.value = ''
  if (!queue.value.length) return
  if (delta > 0) {
    if (queue.value.length > 1) {
      queue.value = queue.value.slice(1)
    } else if (queueLoading.value) { pendingAdvance = true; ready.value = false; note.value = '正在补充媒体列表，请稍候…'; return }
    else if (!options.value?.loop) { finish('queue'); return }
    else {
      const cycle = playbackCycle(availableMedia, options.value, preferences.shownImages)
      queue.value = cycle.queue; preferences.shownImages = cycle.shownImages
      if (cycle.reset) note.value = '未展示图片不足一轮，已开始新的图片周期。'
    }
  } else {
    if (!options.value?.loop) return
    const last = queue.value[queue.value.length - 1]
    if (last) queue.value = [...queue.value.slice(1), last]
  }
  pendingAdvance = false
  imageElapsed.value = 0; zoomLevel.value = 1; error.value = ''; ready.value = false
  void nextTick(() => {
    imageViewport.value?.scrollTo(0, 0)
    void loadCurrentImage()
    void playVideo()
  })
}

/** 忍住了：交给 session 记一次，并立刻切到「等它平息」。 */
/** 切换时振动：参考站在指令切换、按「忍住了」、结局三处振动。 */
function buzz(pattern: number | number[], kind: 'command' | 'edge' | 'finish') {
  if (!settings.value.vibrate || !settings.value.vibrateOn[kind]) return
  try { navigator.vibrate?.(pattern) } catch { /* 桌面浏览器不支持，忽略 */ }
}
function hold() {
  if (!canHold.value || !session.value) return
  session.value.hold()
  held.value = session.value.held
  frame.value = session.value.frame()
  note.value = ''
  nextBeat = 0
  buzz([40, 30, 40], 'edge')
  if (settings.value.metronome) void sound.cue({ beatVolume: settings.value.beatVolume, heartbeatVolume: settings.value.heartbeatVolume })
}
function lose() {
  if (!session.value || screen.value !== 'playing') return
  session.value.lose()
  const outcome = session.value.outcome ?? 'lost'
  frame.value = session.value.frame()
  finish(outcome)
}

/** 节拍与心跳：go 880Hz、slow 520Hz、stop 按 redBeat 决定心跳还是节拍。 */
function pulse(now: number) {
  const frameValue = frame.value
  if (!frameValue || paused.value) return
  const currentMode = frameValue.mode
  if (currentMode !== lastMode) {
    lastMode = currentMode
    nextBeat = 0
    nextHeart = 0
  }
  const heartbeatOn = settings.value.heartbeat
  const redBeat = settings.value.redBeat
  const touching = frameValue.task?.command?.category === 'nipple'
  const reward = allowed.value
  const stopMode = currentMode === 'stop'
  const beatBpmValue = imageBeatMode.value && !stopMode ? imageBeatBpm.value : beatBpm.value || 0
  /* 参考站口径：红色带 BPM 且不是乳头指令时才算“红色的节拍”。 */
  const redWithBpm = stopMode && !touching && beatBpmValue > 0
  const heartbeatHere = heartbeatOn && (reward || (stopMode && !touching && (!redWithBpm || redBeat !== 'metronome')))
  const heartInterval = reward ? 630 : redWithBpm ? Math.round(60_000 / beatBpmValue) : 860
  const metronomeHere = beatBpmValue > 0 && !reward && !(redWithBpm && !(redBeat !== 'heartbeat' || !heartbeatOn))
  const volume = { beatVolume: settings.value.beatVolume, heartbeatVolume: settings.value.heartbeatVolume }
  if (heartbeatHere && heartInterval > 0) {
    if (!nextHeart) nextHeart = now + heartInterval
    else if (now >= nextHeart) { nextHeart = now + heartInterval; void sound.heartbeat(volume) }
  } else nextHeart = 0
  const beatInterval = beatIntervalFor(beatBpmValue)
  if (!metronomeHere || !beatInterval) { nextBeat = 0; return }
  if (!nextBeat) { nextBeat = now + beatInterval; return }
  if (now < nextBeat) return
  nextBeat = now + beatInterval
  if (imageBeatMode.value && !stopMode) step(1)
  // 「每拍一张」时即使关掉节拍器也要出声，否则图片不动。
  if (settings.value.metronome || imageBeatMode.value) void sound.beat(currentMode === 'slow' ? 'slow' : 'go', volume)
}

function tick() {
  const now = performance.now(), delta = now - previousTick
  previousTick = now
  if (screen.value !== 'playing' || !session.value) return
  if (paused.value) return
  session.value.tick(delta)
  frame.value = session.value.frame()
  held.value = session.value.held
  /* 参考站口径：每换一条指令振一次，「不许碰」更久。 */
  const tickTask = frame.value.task?.index ?? -1
  if (tickTask !== lastTask) {
    lastTask = tickTask
    if (tickTask >= 0 && !frame.value.cooling) buzz(frame.value.mode === 'stop' ? [90, 60, 90] : 40, 'command')
  }
  if (session.value.phase === 'done') {
    const outcome = session.value.outcome ?? 'manual'
    finish(outcome)
    return
  }
  pulse(now)
  if (pipWindow) renderPip()
  if (!imageBeatMode.value && current.value?.kind === 'image' && imageSeconds.value > 0) {
    imageElapsed.value += delta
    if (imageElapsed.value >= imageSeconds.value * 1000) step(1)
  }
}

function mediaFailed(event: Event) {
  if (event.currentTarget !== video.value && event.currentTarget !== imageViewport.value?.querySelector('img')) return
  pause(); ready.value = false
  error.value = '无法播放此文件，请检查文件是否仍在图库，以及浏览器是否支持此格式；文件有变化时请返回列表重新开始。'
}
function imageLoaded(event: Event) {
  const image = event.currentTarget
  if (image !== imageViewport.value?.querySelector('img')) return
  ready.value = true
  requestAnimationFrame(() => requestAnimationFrame(() => { if (image === imageViewport.value?.querySelector('img')) recordDisplayedImage() }))
}
function recordDisplayedImage() {
  if (document.hidden || runtimeSettings.value || screen.value !== 'playing' || !ready.value || error.value || current.value?.kind !== 'image') return
  const key = imageKey(current.value)
  if (!preferences.shownImages.includes(key)) preferences.shownImages = trimShownImages([...preferences.shownImages, key])
}
function videoStarted(event: Event) {
  if (event.currentTarget !== video.value) return
  if (screen.value !== 'playing' || document.hidden || runtimeSettings.value) { video.value?.pause(); return }
  if (paused.value) { paused.value = false; note.value = ''; previousTick = performance.now() }
}
function videoPlaying(event: Event) {
  if (event.currentTarget !== video.value) return
  if (screen.value !== 'playing' || document.hidden || paused.value) video.value?.pause()
  else ready.value = true
}
function videoPaused(event: Event) {
  if (event.currentTarget !== video.value || video.value?.ended) return
  // 红色相位由 syncVideoPhase 主动暂停时不算用户暂停整局。
  if (videoHold) return
  pause()
}
function videoReady(event: Event) {
  if (event.currentTarget === video.value) { ready.value = event.type === 'canplay'; if (ready.value) warmImages() }
}
function videoVolumeChanged(event: Event) {
  if (event.currentTarget !== video.value) return
  settings.value.mediaVolume = Math.round(video.value.volume * 100)
}
function retryMedia() {
  error.value = ''; ready.value = false
  if (video.value) video.value.load()
  else { if (current.value) imageBuffer.remove(current.value); void loadCurrentImage() }
}
function toggleFavorite() {
  if (!current.value) return
  const key = mediaKey(current.value)
  if (favorite.value) preferences.favorites = preferences.favorites.filter(value => value !== key)
  else preferences.favorites = [...preferences.favorites, key]
}
function zoom(delta: number) {
  zoomLevel.value = delta === 0 ? 1 : Math.max(1, Math.min(4, zoomLevel.value + delta))
}
function pointerDown(event: PointerEvent) {
  if (event.button !== 0 || !imageViewport.value) return
  if (pointer) { pointer = undefined; suppressClick = true; return }
  pointer = { id: event.pointerId, x: event.clientX, y: event.clientY, left: imageViewport.value.scrollLeft, top: imageViewport.value.scrollTop, moved: false }
  suppressClick = false
  if (zoomLevel.value > 1) imageViewport.value.setPointerCapture(event.pointerId)
}
function pointerMove(event: PointerEvent) {
  if (!pointer || pointer.id !== event.pointerId) return
  const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y
  if (Math.hypot(dx, dy) > 10) pointer.moved = true
  if (zoomLevel.value > 1 && imageViewport.value) imageViewport.value.scrollTo(pointer.left - dx, pointer.top - dy)
}
function pointerUp(event: PointerEvent) {
  if (!pointer || pointer.id !== event.pointerId) return
  const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y
  suppressClick = pointer.moved
  if (zoomLevel.value === 1 && Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.3) step(dx < 0 ? 1 : -1)
  pointer = undefined
}
function imageClick() { if (!suppressClick && zoomLevel.value === 1) step(1) }
async function fullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else if (playerElement.value?.requestFullscreen) await playerElement.value.requestFullscreen()
    else note.value = '当前浏览器不支持页面全屏，可使用视频自带的全屏按钮。'
  } catch { note.value = '无法进入全屏，请检查浏览器权限。' }
}
function fullscreenChanged() { fullscreenOn.value = document.fullscreenElement === playerElement.value }
async function pip() {
  if (pipMode.value === 'doc') { await openDocPip(); return }
  const element = video.value
  if (!element || !document.pictureInPictureEnabled) { note.value = '当前浏览器不支持视频悬浮小窗。'; return }
  try {
    if (document.pictureInPictureElement) await document.exitPictureInPicture()
    else await element.requestPictureInPicture()
  } catch { note.value = '无法打开悬浮小窗，请检查浏览器权限。' }
}
/** Document PiP：把当前指令投到一个独立小窗里，可以一边看别的应用一边继续。 */
async function openDocPip() {
  const api = (window as Window & { documentPictureInPicture?: { window?: Window | null; requestWindow?: (options?: { width?: number; height?: number }) => Promise<Window> } }).documentPictureInPicture
  if (!api?.requestWindow) { note.value = '当前浏览器不支持悬浮小窗。'; return }
  if (api.window) { api.window.close(); pipWindow = null; return }
  try {
    const win = await api.requestWindow({ width: 340, height: 250 })
    pipWindow = win
    win.document.documentElement.lang = document.documentElement.lang || 'zh-CN'
    win.document.title = '寸止游戏'
    const body = win.document.body
    body.style.margin = '0'
    body.style.background = '#000'
    renderPip()
    win.addEventListener('pagehide', () => { pipWindow = null })
  } catch { note.value = '无法打开悬浮小窗，请检查浏览器权限。' }
}
/** 把当前帧画进 Document PiP 小窗（指令 + 模式 + 剩余时间 + 忍耐/暂停）。 */
function renderPip() {
  const win = pipWindow
  if (!win) return
  const doc = win.document
  const value = frame.value
  const color = modeColors[mode.value] ?? '#fff'
  doc.body.innerHTML = ''
  const wrap = doc.createElement('div')
  wrap.setAttribute('data-sundome-pip-view', '')
  wrap.style.cssText = 'position:fixed;inset:0;display:flex;flex-direction:column;gap:8px;padding:12px 14px;box-sizing:border-box;background:#0a0708;color:#fff;font-family:system-ui,-apple-system,"Segoe UI","PingFang SC","Noto Sans SC",sans-serif'
  const head = doc.createElement('div')
  head.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px'
  const pill = doc.createElement('span')
  pill.setAttribute('data-sundome-pip-mode', '')
  pill.textContent = modeLabels[mode.value] ?? ''
  pill.style.cssText = `border:2px solid ${color};color:${color};border-radius:999px;padding:2px 10px;font-size:13px;font-weight:700;letter-spacing:.15em;white-space:nowrap`
  head.append(pill)
  if (!settings.value.hideRemaining) {
    const clock = doc.createElement('span')
    clock.setAttribute('data-sundome-pip-clock', '')
    clock.textContent = remainingText.value
    clock.style.cssText = 'font-size:22px;font-weight:700;font-variant-numeric:tabular-nums'
    head.append(clock)
  }
  const center = doc.createElement('div')
  center.style.cssText = 'flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;text-align:center'
  if (value?.toneBefore) {
    const before = doc.createElement('p')
    before.textContent = value.toneBefore
    before.style.cssText = 'margin:0;font-size:15px;font-weight:700;opacity:.85'
    center.append(before)
  }
  const text = doc.createElement('p')
  text.setAttribute('data-sundome-pip-text', '')
  text.textContent = value?.text ?? ''
  text.style.cssText = 'margin:0;font-size:clamp(18px,8vw,40px);font-weight:800;line-height:1.2;text-wrap:balance;overflow-wrap:anywhere'
  center.append(text)
  if (value?.toneAfter) {
    const after = doc.createElement('p')
    after.textContent = value.toneAfter
    after.style.cssText = 'margin:0;font-size:14px;font-weight:700;opacity:.8'
    center.append(after)
  }
  wrap.append(head, center)
  const actions = doc.createElement('div')
  actions.style.cssText = 'display:flex;justify-content:center;gap:8px;padding-top:8px'
  const base = 'flex:1 1 auto;font:inherit;font-size:13px;font-weight:700;border-radius:999px;padding:7px 12px;cursor:pointer;white-space:nowrap'
  const edgeButton = doc.createElement('button')
  edgeButton.type = 'button'
  edgeButton.setAttribute('data-sundome-pip-edge', '')
  edgeButton.textContent = value?.cooling ? '等它平息' : '忍住了'
  edgeButton.disabled = !canHold.value
  edgeButton.style.cssText = `${base};border:2px solid ${canHold.value ? 'rgba(255,255,255,.6)' : 'rgba(255,255,255,.2)'};background:transparent;color:${canHold.value ? '#fff' : 'rgba(255,255,255,.3)'}`
  edgeButton.addEventListener('click', () => hold())
  const pauseButton = doc.createElement('button')
  pauseButton.type = 'button'
  pauseButton.setAttribute('data-sundome-pip-pause', '')
  pauseButton.textContent = paused.value ? '继续' : '暂停'
  pauseButton.style.cssText = `${base};border:1px solid rgba(255,255,255,.4);background:transparent;color:#fff`
  pauseButton.addEventListener('click', () => (paused.value ? resume() : pause()))
  actions.append(edgeButton, pauseButton)
  wrap.append(actions)
  doc.body.append(wrap)
}
/** 提示卡里点「打开小窗」。 */
async function openPipFromOffer() {
  await pip()
  pipOfferDone.value = true
}
function openPipSite() {
  const site = settings.value.pipSite
  if (!site) return
  window.open(site, '_blank', 'noopener')
}
function closePipOffer() {
  pipOfferOpen.value = false
}

async function landscape() {
  const orientation = window.screen.orientation as (ScreenOrientation & { lock?: (value: string) => Promise<void> }) | undefined
  try { await orientation?.lock?.('landscape') } catch { note.value = '当前浏览器不支持锁定横屏，可手动旋转设备。' }
}
function updateVolume(payload: { key: 'mediaVolume' | 'beatVolume' | 'textOpacity' | 'textScale'; value: number }) {
  const value = Math.round(payload.value)
  if (!Number.isFinite(value)) return
  if (payload.key === 'textOpacity') settings.value.textOpacity = Math.min(100, Math.max(textOpacityMin, value))
  else if (payload.key === 'textScale') settings.value.textScale = Math.min(140, Math.max(textScaleMin, value))
  else if (payload.key === 'mediaVolume') {
    settings.value.mediaVolume = Math.min(100, Math.max(0, value))
    if (video.value) video.value.volume = settings.value.mediaVolume / 100
  } else settings.value.beatVolume = Math.min(beatVolumeMax, Math.max(0, value))
}
function backToLists() {
  queueRequest.abort(); queueLoading.value = false; pendingAdvance = false; imageLoad++; imageBuffer.clear()
  stopMirror()
  pause(); screen.value = 'setup'; runtimeSettings.value = false; queue.value = []; availableMedia = []
  error.value = ''; note.value = ''; session.value = null; frame.value = null; held.value = 0
  if (document.fullscreenElement === playerElement.value) void document.exitFullscreen()
}
function exitRun() {
  if (screen.value !== 'playing') { backToLists(); return }
  if (!confirm('结束本次播放并返回播放列表？')) return
  backToLists()
}
function restart() {
  if (!options.value) { backToLists(); return }
  imageBuffer.clear(); imageLoad++
  stopMirror()
  lostBestNow.value = false
  const cycle = playbackCycle(availableMedia, options.value, preferences.shownImages)
  queue.value = cycle.queue; preferences.shownImages = cycle.shownImages
  beginSession()
}

/** 「带惩罚再来一局」：把下一局的结局改成「必定禁止」，然后立刻重开。 */
function penaltyRestart() {
  settings.value.finale = 'never'
  persistEdge()
  note.value = ''
  restart()
}
function guideAnchor(step: number) {
  // 引导卡用聚光灯指到该步对应的元素上；找不到就居中展示。
  const selector = guideSteps[step]?.target
  if (!selector) return null
  return document.querySelector(selector)
}

function closeGuide() {
  guideOpen.value = false
  markGuideSeen()
  if (pendingStart.value) { pendingStart.value = false; void nextTick(() => { void start() }); return }
  playerElement.value?.focus()
}
function keydown(event: KeyboardEvent) {
  if (screen.value !== 'playing' || runtimeSettings.value || event.altKey || event.ctrlKey || event.metaKey
    || (event.target as HTMLElement).closest('input,select,textarea,video,[contenteditable]')) return
  if (event.key === 'Escape') { exitRun(); event.preventDefault(); return }
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    const forward = event.key === 'ArrowRight'
    if (current.value?.kind === 'video' && video.value) seekStep(forward ? 1 : -1)
    else step(forward ? 1 : -1)
  }
  else if (event.code === 'Space' && !(event.target as HTMLElement).closest('button')) { if (paused.value) void resume(); else pause() }
  else if (event.key.toLowerCase() === 'e') hold()
  else if (event.key.toLowerCase() === 'f') void fullscreen()
  else return
  event.preventDefault()
}
function visibilityChanged() {
  if (document.hidden && screen.value === 'playing' && !paused.value) {
    pause(); note.value = '页面已转入后台，播放已暂停。'
  }
  if (!document.hidden) requestAnimationFrame(recordDisplayedImage)
}
function adjustTextOpacity(delta: number) {
  settings.value.textOpacity = Math.min(100, Math.max(textOpacityMin, textOpacity.value + delta))
}
function adjustTextScale(delta: number) {
  settings.value.textScale = Math.min(140, Math.max(textScaleMin, textScale.value + delta))
}

watch(current, () => { void loadCurrentImage() })
watch(() => queue.value.length, () => { if (ready.value) warmImages() })
watch(() => screen.value, value => {
  const next = value === 'playing'
  if (next === immersive) return
  immersive = next
  document.documentElement.classList.toggle('playback-immersive', next)
}, { immediate: true })

onMounted(() => {
  try {
    const stored = localStorage.getItem(playbackStorageKey)
    if (stored) Object.assign(preferences, readPreferences(stored))
  } catch {
    setupModel.storageBlocked = true
    setupModel.storageError = '无法读取本机播放设置，请检查浏览器存储权限；也可重置后重新创建播放列表。'
  }
  try {
    const storedEdge = localStorage.getItem(edgeStorageKey)
    if (storedEdge) settings.value = readEdgeSettings(storedEdge)
  } catch { /* 设置读不出来就用默认值 */ }
  try {
    const storedLost = localStorage.getItem(lostStorageKey)
    if (storedLost) lostRecord.value = readLost(storedLost)
  } catch { /* 记录读不出来就当没玩过 */ }
  if (!preferences.playlists.length) createPlaylist()
  if (!playlist.value) preferences.selected = preferences.playlists[0]!.id
  setupModel.ready = true
  if (!setupModel.storageBlocked) persist()
  void loadGalleries()
  landscapeAvailable.value = typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches
  previousTick = performance.now(); timer = setInterval(tick, 100)
  document.addEventListener('keydown', keydown)
  document.addEventListener('visibilitychange', visibilityChanged)
  document.addEventListener('fullscreenchange', fullscreenChanged)
})
onBeforeUnmount(() => {
  disposed = true; request.abort(); queueRequest.abort(); imageLoad++; imageBuffer.clear(); clearInterval(timer); pause()
  stopMirror()
  try { pipWindow?.close() } catch {}
  pipWindow = null
  document.documentElement.classList.remove('playback-immersive')
  sound.close()
  document.removeEventListener('keydown', keydown)
  document.removeEventListener('visibilitychange', visibilityChanged)
  document.removeEventListener('fullscreenchange', fullscreenChanged)
})
</script>

<template>
  <div class="playback-panel">
    <p v-if="setupModel.storageError" class="notice error" role="alert">{{ setupModel.storageError }}<button v-if="setupModel.storageBlocked" class="text-button" @click="resetPreferences">重置播放设置</button><button v-else class="text-button" @click="persist">重新保存</button></p>

    <form v-if="screen === 'setup'" class="playlist-editor" data-sundome="setup" novalidate @submit.prevent="start">
      <div class="playlist-picker">
        <label>播放列表<select v-model="preferences.selected" :disabled="setupModel.starting">
          <option v-for="item in preferences.playlists" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select></label>
        <button type="button" class="secondary" :disabled="setupModel.starting" @click="createPlaylist">新建</button>
        <button type="button" class="text-button danger-text" :disabled="setupModel.starting || !playlist" @click="deletePlaylist">删除</button>
      </div>
      <template v-if="playlist">
        <div class="setup-summary">
          <div><strong>准备开始</strong><p data-sundome-summary>{{ summary }}</p></div>
          <button class="primary" data-sundome-start-quick :disabled="setupModel.loading || setupModel.starting || !playlist.roots.length">
            <Icon :name="setupModel.starting ? 'loader' : 'play'" :size="18" />{{ setupModel.starting ? '正在读取媒体…' : '开始' }}
          </button>
          <button v-if="setupModel.starting" type="button" class="secondary" @click="queueRequest.abort()">取消读取</button>
        </div>
        <fieldset :disabled="setupModel.starting" class="playlist-fields">
          <label class="playlist-name">名称<input v-model.trim="playlist.name" maxlength="80" required></label>
          <fieldset class="media-types"><legend>播放内容</legend>
            <label v-for="choice in ([['mixed', '混合'], ['image', '仅图片'], ['video', '仅视频']] as const)" :key="choice[0]" :class="{ chosen: playlist.kind === choice[0] }">
              <input v-model="playlist.kind" type="radio" name="media-kind" :value="choice[0]" />{{ choice[1] }}
            </label>
          </fieldset>
          <div class="gallery-heading"><span>图库</span><button class="text-button" type="button" :disabled="setupModel.loading" @click="loadGalleries"><Icon name="refresh" :size="16" />{{ setupModel.loading ? '正在刷新…' : '刷新' }}</button></div>
          <p v-if="setupModel.loading && !setupModel.galleries.length" class="muted" role="status">正在读取图库…</p>
          <div class="gallery-choices">
            <label v-for="gallery in setupModel.galleries" :key="gallery.id" :class="{ chosen: playlist.roots.includes(gallery.id) }">
              <input type="checkbox" :checked="playlist.roots.includes(gallery.id)" @change="checkGallery(gallery.id, ($event.target as HTMLInputElement).checked)" />
              <Icon name="folder" :size="22" /><span><strong>{{ galleryName(gallery) }}</strong><small>{{ gallery.path }}</small></span>
            </label>
            <label v-for="id in playlist.roots.filter(id => !setupModel.galleries.some(gallery => gallery.id === id))" :key="id" class="missing-gallery">
              <input type="checkbox" checked @change="checkGallery(id, false)" /><span>图库已移除，取消勾选后可继续</span>
            </label>
          </div>
          <p class="gallery-help muted">包含子目录。其他图库可在小米云相册中绑定本地目录后选择。</p>
          <div class="playback-settings"><PlaybackSettings v-model="settings" /></div>
          <details class="configuration-management"><summary>配置管理</summary>
            <p class="muted">导出只包含播放参数，不包含原文件、图库路径、喜欢或已展示记录；导入后需重新选择图库。</p>
            <div class="configuration-actions">
              <button class="secondary" type="button" @click="downloadConfiguration">导出 JSON</button>
              <button class="secondary" type="button" @click="importInput?.click()">导入 JSON</button>
              <button class="text-button" type="button" @click="restoreDefaults">恢复当前列表默认参数</button>
            </div>
            <input ref="importInput" type="file" accept=".json,application/json" hidden @change="uploadConfiguration" />
          </details>
        </fieldset>
        <p v-if="setupModel.error" class="notice error" role="alert">{{ setupModel.error }}</p>
        <div class="playback-start">
          <span class="muted">已选 {{ playlist.roots.length }} 个图库</span>
          <button class="primary" data-sundome-start :disabled="setupModel.loading || setupModel.starting || !playlist.roots.length">
            <Icon :name="setupModel.starting ? 'loader' : 'play'" :size="18" />{{ setupModel.starting ? '正在读取媒体…' : '开始' }}
          </button>
        </div>
      </template>
    </form>

    <PlaybackFinished
      v-else-if="screen === 'finished'"
      :outcome="finishedReason"
      :elapsed="clockTime(elapsedMs)"
      :duration-minutes="settings.minutes"
      :percent="finishedPercent"
      :held="held"
      :commands="commandCount"
      :rounds="frame?.round ?? round"
      :extends="session?.extends ?? 0"
      :lost-count="lostRecord.count"
      :lost-best="clockTime(lostRecord.bestMs)"
      :lost-best-now="lostBestNow"
      :multi="finishedMulti"
      @again="restart"
      @exit="backToLists"
      @penalty="penaltyRestart"
    />

    <div
      v-else
      ref="playerElement"
      class="playback-runtime"
      tabindex="-1"
      data-sundome="play"
      data-body="male"
      :data-mode="mode"
      :data-nipple="settings.focus === 'nipple' ? 'true' : 'false'"
      :data-glans="settings.focus === 'glans' ? 'true' : 'false'"
      :data-category="taskCategory"
      :data-paused="paused ? 'true' : 'false'"
      :data-cooldown="cooling ? 'true' : 'false'"
      :data-edges="held"
      :data-toy="settings.toy ? 'on' : 'off'"
      :data-task-seconds="taskSeconds"
      role="dialog"
      aria-modal="true"
      :aria-label="'游戏进行中'"
    >
      <PlaybackOverlay :mode="mode" :dim="dimLevel" :opacity="textOpacity" :scale="textScale">
        <template #media>
          <div
            v-show="!runtimeSettings"
            class="playback-media"
            data-sundome-video
            :data-video-kind="current?.kind ?? 'image'"
            :data-fit="settings.fit"
            :data-pos="noCrop ? settings.pos : 'cover'"
            data-layout="background"
            :data-playing="videoDimmed ? 'false' : 'true'"
            :data-dim="Math.round(dimLevel)"
            :style="{ opacity: mediaOpacity }"
            @pointerup="tapSeek"
          >
            <div
              v-if="current?.kind === 'image'"
              ref="imageViewport"
              class="image-viewport"
              :class="{ zoomed: zoomLevel > 1 }"
              @pointerdown="pointerDown" @pointermove="pointerMove" @pointerup="pointerUp"
              @pointercancel="pointer = undefined; suppressClick = true" @click="imageClick"
            >
              <div class="image-canvas" :style="{ width: `${zoomLevel * 100}%`, height: `${zoomLevel * 100}%` }">
                <img v-if="imageSource" :key="mediaKey(current)" :src="imageSource" :alt="current.name"
                  :style="{ objectFit: noCrop ? 'contain' : 'cover', objectPosition: noCrop ? `center ${settings.pos}` : 'center' }"
                  draggable="false" @load="imageLoaded" @error="mediaFailed" />
              </div>
            </div>
            <video
              v-else-if="current" :key="mediaKey(current)" ref="video" :src="mediaUrl(current)"
              :style="{ objectFit: noCrop ? 'contain' : 'cover', objectPosition: noCrop ? `center ${settings.pos}` : 'center' }"
              playsinline preload="metadata" :muted="videoMuted"
              @volumechange="videoVolumeChanged" @loadedmetadata="videoLoaded"
              @canplay="videoReady" @play="videoStarted" @playing="videoPlaying" @waiting="videoReady"
              @pause="videoPaused" @ended="$event.currentTarget === video && step(1)" @error="mediaFailed"
            />
            <!-- 镜子：前置摄像头左右翻转；铺满背景时叠一层模式色遮罩，与参考站一致 -->
            <video
              v-if="mirrorVisible" ref="mirrorVideo" class="mirror-video" :class="`mirror-${mirrorPlace}`"
              :data-sundome-mirror="mirrorPlace" :aria-label="mirrorText.aria"
              autoplay playsinline muted disablePictureInPicture
              @loadedmetadata="attachMirror"
            />
            <div v-if="mirrorVisible && mirrorPlace === 'bg'" class="mirror-dim" :style="{ backgroundColor: mirrorDim }" aria-hidden="true" />
          </div>
        </template>
        <template #top>
          <PlaybackTopBar
            :name="options?.name || ''"
            :position="{ index: frame?.task?.index ?? 0, total: session?.tasks.length ?? 0, cycle: frame?.round ?? 1 }"
            :remaining="remainingText"
            :hide-time="hideClock"
            :paused="paused"
            :playing="screen === 'playing'"
            :held="held"
            :no-crop="noCrop"
            :align="settings.pos"
            :pip-available="pipAvailable"
            :landscape-available="landscapeAvailable"
            :volume-open="volumeOpen"
            :fullscreen="fullscreenOn"
            :note="note"
            :extend-count="session?.extends ?? 0"
            @toggle-crop="toggleCrop"
            @cycle-position="cyclePosition"
            @pip="pip"
            @volume="volumeOpen = !volumeOpen"
            @landscape="landscape"
            @fullscreen="fullscreen"
            @toggle-pause="paused ? resume() : pause()"
            @exit="exitRun"
          />
        </template>
        <PlaybackStage
          :mode="mode"
          :text="commandText"
          :hint="commandHint"
          :bpm="paused ? 0 : beatBpm"
          :progress="taskProgress"
          :task-seconds="taskSeconds"
          :task-key="taskKey"
          :paused="paused"
          :cooling="cooling"
          :can-hold="canHold"
          :held="held"
          :note="note"
          :tone-before="frame?.toneBefore ?? ''"
          :tone-after="frame?.toneAfter ?? ''"
          @hold="hold"
          @lost="lose"
          @guide="guideOpen = true"
        />
        <template #bottom>
          <PlaybackBottom
            :elapsed="clockTime(elapsedMs)"
            :total="totalMs ? formatClock(totalMs) : ''"
            :progress="progressPercent"
            :allowed="allowed"
            :window-left="windowLeft"
            :hide-time="hideClock"
            @skip="step(1)"
          />
        </template>
      </PlaybackOverlay>

      <div v-if="seekFlash" :key="seekFlash.key" class="seek-flash" :data-sundome-seek-flash="seekFlash.side * seekFlash.total" :style="{ left: `${seekFlash.x}px`, top: `${seekFlash.y}px` }">
        <span class="seek-flash-pill">
          <svg v-if="seekFlash.side < 0" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M11 6v12l-8.5-6zM21 6v12l-8.5-6z" /></svg>
          {{ seekFlash.side > 0 ? `+${seekFlash.total}` : `−${seekFlash.total}` }}
          <svg v-if="seekFlash.side > 0" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M13 6v12l8.5-6zM3 6v12l8.5-6z" /></svg>
        </span>
      </div>

      <PlaybackReward
        v-if="allowed"
        :ruined="ruined"
        :window-left="windowLeft"
        :window-total="windowTotal"
        :multi="multi"
        :round="multiRound"
        :allow-below="allowBelow"
      />

      <div v-if="pipOfferOpen" class="pip-offer" data-sundome-pip-section="on" role="dialog" aria-modal="true">
        <p class="pip-offer-title">边看别的视频边玩</p>
        <p class="pip-offer-lead">{{ pipOfferDone ? '小窗已打开。现在去打开你想看的网站吧。' : '把指令放进悬浮小窗。在别的网站看视频时，也能照着指令继续。' }}</p>
        <div class="pip-offer-actions">
          <button v-if="!pipOfferDone" class="pip-offer-cta" type="button" data-sundome-pip-cta @click="openPipFromOffer">打开小窗</button>
          <button v-else class="pip-offer-cta" type="button" data-sundome-pip-start-now @click="closePipOffer">开始</button>
          <button v-if="pipOfferDone && settings.pipSite" class="pip-offer-link" type="button" @click="openPipSite">打开 {{ pipSiteLabel }}</button>
          <button class="pip-offer-dismiss" type="button" @click="closePipOffer">关闭</button>
        </div>
      </div>

      <div class="runtime-controls">
        <button class="runtime-chip" type="button" title="换一项" @click="step(1)"><Icon name="chevron" :size="14" /></button>
        <button class="runtime-chip" :class="{ liked: favorite }" type="button" :aria-pressed="favorite" title="喜欢" @click="toggleFavorite"><Icon name="heart" :size="14" /></button>
        <button class="runtime-chip" type="button" title="调大字号" @click="adjustTextScale(10)">A+</button>
        <button class="runtime-chip" type="button" title="调小字号" @click="adjustTextScale(-10)">A−</button>
        <button class="runtime-chip" type="button" title="文字更清楚" @click="adjustTextOpacity(10)">◐+</button>
        <button class="runtime-chip" type="button" title="文字更透" @click="adjustTextOpacity(-10)">◐−</button>
        <button ref="settingsButton" class="runtime-chip" type="button" title="播放设置" @click="openSettings"><Icon name="settings" :size="14" /></button>
        <button class="runtime-chip" type="button" title="结束" @click="finish('manual')">结束</button>
      </div>

      <PlaybackVolumePopover
        v-if="volumeOpen"
        :media-volume="settings.mediaVolume"
        :beat-volume="settings.beatVolume"
        :beat-volume-max="beatVolumeMax"
        :text-opacity="textOpacity"
        :text-scale="textScale"
        :text-opacity-min="textOpacityMin"
        :text-scale-min="textScaleMin"
        @update="updateVolume"
      />

      <p v-if="error" class="runtime-error" role="alert">{{ error }}<button class="text-button" @click="retryMedia">重新加载</button></p>

      <section v-if="runtimeSettings" ref="runtimePanel" class="runtime-sheet" tabindex="-1" aria-label="播放中设置">
        <div class="runtime-inner">
          <div class="runtime-heading"><div><h2>播放中设置</h2><p>播放已暂停，改完点「完成设置」继续。图库、顺序与每轮数量请返回列表修改。</p></div><button class="secondary" @click="closeSettings">完成设置</button></div>
          <PlaybackSettings v-model="settings" runtime />
          <p v-if="settingsError" class="notice error" role="alert">{{ settingsError }}</p>
        </div>
      </section>
    </div>
    <PlaybackGuide :steps="guideSteps" :open="guideOpen" :anchor="guideAnchor" @close="closeGuide" />
  </div>
</template>

<style scoped>
.playlist-editor { max-width: 920px; margin: 0 auto; }
.playlist-picker { display: flex; align-items: end; gap: 16px; margin-bottom: 24px; }
.playlist-picker > label { flex: 1; min-width: 0; }
.setup-summary { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 24px; padding: 20px; border-radius: 18px; background: var(--color-soft); }
.setup-summary > div { min-width: 0; }
.setup-summary strong { font-size: 17px; }
.setup-summary p { margin: 6px 0 0; font-size: 14px; color: var(--color-muted); line-height: 1.6; }
.setup-summary button { flex-shrink: 0; }
.playlist-fields { min-width: 0; border: 0; padding: 0; margin: 0; }
.playlist-name { max-width: 440px; }
.media-types { display: flex; gap: 4px; width: fit-content; border: 0; padding: 4px; margin: 20px 0; background: var(--color-soft); border-radius: 12px; }
.media-types legend { float: left; position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.media-types label { position: relative; flex-direction: row; align-items: center; min-height: 44px; padding: 8px 22px; cursor: pointer; border-radius: 8px; }
.media-types .chosen { background: var(--color-canvas); color: var(--color-primary); font-weight: 600; }
.media-types input { position: absolute; opacity: 0; width: 1px; }
.media-types label:has(:focus-visible) { outline: 2px solid var(--color-primary-focus); }
.gallery-heading { display: flex; align-items: center; justify-content: space-between; font-size: 14px; }
.gallery-choices { border-block: 1px solid var(--color-hairline); }
.gallery-choices label { display: flex; flex-direction: row; align-items: center; gap: 16px; padding: 16px 12px; border-bottom: 1px solid var(--color-soft); cursor: pointer; }
.gallery-choices label:last-child { border-bottom: 0; }
.gallery-choices .chosen { background: var(--color-selection); }
.gallery-choices label > span { min-width: 0; display: grid; gap: 4px; }
.gallery-choices strong { font-size: 17px; }
.gallery-choices small { color: var(--color-muted); overflow-wrap: anywhere; }
.gallery-help { margin-top: 12px; }
.missing-gallery { color: var(--color-danger); }
.playback-settings { margin: 24px 0; }
.configuration-management { margin: 24px 0; }
.configuration-management summary { min-height: 44px; cursor: pointer; }
.configuration-management p { font-size: 14px; line-height: 1.6; }
.configuration-actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 16px; }
.playback-start { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.playback-runtime { position: fixed; inset: 0; z-index: 60; color: #fff; outline: none; }
.playback-runtime:fullscreen { inset: 0; width: 100%; height: 100%; background: #000; }
/* 媒体层要接收手势（拖拽缩放、双击快进），外层 .sd-media 是 pointer-events:none。 */
.playback-media {
  transition: opacity .5s ease; position: absolute; inset: 0; overflow: hidden; pointer-events: auto; }
/* 镜子：前置摄像头画面左右翻转。铺满背景时压暗，播放视频时固定到右下角小窗 */
.mirror-video { pointer-events: none; object-fit: cover; position: absolute; }
.mirror-bg { inset: 0; width: 100%; height: 100%; transform: scaleX(-1); }
.mirror-corner { right: 12px; bottom: 84px; z-index: 20; width: 80px; aspect-ratio: 3 / 4; border: 1px solid rgba(255, 255, 255, .3); border-radius: 12px; background: #000; box-shadow: 0 10px 30px rgba(0, 0, 0, .45); transform: scaleX(-1); }
.mirror-dim { position: absolute; inset: 0; transition: background-color .5s ease; }
@media (min-width: 640px) { .mirror-corner { width: 128px; } }
.image-viewport { width: 100%; height: 100%; overflow: hidden; touch-action: pan-y pinch-zoom; cursor: pointer; user-select: none; }
.image-viewport.zoomed { overflow: auto; touch-action: none; cursor: grab; }
.image-canvas { display: grid; place-items: center; }
.image-canvas img { display: block; width: 100%; height: 100%; object-fit: contain; }
.playback-media video { display: block; width: 100%; height: 100%; object-fit: contain; }
.runtime-controls { position: fixed; left: 50%; bottom: max(64px, calc(env(safe-area-inset-bottom) + 56px)); z-index: 30; display: flex; gap: 6px; transform: translateX(-50%); padding: 6px; border-radius: 999px; background: rgba(10, 7, 8, .55); backdrop-filter: blur(8px); }
.runtime-chip { display: inline-flex; align-items: center; justify-content: center; min-width: 30px; min-height: 30px; padding: 0 9px; border: 1px solid rgba(255, 255, 255, .22); border-radius: 999px; background: transparent; color: rgba(255, 255, 255, .82); font-size: 11px; font-weight: 600; cursor: pointer; }
.runtime-chip:hover { background: rgba(255, 255, 255, .14); }
.runtime-chip.liked { color: #f2afc9; }
.runtime-chip.liked :deep(svg) { fill: currentColor; }
.runtime-error { position: fixed; left: 50%; top: 50%; z-index: 95; transform: translate(-50%, -50%); max-width: min(520px, 90vw); padding: 18px 20px; border-radius: 16px; background: rgba(12, 8, 10, .94); color: #fff; font-size: 14px; line-height: 1.6; text-align: center; }
.seek-flash { position: fixed; z-index: 20; transform: translate(-50%, -50%); pointer-events: none; }
.seek-flash-pill { display: inline-flex; align-items: center; gap: 4px; padding: 6px 12px; border-radius: 999px; background: rgba(0, 0, 0, .55); color: #fff; font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; animation: seek-flash .85s ease-out forwards; }
@keyframes seek-flash { 0% { opacity: 0; transform: scale(.9); } 15% { opacity: 1; transform: scale(1); } 70% { opacity: 1; } 100% { opacity: 0; } }
.runtime-sheet { position: fixed; inset: 0; z-index: 70; overflow-y: auto; background: var(--color-canvas); color: var(--color-ink); padding: max(16px, env(safe-area-inset-top)) max(16px, env(safe-area-inset-right)) 48px max(16px, env(safe-area-inset-left)); }
.runtime-inner { max-width: 920px; margin: 0 auto; }
.runtime-heading { display: flex; justify-content: space-between; align-items: start; gap: 20px; margin-bottom: 24px; }
.runtime-heading h2 { margin: 0 0 8px; font-size: 20px; }
.runtime-heading p { font-size: 14px; color: var(--color-muted); max-width: 560px; }
.runtime-heading button { flex-shrink: 0; }
@media (max-width: 600px) {
  .setup-summary { align-items: stretch; flex-direction: column; gap: 16px; padding: 16px; }
  .playlist-picker { gap: 10px; }
  .media-types { width: 100%; }
  .media-types label { flex: 1; justify-content: center; padding-inline: 12px; }
  .gallery-choices label { gap: 10px; padding-inline: 6px; }
  .gallery-choices label > svg { display: none; }
  .runtime-controls { bottom: max(56px, calc(env(safe-area-inset-bottom) + 48px)); gap: 4px; }
  .runtime-chip { min-width: 26px; min-height: 26px; padding: 0 7px; font-size: 10px; }
}
.pip-offer { position: fixed; left: 50%; bottom: max(120px, calc(env(safe-area-inset-bottom) + 112px)); z-index: 32; width: min(360px, calc(100vw - 32px)); transform: translateX(-50%); padding: 14px 16px; border: 1px solid rgba(255, 255, 255, .18); border-radius: 16px; background: rgba(10, 7, 8, .92); color: #fff; text-align: center; backdrop-filter: blur(10px); }
.pip-offer-title { margin: 0; font-size: 14px; font-weight: 700; }
.pip-offer-lead { margin: 6px 0 0; font-size: 12px; line-height: 1.6; color: rgba(255, 255, 255, .72); }
.pip-offer-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 8px; margin-top: 12px; }
.pip-offer-cta { min-height: 0; padding: 8px 20px; border: 0; border-radius: 999px; background: #fff; color: #000; font-size: 13px; font-weight: 700; cursor: pointer; }
.pip-offer-link { min-height: 0; padding: 6px 12px; border: 1px solid rgba(255, 255, 255, .3); border-radius: 999px; background: rgba(0, 0, 0, .5); color: rgba(255, 255, 255, .9); font-size: 12px; cursor: pointer; }
.pip-offer-dismiss { min-height: 0; padding: 8px 4px; border: 0; background: none; color: rgba(255, 255, 255, .55); font-size: 13px; text-decoration: underline; text-underline-offset: 4px; cursor: pointer; }
</style>
