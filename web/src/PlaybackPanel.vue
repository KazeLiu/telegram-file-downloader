<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { api } from './api'
import Icon from './Icon.vue'
import PlaybackSettings from './PlaybackSettings.vue'
import PlaybackBottom from './playback/PlaybackBottom.vue'
import PlaybackFinished from './playback/PlaybackFinished.vue'
import PlaybackGuide from './playback/PlaybackGuide.vue'
import PlaybackOverlay from './playback/PlaybackOverlay.vue'
import PlaybackStage from './playback/PlaybackStage.vue'
import PlaybackTopBar from './playback/PlaybackTopBar.vue'
import PlaybackVolumePopover from './playback/PlaybackVolumePopover.vue'
import { guideSteps, markGuideSeen, readGuideSeen } from './playback/guideSteps'
import { finishLabels, phaseHints, phaseLabels, phaseLegend, phaseOrder, phaseRatios, type FinishReason } from './playback/types'
import { nextPermitRate, overtimeLimit, overtimeStep, phaseDurationMs, pickPhaseKind, resolveEnding, waitDurationMs } from './playback/edge'
import { pickVoiceLine, type VoiceMoment } from './playback/voiceLines'
import { loadPlaybackQueue, PlaybackImageBuffer } from './playbackLoader'
import { clockTime, exportConfiguration, imageKey, importConfiguration, mediaKey, mediaUrl, newPlaylist, nextBeatTime, orderedMedia, playbackCycle, playbackStorageKey, readPreferences, trimShownImages, validPlaylist,
  type Gallery, type ImageTiming, type PlaybackMedia, type PlaybackPreferences, type Playlist } from './playback'

const preferences = reactive<PlaybackPreferences>({ playlists: [], selected: '', favorites: [], shownImages: [] })
const setupModel = reactive({ galleries: [] as Gallery[], loading: false, starting: false, error: '', storageError: '', storageBlocked: false, ready: false })
const playlist = computed(() => preferences.playlists.find(item => item.id === preferences.selected))
const queue = shallowRef<PlaybackMedia[]>([])
const player = reactive({ mode: 'setup' as 'setup' | 'playing' | 'finished', index: 0, paused: false, ready: false,
  error: '', note: '', elapsed: 0, imageElapsed: 0, phaseElapsed: 0, phaseDuration: 24000, phase: 0, autoImages: true,
  imageSeconds: 8, zoom: 1, fullscreen: false, finishedReason: '', beat: false, cycle: 1, noCrop: true,
  // 寸止玩法：忍住次数、当前许可率、是否在许可窗口、窗口剩余秒、加时次数、本次会话总时长。
  held: 0, permit: 0, allowed: false, windowLeft: 0, overtimeCount: 0, totalMs: 0 })
const options = ref<Playlist>()
const runtimeSettings = ref(false)
const volumeOpen = ref(false)
const landscapeAvailable = ref(false)
const guideOpen = ref(false)
const pendingStart = ref(false)
// 中央大字：只在进行中的事件（开始、切相位、忍住、加时、许可）时改写，不在 25ms tick 里重算。
const centerLine = ref('')
let lastVoiceText = ''
let immersive = false
const importInput = ref<HTMLInputElement>()
const settingsButton = ref<HTMLButtonElement>()
const runtimePanel = ref<HTMLElement>()
const settingsError = ref('')
const queueLoading = ref(false)
const queueError = ref('')
const imageSource = ref('')
const imageBuffer = new PlaybackImageBuffer()
let queueRequest = new AbortController()
let pendingAdvance = false
let imageLoad = 0
let availableMedia: PlaybackMedia[] = []
const summary = computed(() => {
  const item = playlist.value
  if (!item) return ''
  return [({ mixed: '混合', image: '仅图片', video: '仅视频' })[item.kind], item.order === 'shuffle' ? '随机顺序' : '文件名顺序',
    item.kind === 'video' ? '' : item.kind === 'image' && item.imageTiming === 'beat' ? `每拍一张 · 快速 ${item.bpm} BPM` : `每张 ${item.imageSeconds} 秒`,
    item.kind === 'video' ? '' : item.imageCount ? `每轮 ${item.imageCount} 张` : '全部未展示图片', item.minutes ? `${item.minutes} 分钟` : '不限时',
    item.metronome || (item.kind === 'image' && item.imageTiming === 'beat') ? '节拍器开' : '节拍器关', item.speech ? '语音开' : '语音关'].filter(Boolean).join(' · ')
})
const imageBeatMode = computed(() => options.value?.kind === 'image' && options.value.imageTiming === 'beat')
const metronomeEnabled = computed(() => options.value?.metronome || imageBeatMode.value)
const current = computed(() => queue.value[player.index])
const phaseKind = computed(() => phaseOrder[player.phase] ?? 'slow')
const phase = computed(() => ({ label: phaseLabels[phaseKind.value], ratio: phaseRatios[phaseKind.value] }))
const bpm = computed(() => Math.round((options.value?.bpm || 100) * phase.value.ratio))
const beatIntervalMs = computed(() => (bpm.value ? 60000 / bpm.value : 0))
// 本次会话总时长（毫秒）：加时赛会把它变长，未加时就是设置的分钟数。
const sessionMs = computed(() => player.totalMs || (options.value?.minutes || 0) * 60000)
const progressPercent = computed(() => (sessionMs.value ? Math.min(100, player.elapsed / sessionMs.value * 100) : 0))
// 中央细进度条表示「当前这一张还要多久换」，与底部的整场进度不是同一个东西。
const itemProgress = computed(() => {
  if (player.paused || current.value?.kind !== 'image' || !player.autoImages || imageBeatMode.value || !player.imageSeconds) return 0
  return Math.min(100, Math.max(0, player.imageElapsed / (player.imageSeconds * 1000) * 100))
})
const pipAvailable = computed(() => current.value?.kind === 'video' && 'pictureInPictureEnabled' in document)
const favorite = computed(() => !!current.value && preferences.favorites.includes(mediaKey(current.value)))
const active = computed(() => player.mode === 'playing' && !player.paused && player.ready && !player.error)
const remaining = computed(() => Math.max(0, sessionMs.value - player.elapsed))
const playerElement = ref<HTMLElement>()
const imageViewport = ref<HTMLElement>()
const video = ref<HTMLVideoElement>()
const imageIntervalInput = ref('8')
const bpmInput = ref('100')
let request = new AbortController()
let timer: ReturnType<typeof setInterval>
let previousTick = 0
let nextBeat = 0
let audio: AudioContext | undefined
let disposed = false
let pointer: { id: number; x: number; y: number; left: number; top: number; moved: boolean } | undefined
let suppressClick = false

watch([current, () => player.cycle], () => { void loadCurrentImage() })
watch(() => queue.value.length, () => { if (player.ready) warmImages() })

function warmImages() {
  if (player.mode !== 'playing') return
  const items = queue.value.slice(Math.max(0, player.index - 1)).filter(item => item.kind === 'image').slice(0, 20)
  void imageBuffer.fill(items)
}
async function loadCurrentImage() {
  const item = current.value, version = ++imageLoad
  imageSource.value = ''
  if (item?.kind !== 'image' || player.mode !== 'playing') return
  player.ready = false
  try {
    const url = await imageBuffer.show(item)
    if (version !== imageLoad || disposed || player.mode !== 'playing') return
    imageSource.value = url; warmImages()
  } catch (error) {
    if (version !== imageLoad || disposed || (error as Error).name === 'AbortError') return
    pause(); player.error = (error as Error).message
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
watch(options, value => {
  if (!value || !validPlaylist(value)) return
  const saved = preferences.playlists.find(item => item.id === value.id)
  if (saved) Object.assign(saved, value)
}, { deep: true })
watch(() => [options.value?.imageSeconds, options.value?.bpm, options.value?.imageTiming] as const, ([seconds, value, timing], previous) => {
  if (!options.value || !validPlaylist(options.value)) return
  if (seconds !== previous[0]) { player.imageSeconds = seconds!; imageIntervalInput.value = String(seconds); player.imageElapsed = 0 }
  if (value !== previous[1]) bpmInput.value = String(value)
  if (value !== previous[1] || timing !== previous[2]) { nextBeat = 0; player.beat = false }
})
watch(() => options.value?.minutes, minutes => {
  if (typeof minutes === 'number' && Number.isInteger(minutes) && minutes >= 0 && minutes <= 180) player.totalMs = minutes * 60000
})
watch(() => options.value?.speech, enabled => { if (!enabled && 'speechSynthesis' in window) speechSynthesis.cancel() })
// 播放期间给 <html> 挂沉浸态：隐藏全局导航与页头，只留播放层。
watch(() => player.mode, mode => {
  const next = mode === 'playing'
  if (next === immersive) return
  immersive = next
  document.documentElement.classList.toggle('playback-immersive', next)
}, { immediate: true })

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
  } catch (error) { setupModel.error = `导入失败：${(error as Error).message}` }
  finally { input.value = '' }
}
async function openSettings() {
  pause(); runtimeSettings.value = true; settingsError.value = ''
  await nextTick(); runtimePanel.value?.focus()
}
function closeSettings() {
  if (!options.value || !validPlaylist(options.value)) { settingsError.value = '请修正数值：间隔 1–300 秒、时长 0–180 分钟、快速节拍 30–180 BPM，均为整数。'; return }
  runtimeSettings.value = false; settingsButton.value?.focus()
  advancePending()
  requestAnimationFrame(recordDisplayedImage)
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
  } catch (error) { if (!disposed) setupModel.error = (error as Error).message }
  finally { if (!disposed) setupModel.loading = false }
}
function galleryName(gallery: Gallery) {
  return gallery.id === 'downloads' ? '下载图库' : gallery.path.split(/[\\/]/).filter(Boolean).pop() || gallery.path
}
function checkGallery(id: string, checked: boolean) {
  if (!playlist.value) return
  playlist.value.roots = checked ? [...playlist.value.roots, id] : playlist.value.roots.filter(root => root !== id)
}
async function prepareAudio() {
  if (!metronomeEnabled.value) return
  try {
    audio ||= new AudioContext()
    if (audio.state === 'suspended') await audio.resume()
  } catch { player.note = '节拍器无法启用，可检查浏览器声音权限，或关闭节拍器继续。' }
}
/** 换中央大字：同一时机内随机，并尽量避开上一句。 */
function setLine(moment: VoiceMoment, fallback = '') {
  const text = pickVoiceLine(moment, Math.random, lastVoiceText)
  if (text) lastVoiceText = text
  centerLine.value = text ?? fallback
}
/** 既有的语音播报通道：语音开关打开时，把当前中央大字念出来。 */
function speakLine() {
  if (!options.value?.speech || !('speechSynthesis' in window) || !centerLine.value) return
  speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(centerLine.value)
  utterance.lang = 'zh-CN'; utterance.rate = options.value.speechRate; utterance.volume = options.value.speechVolume / 100
  utterance.onerror = event => { if (!['canceled', 'interrupted'].includes(event.error) && !disposed) player.note = '语音提示不可用，请检查系统中文语音和浏览器权限。' }
  speechSynthesis.speak(utterance)
}
function silence() {
  nextBeat = 0; player.beat = false
  if ('speechSynthesis' in window && options.value?.speech) speechSynthesis.cancel()
}
function beat(now: number) {
  if (!bpm.value || (imageBeatMode.value && !player.autoImages)) { player.beat = false; nextBeat = 0; return }
  if (!nextBeat) { nextBeat = nextBeatTime(0, now, bpm.value); player.beat = false; return }
  if (now < nextBeat) { player.beat = player.beat && nextBeat - now > 60000 / bpm.value - 120; return }
  nextBeat = nextBeatTime(nextBeat, now, bpm.value)
  if (imageBeatMode.value) {
    step(1)
    if (player.mode !== 'playing') return
  }
  player.beat = true
  if (!metronomeEnabled.value || audio?.state !== 'running' || !options.value?.beatVolume) return
  const oscillator = audio.createOscillator(), gain = audio.createGain()
  oscillator.frequency.value = 660
  gain.gain.setValueAtTime(.055 * options.value.beatVolume / 100, audio.currentTime)
  gain.gain.exponentialRampToValueAtTime(.00001, audio.currentTime + .045)
  oscillator.connect(gain); gain.connect(audio.destination)
  oscillator.start(); oscillator.stop(audio.currentTime + .05)
  oscillator.onended = () => { oscillator.disconnect(); gain.disconnect() }
}
async function start() {
  if (!playlist.value || setupModel.starting) return
  if (!readGuideSeen() && !pendingStart.value) { pendingStart.value = true; guideOpen.value = true; return }
  setupModel.error = ''
  const item = playlist.value
  if (!item.roots.length) { setupModel.error = '请至少勾选一个图库。'; return }
  if (item.roots.some(id => !setupModel.galleries.some(gallery => gallery.id === id))) {
    setupModel.error = '列表包含已移除的图库，请取消勾选后重新开始。'; return
  }
  if (!validPlaylist(item)) {
    setupModel.error = '请填写列表名称，并检查图片间隔（1–300 秒）、总时长（0–180 分钟）、每轮图片数（0–100000）和快速节拍（30–180 BPM），数值请使用整数。'; return
  }
  setupModel.starting = true
  queueRequest.abort(); queueRequest = new AbortController()
  const signal = queueRequest.signal
  queueLoading.value = true; queueError.value = ''; pendingAdvance = false
  availableMedia = []; imageBuffer.clear()
  player.note = ''
  options.value = { ...item, roots: item.roots.slice() }
  imageIntervalInput.value = String(item.imageSeconds); bpmInput.value = String(item.bpm)
  // Unlock audio while the start button's user activation is still available.
  void prepareAudio()
  try {
    await loadPlaybackQueue(options.value, signal, async (batch, done) => {
      if (disposed || signal.aborted) return
      const items = item.favoritesOnly ? batch.filter(media => preferences.favorites.includes(mediaKey(media))) : batch
      availableMedia.push(...items)
      queueLoading.value = !done
      if (player.mode === 'setup') {
        if (!availableMedia.length) {
          if (done) setupModel.error = item.favoritesOnly ? '所选图库中没有符合类型的喜欢收藏，可关闭“仅播放喜欢”。' : '所选图库中没有符合类型的媒体，请调整图库或媒体类型。'
          return
        }
        const cycle = playbackCycle(availableMedia, item, preferences.shownImages)
        if (!done && (cycle.reset || cycle.queue.length < Math.min(20, item.imageCount || 20))) return
        queue.value = cycle.queue; preferences.shownImages = cycle.shownImages
        runtimeSettings.value = false
        if (cycle.reset) player.note = '未展示图片不足一轮，已开始新的图片周期。'
        Object.assign(player, { mode: 'playing', index: 0, paused: document.hidden, ready: false, error: '', elapsed: 0, imageElapsed: 0,
          phaseElapsed: 0, phaseDuration: 24000, phase: 0, autoImages: true, imageSeconds: item.imageSeconds, zoom: 1, finishedReason: '', beat: false, cycle: 1, noCrop: true,
          held: 0, permit: nextPermitRate(item.permitBase, 0), allowed: false, windowLeft: 0, overtimeCount: 0, totalMs: (item.minutes || 0) * 60000 })
        // 第一段相位同样按三比例抽签，并用指令时长倍率算时长。
        const firstPhase = pickPhaseKind(item.ratioFast, item.ratioSlow, item.ratioRest, null, Math.random)
        player.phase = Math.max(0, phaseOrder.indexOf(firstPhase))
        player.phaseDuration = phaseDurationMs(firstPhase, item.instructionPace, Math.random)
        previousTick = performance.now(); nextBeat = 0
        setLine('start', phaseHints[firstPhase])
        if (item.speech && !('speechSynthesis' in window)) player.note = '当前浏览器不支持语音提示。'
        await nextTick(); playerElement.value?.focus(); if (!player.paused) speakLine()
      } else if (player.mode === 'playing') {
        let count = queue.value.filter(media => media.kind === 'image').length
        const added = orderedMedia(items.filter(media => media.kind !== 'image' || !preferences.shownImages.includes(imageKey(media))), item.order)
          .filter(media => media.kind !== 'image' || !item.imageCount || count++ < item.imageCount)
        if (added.length) queue.value = [...queue.value, ...added]
      }
      advancePending()
    })
  } catch (error) {
    if (!disposed && !signal.aborted) {
      if (player.mode === 'setup') setupModel.error = (error as Error).message
      else { queueError.value = '媒体清单读取中断，请返回列表重新开始。'; pause(); player.error = queueError.value }
    }
  } finally { if (!disposed && signal === queueRequest.signal) { setupModel.starting = false; queueLoading.value = false } }
}
function pause() {
  if (player.mode !== 'playing') return
  player.paused = true; video.value?.pause(); silence()
}
async function resume() {
  if (player.mode !== 'playing' || player.error || runtimeSettings.value) return
  player.paused = false; player.note = ''; previousTick = performance.now()
  advancePending()
  if (player.mode !== 'playing' || pendingAdvance) return
  await prepareAudio()
  if (current.value?.kind === 'video') await playVideo()
  if (!player.paused) speakLine()
}
async function playVideo() {
  const element = video.value
  if (!element || player.mode !== 'playing' || player.paused || player.error) return
  try { await element.play() }
  catch (error) {
    if (disposed || element !== video.value || (error as Error).name === 'AbortError') return
    pause(); player.note = '视频尚未开始，请点击继续播放；若仍无法播放，请检查浏览器支持的格式。'
  }
}
function finish(reason: FinishReason) {
  queueRequest.abort(); queueLoading.value = false; pendingAdvance = false
  imageLoad++; imageBuffer.clear()
  pause(); player.mode = 'finished'; player.finishedReason = finishLabels[reason]; player.error = ''
}
function advancePending() {
  if (!pendingAdvance || player.mode !== 'playing' || runtimeSettings.value
    || (queueLoading.value && player.index >= queue.value.length - 1)) return
  step(1)
}
function step(delta: number) {
  if (player.mode !== 'playing' || runtimeSettings.value) return
  if (pendingAdvance) player.note = ''
  let target = player.index + delta
  if (target >= queue.value.length) {
    if (queueError.value) { pause(); player.note = queueError.value; return }
    if (queueLoading.value) { pendingAdvance = true; player.ready = false; player.note = '正在补充媒体列表，请稍候…'; return }
    if (!options.value?.loop) { finish('queue'); return }
    const cycle = playbackCycle(availableMedia, options.value, preferences.shownImages)
    queue.value = cycle.queue; preferences.shownImages = cycle.shownImages
    player.cycle++
    if (cycle.reset) player.note = '未展示图片不足一轮，已开始新的图片周期。'
    target = 0
  } else if (target < 0) target = options.value?.loop ? queue.value.length - 1 : 0
  if (target === player.index && delta < 0) return
  pendingAdvance = false
  player.index = target; player.imageElapsed = 0; player.zoom = 1; player.error = ''; player.ready = false
  void nextTick(() => {
    imageViewport.value?.scrollTo(0, 0)
  })
}
/** 按三比例抽下一段相位（不与上一段相同），时长走 phaseDurationMs。 */
function changePhase() {
  const item = options.value
  if (!item) return
  const kind = pickPhaseKind(item.ratioFast, item.ratioSlow, item.ratioRest, phaseKind.value, Math.random)
  player.phase = Math.max(0, phaseOrder.indexOf(kind))
  player.phaseElapsed = 0
  player.phaseDuration = phaseDurationMs(kind, item.instructionPace, Math.random)
  nextBeat = 0; player.beat = false
  setLine(`phase-${kind}` as VoiceMoment, phaseHints[kind])
  speakLine()
}
/** 忍住了：次数 +1、按许可率公式重算，并立刻切到休息相位等它平息。 */
function hold() {
  const item = options.value
  if (!item || player.mode !== 'playing' || player.paused || player.error || player.allowed || runtimeSettings.value) return
  player.held++
  player.permit = nextPermitRate(item.permitBase, player.held)
  player.phase = Math.max(0, phaseOrder.indexOf('rest'))
  player.phaseElapsed = 0
  player.phaseDuration = waitDurationMs(item.waitMode, item.waitPreset, item.waitMin, item.waitMax, Math.random)
  nextBeat = 0; player.beat = false
  setLine('held')
  speakLine()
}
/** 时间到结算：许可窗口 / 加时 / 直接结束。 */
function settleEnding() {
  const item = options.value
  if (!item || player.mode !== 'playing') return
  const outcome = resolveEnding(item.ending, player.permit, Math.random, player.overtimeCount)
  if (outcome === 'allow') {
    player.allowed = true
    player.windowLeft = Math.max(1, Math.round(item.edgeWindow))
    setLine('ending-allow', '现在可以了')
    speakLine()
    return
  }
  if (outcome === 'ruin') { finish('ruin'); return }
  // 加时赛：没过上限就加时并继续计时，许可率每次 +15%。
  if (item.ending === 'overtime' && player.overtimeCount < overtimeLimit) {
    player.overtimeCount++
    player.permit = Math.min(100, player.permit + overtimeStep)
    player.totalMs += Math.max(1000, Math.round((item.minutes || 0) * 60000 * overtimeStep / 100))
    centerLine.value = `加时 ${player.overtimeCount}`
    lastVoiceText = centerLine.value
    speakLine()
    return
  }
  finish('deny')
}
function tick() {
  const now = performance.now(), elapsed = now - previousTick
  previousTick = now
  if (!active.value) {
    if (imageBeatMode.value && !player.ready) { nextBeat = 0; player.beat = false }
    return
  }
  if (player.allowed) {
    // 许可窗口：只走白色倒计时，不切相位、不再累加整场计时。
    player.windowLeft = Math.max(0, player.windowLeft - elapsed / 1000)
    if (player.windowLeft <= 0) { finish('allow'); return }
  } else {
    player.elapsed += elapsed; player.phaseElapsed += elapsed
    if (options.value?.minutes && remaining.value <= 0) {
      settleEnding()
      if (player.mode !== 'playing') return
    }
    if (!player.allowed && player.phaseElapsed >= player.phaseDuration) changePhase()
  }
  beat(now)
  if (current.value?.kind === 'image' && player.autoImages && !imageBeatMode.value) {
    player.imageElapsed += elapsed
    if (player.imageElapsed >= player.imageSeconds * 1000) step(1)
  }
}
function mediaFailed(event: Event) {
  if (event.currentTarget !== video.value && event.currentTarget !== imageViewport.value?.querySelector('img')) return
  pause(); player.ready = false
  player.error = '无法播放此文件，请检查文件是否仍在图库，以及浏览器是否支持此格式；文件有变化时请返回列表重新开始。'
}
function imageLoaded(event: Event) {
  const image = event.currentTarget
  if (image !== imageViewport.value?.querySelector('img')) return
  player.ready = true
  requestAnimationFrame(() => requestAnimationFrame(() => { if (image === imageViewport.value?.querySelector('img')) recordDisplayedImage() }))
}
function recordDisplayedImage() {
  if (document.hidden || runtimeSettings.value || player.mode !== 'playing' || !player.ready || player.error || current.value?.kind !== 'image') return
  const key = imageKey(current.value)
  if (!preferences.shownImages.includes(key)) preferences.shownImages = trimShownImages([...preferences.shownImages, key])
}
function videoStarted(event: Event) {
  if (event.currentTarget !== video.value) return
  if (player.mode !== 'playing' || document.hidden || runtimeSettings.value) { video.value?.pause(); return }
  if (player.paused) {
    player.paused = false; player.note = ''; previousTick = performance.now()
    void prepareAudio(); speakLine()
  }
}
function videoPlaying(event: Event) {
  if (event.currentTarget !== video.value) return
  if (player.mode !== 'playing' || document.hidden || player.paused) video.value?.pause()
  else player.ready = true
}
function videoPaused(event: Event) {
  if (event.currentTarget === video.value && !video.value?.ended) pause()
}
function videoReady(event: Event) {
  if (event.currentTarget === video.value) { player.ready = event.type === 'canplay'; if (player.ready) warmImages() }
}
function videoVolumeChanged(event: Event) {
  if (event.currentTarget === video.value && options.value) options.value.mediaVolume = Math.round(video.value.volume * 100)
}
function retryMedia() {
  player.error = ''; player.ready = false
  if (video.value) video.value.load()
  else {
    if (current.value) imageBuffer.remove(current.value)
    void loadCurrentImage()
  }
}
function updateInterval(event: Event) {
  const input = event.target as HTMLInputElement
  const seconds = Number(input.value)
  if (!Number.isInteger(seconds) || seconds < 1 || seconds > 300) {
    player.note = '图片间隔请输入 1–300 之间的整数秒。'; imageIntervalInput.value = String(player.imageSeconds); return
  }
  player.imageSeconds = seconds; player.imageElapsed = 0; player.note = ''
  options.value!.imageSeconds = seconds
  imageIntervalInput.value = String(seconds)
  const saved = preferences.playlists.find(item => item.id === options.value?.id)
  if (saved) saved.imageSeconds = seconds
}
async function updateImageTiming(event: Event) {
  const imageTiming = (event.target as HTMLSelectElement).value as ImageTiming
  options.value = { ...options.value!, imageTiming }
  player.imageElapsed = 0; nextBeat = 0; player.beat = false; player.note = ''
  const saved = preferences.playlists.find(item => item.id === options.value?.id)
  if (saved) saved.imageTiming = imageTiming
  await prepareAudio()
}
function updateBpm(event: Event) {
  const input = event.target as HTMLInputElement
  const value = Number(input.value)
  if (!Number.isInteger(value) || value < 30 || value > 180) {
    player.note = '快速节拍请输入 30–180 之间的整数 BPM。'; bpmInput.value = String(options.value!.bpm); return
  }
  options.value = { ...options.value!, bpm: value }
  bpmInput.value = String(value)
  nextBeat = 0; player.note = ''
  const saved = preferences.playlists.find(item => item.id === options.value?.id)
  if (saved) saved.bpm = value
}
function toggleFavorite() {
  if (!current.value) return
  const key = mediaKey(current.value)
  if (favorite.value) preferences.favorites = preferences.favorites.filter(value => value !== key)
  else preferences.favorites = [...preferences.favorites, key]
}
function zoom(delta: number) {
  player.zoom = delta === 0 ? 1 : Math.max(1, Math.min(4, player.zoom + delta))
  if (player.zoom > 1) { player.autoImages = false; player.imageElapsed = 0 }
}
function pointerDown(event: PointerEvent) {
  if (event.button !== 0 || !imageViewport.value) return
  if (pointer) { pointer = undefined; suppressClick = true; return }
  pointer = { id: event.pointerId, x: event.clientX, y: event.clientY, left: imageViewport.value.scrollLeft, top: imageViewport.value.scrollTop, moved: false }
  suppressClick = false
  if (player.zoom > 1) imageViewport.value.setPointerCapture(event.pointerId)
}
function pointerMove(event: PointerEvent) {
  if (!pointer || pointer.id !== event.pointerId) return
  const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y
  if (Math.hypot(dx, dy) > 10) pointer.moved = true
  if (player.zoom > 1 && imageViewport.value) imageViewport.value.scrollTo(pointer.left - dx, pointer.top - dy)
}
function pointerUp(event: PointerEvent) {
  if (!pointer || pointer.id !== event.pointerId) return
  const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y
  suppressClick = pointer.moved
  if (player.zoom === 1 && Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.3) step(dx < 0 ? 1 : -1)
  pointer = undefined
}
function imageClick() { if (!suppressClick && player.zoom === 1) step(1) }
async function fullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else if (playerElement.value?.requestFullscreen) await playerElement.value.requestFullscreen()
    else player.note = '当前浏览器不支持页面全屏，可使用视频自带的全屏按钮。'
  } catch { player.note = '无法进入全屏，请检查浏览器权限。' }
}
function fullscreenChanged() { player.fullscreen = document.fullscreenElement === playerElement.value }
async function pip() {
  const element = video.value
  if (!element || !document.pictureInPictureEnabled) { player.note = '当前浏览器不支持视频悬浮小窗。'; return }
  try {
    if (document.pictureInPictureElement) await document.exitPictureInPicture()
    else await element.requestPictureInPicture()
  } catch { player.note = '无法打开悬浮小窗，请检查浏览器权限。' }
}
async function landscape() {
  const orientation = screen.orientation as (ScreenOrientation & { lock?: (value: string) => Promise<void> }) | undefined
  try { await orientation?.lock?.('landscape') } catch { player.note = '当前浏览器不支持锁定横屏，可手动旋转设备。' }
}
// 音量弹层的滑块直接改运行中的副本，watch(options) 会同步回本机存储。
function updateVolume(payload: { key: 'mediaVolume' | 'beatVolume' | 'speechVolume' | 'brightness'; value: number }) {
  const item = options.value
  if (!item) return
  const value = Math.round(payload.value)
  if (!Number.isFinite(value)) return
  item[payload.key] = payload.key === 'brightness' ? Math.min(100, Math.max(20, value)) : Math.min(100, Math.max(0, value))
  if (payload.key === 'mediaVolume' && video.value) video.value.volume = item.mediaVolume / 100
  if (payload.key === 'beatVolume') { nextBeat = 0; player.beat = false }
}
function backToLists() {
  queueRequest.abort(); queueLoading.value = false; pendingAdvance = false; imageLoad++; imageBuffer.clear()
  pause(); player.mode = 'setup'; runtimeSettings.value = false; queue.value = []; availableMedia = []; player.error = ''; player.note = ''
  // 回到列表时把玩法状态一起清空，下一次开始从头计数。
  player.allowed = false; player.windowLeft = 0; player.held = 0; player.permit = 0; player.overtimeCount = 0; player.totalMs = 0
  centerLine.value = ''; lastVoiceText = ''
  if (document.fullscreenElement === playerElement.value) void document.exitFullscreen()
}
function exitRun() {
  if (player.mode !== 'playing') { backToLists(); return }
  if (!confirm('结束本次播放并返回播放列表？')) return
  backToLists()
}
function restart() {
  backToLists()
  void nextTick(() => { void start() })
}
function closeGuide() {
  guideOpen.value = false
  markGuideSeen()
  if (pendingStart.value) { pendingStart.value = false; void nextTick(() => { void start() }); return }
  playerElement.value?.focus()
}
function keydown(event: KeyboardEvent) {
  if (player.mode !== 'playing' || runtimeSettings.value || event.altKey || event.ctrlKey || event.metaKey
    || (event.target as HTMLElement).closest('input,select,textarea,video,[contenteditable]')) return
  if (event.key === 'Escape') { exitRun(); event.preventDefault(); return }
  if (event.key === 'ArrowLeft') step(-1)
  else if (event.key === 'ArrowRight') step(1)
  else if (event.code === 'Space' && !(event.target as HTMLElement).closest('button')) player.paused ? void resume() : pause()
  else if (event.key.toLowerCase() === 'f') void fullscreen()
  else return
  event.preventDefault()
}
function visibilityChanged() {
  if (document.hidden && player.mode === 'playing' && !player.paused) {
    pause(); player.note = '页面已转入后台，播放已暂停。'
  }
  if (!document.hidden) requestAnimationFrame(recordDisplayedImage)
}
onMounted(() => {
  try {
    const stored = localStorage.getItem(playbackStorageKey)
    if (stored) Object.assign(preferences, readPreferences(stored))
  } catch (error) {
    setupModel.storageBlocked = true
    setupModel.storageError = '无法读取本机播放设置，请检查浏览器存储权限；也可重置后重新创建播放列表。'
  }
  if (!preferences.playlists.length) createPlaylist()
  if (!playlist.value) preferences.selected = preferences.playlists[0]!.id
  setupModel.ready = true
  if (!setupModel.storageBlocked) persist()
  void loadGalleries()
  landscapeAvailable.value = typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches
  previousTick = performance.now(); timer = setInterval(tick, 25)
  document.addEventListener('keydown', keydown)
  document.addEventListener('visibilitychange', visibilityChanged)
  document.addEventListener('fullscreenchange', fullscreenChanged)
})
onBeforeUnmount(() => {
  disposed = true; request.abort(); queueRequest.abort(); imageLoad++; imageBuffer.clear(); clearInterval(timer); pause()
  document.documentElement.classList.remove('playback-immersive')
  if (audio) void audio.close()
  document.removeEventListener('keydown', keydown)
  document.removeEventListener('visibilitychange', visibilityChanged)
  document.removeEventListener('fullscreenchange', fullscreenChanged)
})
</script>

<template>
  <div class="playback-panel">
    <p v-if="setupModel.storageError" class="notice error" role="alert">{{ setupModel.storageError }}<button v-if="setupModel.storageBlocked" class="text-button" @click="resetPreferences">重置播放设置</button><button v-else class="text-button" @click="persist">重新保存</button></p>
    <form v-if="player.mode === 'setup'" class="playlist-editor" novalidate @submit.prevent="start">
      <div class="playlist-picker"><label>播放列表<select v-model="preferences.selected" :disabled="setupModel.starting"><option v-for="item in preferences.playlists" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><button type="button" class="secondary" :disabled="setupModel.starting" @click="createPlaylist">新建</button><button type="button" class="text-button danger-text" :disabled="setupModel.starting || !playlist" @click="deletePlaylist">删除</button></div>
      <template v-if="playlist">
        <div class="setup-summary"><div><strong>准备播放</strong><p>{{ summary }}</p></div><button class="primary" :disabled="setupModel.loading || setupModel.starting || !playlist.roots.length"><Icon :name="setupModel.starting ? 'loader' : 'play'" :size="18" />{{ setupModel.starting ? '正在读取媒体…' : '开始播放' }}</button><button v-if="setupModel.starting" type="button" class="secondary" @click="queueRequest.abort()">取消读取</button></div>
        <fieldset :disabled="setupModel.starting" class="playlist-fields">
          <label class="playlist-name">名称<input v-model.trim="playlist.name" maxlength="80" required /></label>
          <fieldset class="media-types"><legend>播放内容</legend><label v-for="choice in ([['mixed', '混合'], ['image', '仅图片'], ['video', '仅视频']] as const)" :key="choice[0]" :class="{ chosen: playlist.kind === choice[0] }"><input v-model="playlist.kind" type="radio" name="media-kind" :value="choice[0]" />{{ choice[1] }}</label></fieldset>
          <div class="gallery-heading"><span>图库</span><button class="text-button" type="button" :disabled="setupModel.loading" @click="loadGalleries"><Icon name="refresh" :size="16" />{{ setupModel.loading ? '正在刷新…' : '刷新' }}</button></div>
          <p v-if="setupModel.loading && !setupModel.galleries.length" class="muted" role="status">正在读取图库…</p>
          <div class="gallery-choices"><label v-for="gallery in setupModel.galleries" :key="gallery.id" :class="{ chosen: playlist.roots.includes(gallery.id) }"><input type="checkbox" :checked="playlist.roots.includes(gallery.id)" @change="checkGallery(gallery.id, ($event.target as HTMLInputElement).checked)" /><Icon name="folder" :size="22" /><span><strong>{{ galleryName(gallery) }}</strong><small>{{ gallery.path }}</small></span></label><label v-for="id in playlist.roots.filter(id => !setupModel.galleries.some(gallery => gallery.id === id))" :key="id" class="missing-gallery"><input type="checkbox" checked @change="checkGallery(id, false)" /><span>图库已移除，取消勾选后可继续</span></label></div>
          <p class="gallery-help muted">包含子目录。其他图库可在小米云相册中绑定本地目录后选择。</p>
          <div class="playback-settings"><PlaybackSettings :model-value="playlist" /></div>
          <details class="configuration-management"><summary>配置管理</summary><p class="muted">导出只包含播放参数，不包含原文件、图库路径、喜欢或已展示记录；导入后需重新选择图库。</p><div class="configuration-actions"><button class="secondary" type="button" @click="downloadConfiguration">导出 JSON</button><button class="secondary" type="button" @click="importInput?.click()">导入 JSON</button><button class="text-button" type="button" @click="restoreDefaults">恢复当前列表默认参数</button></div><input ref="importInput" type="file" accept=".json,application/json" hidden @change="uploadConfiguration" /></details>
        </fieldset>
        <p v-if="setupModel.error" class="notice error" role="alert">{{ setupModel.error }}</p>
        <div class="playback-start"><span class="muted">已选 {{ playlist.roots.length }} 个图库</span><button class="primary" :disabled="setupModel.loading || setupModel.starting || !playlist.roots.length"><Icon :name="setupModel.starting ? 'loader' : 'play'" :size="18" />{{ setupModel.starting ? '正在读取媒体…' : '开始播放' }}</button></div>
      </template>
    </form>

    <PlaybackFinished v-else-if="player.mode === 'finished'" :reason="player.finishedReason" :elapsed="clockTime(player.elapsed)" :position="{ index: player.index, total: queue.length, cycle: player.cycle }" @restart="restart" @close="backToLists" />

    <div v-else ref="playerElement" class="playback-runtime" tabindex="-1">
      <PlaybackOverlay :phase="phaseKind" :paused="player.paused" :beat-interval-ms="beatIntervalMs" :dim="options?.brightness ?? 100">
        <template #top>
          <PlaybackTopBar
            :name="options?.name || ''"
            :position="{ index: player.index, total: queue.length, cycle: player.cycle }"
            :remaining="options?.minutes ? clockTime(remaining) : ''"
            :hide-time="!!options?.hideTime"
            :paused="player.paused"
            :playing="player.mode === 'playing'"
            :held="player.held"
            :no-crop="player.noCrop"
            :pip-available="pipAvailable"
            :landscape-available="landscapeAvailable"
            :volume-open="volumeOpen"
            :fullscreen="true"
            @toggle-crop="player.noCrop = !player.noCrop"
            @pip="pip"
            @volume="volumeOpen = !volumeOpen"
            @landscape="landscape"
            @fullscreen="fullscreen"
            @toggle-pause="player.paused ? resume() : pause()"
            @exit="exitRun"
          />
        </template>
        <template #stage>
          <PlaybackStage
            :phase="phaseKind"
            :bpm="player.paused ? 0 : bpm"
            :paused="player.paused"
            :finished="false"
            :loading="!player.ready && !player.error"
            :error="player.error"
            :hint="centerLine || phaseHints[phaseKind]"
            :progress="itemProgress"
            :can-hold="player.mode === 'playing' && !player.error && !player.allowed && !runtimeSettings"
            @hold="hold"
            @edge="finish('edge')"
            @skip="step(1)"
          >
            <div v-show="!runtimeSettings" class="playback-media">
              <div v-if="current?.kind === 'image'" ref="imageViewport" class="image-viewport" :class="{ zoomed: player.zoom > 1 }" @pointerdown="pointerDown" @pointermove="pointerMove" @pointerup="pointerUp" @pointercancel="pointer = undefined; suppressClick = true" @click="imageClick">
                <div class="image-canvas" :style="{ width: `${player.zoom * 100}%`, height: `${player.zoom * 100}%` }"><img v-if="imageSource" :key="`${player.cycle}:${mediaKey(current)}`" :src="imageSource" :alt="current.name" :style="{ filter: `brightness(${options!.brightness}%)`, objectFit: player.noCrop ? 'contain' : 'cover' }" draggable="false" @load="imageLoaded" @error="mediaFailed" /></div>
              </div>
              <video v-else-if="current" :key="`${player.cycle}:${mediaKey(current)}`" ref="video" :src="mediaUrl(current)" :volume="options!.mediaVolume / 100" :style="{ filter: `brightness(${options!.brightness}%)`, objectFit: player.noCrop ? 'contain' : 'cover' }" controls playsinline preload="metadata" @volumechange="videoVolumeChanged" @loadedmetadata="$event.currentTarget === video && playVideo()" @canplay="videoReady" @play="videoStarted" @playing="videoPlaying" @waiting="videoReady" @pause="videoPaused" @ended="$event.currentTarget === video && step(1)" @error="mediaFailed" />
            </div>
            <template #actions>
              <button v-if="queueError" class="player-button" @click="backToLists">返回播放列表</button>
              <template v-else><button class="player-button" @click="retryMedia">重新加载</button><button class="player-button" @click="step(1)">下一项</button></template>
            </template>
            <template #help>
              <ul>
                <li>左右方向键、点击图片或左右滑动切换媒体。</li>
                <li>点「忍住了」：在临界点按下，随后松手等它平息，许可率会跟着提高。</li>
                <li>点「射了」表示没忍住，会直接结算本次播放。</li>
                <li>空格暂停或继续，F 切换全屏，Esc 退出播放。</li>
                <li>按时间保留暂停前的剩余间隔；按 BPM 在继续后重新计一拍，休息时保持图片。</li>
                <li>放大后可拖动查看，自动切图会关闭。</li>
                <li>只有已展示的图片才记入本机去重记录。返回列表或结束不会删除文件。</li>
              </ul>
            </template>
          </PlaybackStage>
        </template>
        <template #bottom>
          <PlaybackBottom
            :title="current?.name || ''"
            :elapsed="clockTime(player.elapsed)"
            :total="options?.minutes ? clockTime(sessionMs) : ''"
            :progress="progressPercent"
            :hide-time="!!options?.hideTime"
            :legend="phaseLegend"
            next-label="换一项"
            :can-next="player.mode === 'playing'"
            :allowed="player.allowed"
            :window-left="player.windowLeft"
            :window-total="options?.edgeWindow ?? 0"
            @next="step(1)"
          >
            <template #controls>
              <div class="player-controls"><button class="player-button" :disabled="player.mode !== 'playing' || (!options?.loop && player.index === 0)" aria-label="上一项" title="上一项（←）" @click="step(-1)"><Icon name="chevron" class="previous-icon" /></button><button class="player-button" :disabled="player.mode !== 'playing'" aria-label="下一项" title="下一项（→）" @click="step(1)"><Icon name="chevron" /></button><button class="player-button" :class="{ liked: favorite }" :aria-pressed="favorite" :aria-label="favorite ? '取消喜欢' : '喜欢'" @click="toggleFavorite"><Icon name="heart" /><span class="favorite-label">{{ favorite ? '已喜欢' : '喜欢' }}</span></button><button class="player-button stop-button" :disabled="player.mode !== 'playing'" @click="finish('manual')">结束</button></div>
              <div v-if="current?.kind === 'image' && player.mode === 'playing'" class="image-controls"><label><input v-model="player.autoImages" type="checkbox" @change="player.imageElapsed = 0; nextBeat = 0; player.zoom = 1" />自动切图</label><select v-if="options?.kind === 'image'" :value="options.imageTiming" aria-label="图片切换方式" @change="updateImageTiming"><option value="time">按时间</option><option value="beat">按 BPM</option></select><label v-if="imageBeatMode" class="interval-control"><input v-model="bpmInput" type="number" min="30" max="180" aria-label="快速节拍（BPM）" @change="updateBpm" />快速 BPM</label><label v-else class="interval-control"><input v-model="imageIntervalInput" type="number" min="1" max="300" aria-label="自动切图间隔（秒）" @change="updateInterval" />秒</label><span class="zoom-controls"><button class="player-button" :disabled="player.zoom <= 1" aria-label="缩小图片" @click="zoom(-.5)">−</button><button class="player-button" title="还原图片" @click="zoom(0)">{{ Math.round(player.zoom * 100) }}%</button><button class="player-button" :disabled="player.zoom >= 4" aria-label="放大图片" @click="zoom(.5)">＋</button></span></div>
              <p v-if="player.note" class="player-note" role="status">{{ player.note }}</p>
            </template>
          </PlaybackBottom>
        </template>
      </PlaybackOverlay>

      <PlaybackVolumePopover
        :open="volumeOpen"
        :media-volume="options?.mediaVolume ?? 100"
        :beat-volume="options?.beatVolume ?? 100"
        :speech-volume="options?.speechVolume ?? 100"
        :brightness="options?.brightness ?? 100"
        @close="volumeOpen = false"
        @change="updateVolume"
        @open-settings="volumeOpen = false; openSettings()"
      />

      <section v-if="runtimeSettings && options" ref="runtimePanel" class="runtime-sheet" tabindex="-1" aria-label="播放中设置">
        <div class="runtime-inner">
          <div class="runtime-heading"><div><h2>播放中设置</h2><p>播放已暂停，关闭设置后点击继续。图库、顺序与每轮数量请返回列表修改。</p></div><button class="secondary" @click="closeSettings">完成设置</button></div>
          <PlaybackSettings v-model="options" runtime />
          <p v-if="settingsError" class="notice error" role="alert">{{ settingsError }}</p>
        </div>
      </section>
    </div>
    <PlaybackGuide :steps="guideSteps" :open="guideOpen" @close="closeGuide" />
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
.runtime-heading h2 { margin: 0 0 16px; font-size: 20px; }
.configuration-management { margin: 24px 0; }
.configuration-management summary { min-height: 44px; cursor: pointer; }
.configuration-management p { font-size: 14px; line-height: 1.6; }
.configuration-actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 16px; }
.playback-start { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.rhythm-player { background: #000; color: #fff; border-radius: 18px; overflow: hidden; max-width: 1200px; margin: 0 auto; }
.runtime-settings { background: var(--color-canvas); color: var(--color-ink); padding: 24px; overflow-y: auto; min-height: 0; }
.runtime-heading { display: flex; justify-content: space-between; align-items: start; gap: 20px; margin-bottom: 24px; }
.runtime-heading p { font-size: 14px; color: var(--color-muted); max-width: 560px; }
.runtime-heading button { flex-shrink: 0; }
.rhythm-player:fullscreen { display: flex; flex-direction: column; width: 100%; height: 100%; max-width: none; border-radius: 0; padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left); }
.player-top { display: flex; align-items: center; gap: 16px; min-height: 56px; padding: 4px 12px; }
.player-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; color: #dccbd3; }
.player-button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 44px; min-width: 44px; padding: 8px 12px; border-radius: 8px; font-size: 14px; white-space: nowrap; color: #fff; }
.player-button:hover:not(:disabled) { background: #272729; }
.player-button:focus-visible { outline-color: var(--color-primary-on-dark); }
.previous-icon { transform: rotate(180deg); }
.media-stage { position: relative; height: clamp(240px, 57dvh, 800px); min-height: 0; background: #000; }
:fullscreen .media-stage { flex: 1; height: auto; }
.image-viewport { width: 100%; height: 100%; overflow: hidden; touch-action: pan-y pinch-zoom; cursor: pointer; user-select: none; }
.image-viewport.zoomed { overflow: auto; touch-action: none; cursor: grab; }
.image-viewport.zoomed:active { cursor: grabbing; }
.image-canvas { display: grid; place-items: center; }
.image-canvas img { display: block; width: 100%; height: 100%; object-fit: contain; min-width: 0; min-height: 0; }
.media-stage video { width: 100%; height: 100%; object-fit: contain; display: block; }
.media-loading { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #dccbd3; pointer-events: none; font-size: 14px; }
.media-message { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; background: #000e; padding: 24px; text-align: center; }
.media-message > p { max-width: 560px; }
.media-message > div { display: flex; gap: 16px; }
.player-bottom { padding: 12px 20px 16px; }
.rhythm-status { display: flex; align-items: center; gap: 10px; min-height: 36px; font-size: 14px; }
.rhythm-status > span:not(.beat-dot) { color: #dccbd3; }
.rhythm-status time { margin-left: auto; font-variant-numeric: tabular-nums; font-size: 20px; }
.beat-dot { width: 10px; height: 10px; background: #735d69; border-radius: 50%; transition: background-color .1s; }
.beat-dot.pulse { background: var(--color-primary-on-dark); }
.player-bottom progress { height: 3px; margin: 8px 0 12px; }
.player-file { display: flex; gap: 16px; align-items: center; font-size: 14px; color: #dccbd3; }
.player-file > span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.player-file small { white-space: nowrap; font-variant-numeric: tabular-nums; }
.player-controls { display: flex; justify-content: center; align-items: center; gap: 8px; margin-top: 12px; }
.main-play { background: var(--color-primary); border-radius: 50%; width: 52px; height: 52px; }
.main-play:hover:not(:disabled) { background: var(--color-primary-focus); }
.control-divider { height: 24px; width: 1px; background: #5c4652; margin: 0 8px; }
.liked { color: var(--color-primary-on-dark); }
.liked :deep(svg) { fill: currentColor; }
.image-controls { display: flex; justify-content: center; align-items: center; gap: 12px; margin-top: 8px; }
.image-controls label { flex-direction: row; align-items: center; color: #dccbd3; white-space: nowrap; }
.image-controls .interval-control input { width: 72px; min-height: 44px; background: #272729; border-color: #5c4652; color: #fff; padding: 6px 8px; text-align: center; }
.image-controls select { width: auto; min-height: 44px; background-color: #272729; border-color: #5c4652; color: #fff; }
.zoom-controls { display: flex; align-items: center; gap: 0; }
.zoom-controls button { font-variant-numeric: tabular-nums; padding-inline: 8px; }
.player-note { margin-top: 8px; text-align: center; color: #dccbd3; font-size: 14px; }
.player-help { margin-top: 12px; color: #dccbd3; font-size: 14px; }
.player-help summary { min-height: 44px; padding: 12px 0; cursor: pointer; }
.player-help ul { padding-left: 20px; line-height: 1.7; }
@media (max-width: 600px) {
  .setup-summary { align-items: stretch; flex-direction: column; gap: 16px; padding: 16px; }
  .runtime-settings { padding: 16px; }
  .runtime-heading { flex-wrap: wrap; gap: 8px; }
  .playlist-picker { gap: 10px; }
  .media-types { width: 100%; }
  .media-types label { flex: 1; justify-content: center; padding-inline: 12px; }
  .gallery-choices label { gap: 10px; padding-inline: 6px; }
  .gallery-choices label > svg { display: none; }
  .rhythm-player { margin-inline: -12px; border-radius: 12px; }
  .media-stage { height: max(180px, calc(100svh - 450px)); }
  :fullscreen .media-stage { height: auto; }
  .player-top { gap: 4px; padding-inline: 4px; }
  .player-top > button { gap: 4px; padding-inline: 8px; }
  .player-bottom { padding-inline: 12px; }
  .player-controls { gap: 4px; }
  .control-divider { margin-inline: 2px; }
  .stop-button { padding-inline: 8px; }
  .image-controls { gap: 6px; flex-wrap: wrap; }
  .image-controls label { gap: 6px; }
  .image-controls .interval-control input { width: 68px; }
  .zoom-controls button { min-width: 44px; padding-inline: 5px; }
}
@media (max-width: 380px) { .favorite-label { display: none; } }
@media (max-height: 500px) and (min-width: 601px) {
  .rhythm-player, .rhythm-player:fullscreen { position: fixed; inset: 0; z-index: 30; display: grid; grid-template-columns: minmax(0, 1fr) 330px; grid-template-rows: 56px minmax(0, 1fr); height: 100dvh; max-width: none; margin: 0; border-radius: 0; }
  .player-top, .runtime-settings { grid-column: 1 / -1; }
  .media-stage { height: 100%; }
  .player-bottom { overflow-y: auto; padding: 8px 12px; }
  .image-controls { flex-wrap: wrap; }
}
.playback-runtime { position: fixed; inset: 0; z-index: 60; color: #fff; outline: none; }
.playback-runtime:fullscreen { inset: 0; width: 100%; height: 100%; background: #000; }
.playback-media { position: absolute; inset: 0; overflow: hidden; }
.playback-media .image-viewport { width: 100%; height: 100%; }
.playback-media video { display: block; width: 100%; height: 100%; object-fit: contain; }
.runtime-sheet { position: fixed; inset: 0; z-index: 70; overflow-y: auto; background: var(--color-canvas); color: var(--color-ink); padding: max(16px, env(safe-area-inset-top)) max(16px, env(safe-area-inset-right)) 48px max(16px, env(safe-area-inset-left)); }
.runtime-inner { max-width: 920px; margin: 0 auto; }
@media (prefers-reduced-motion: reduce) { .beat-dot { transition: none; } .beat-dot.pulse { background: #735d69; } }
</style>
