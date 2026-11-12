<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { api } from './api'
import Icon from './Icon.vue'
import { clockTime, mediaKey, mediaUrl, newPlaylist, orderedMedia, playbackStorageKey, readPreferences, validPlaylist,
  type Gallery, type PlaybackMedia, type PlaybackPreferences, type Playlist } from './playback'

const preferences = reactive<PlaybackPreferences>({ playlists: [], selected: '', favorites: [] })
const setupModel = reactive({ galleries: [] as Gallery[], loading: false, starting: false, error: '', storageError: '', storageBlocked: false, ready: false })
const playlist = computed(() => preferences.playlists.find(item => item.id === preferences.selected))
const queue = shallowRef<PlaybackMedia[]>([])
const player = reactive({ mode: 'setup' as 'setup' | 'playing' | 'finished', index: 0, paused: false, ready: false,
  error: '', note: '', elapsed: 0, imageElapsed: 0, phaseElapsed: 0, phaseDuration: 24000, phase: 0, autoImages: true,
  imageSeconds: 8, zoom: 1, fullscreen: false, finishedReason: '', beat: false })
const options = shallowRef<Playlist>()
const phases = [{ label: '慢速', ratio: .6 }, { label: '快速', ratio: 1 }, { label: '休息', ratio: 0 }]
const current = computed(() => queue.value[player.index])
const phase = computed(() => phases[player.phase]!)
const bpm = computed(() => Math.round((options.value?.bpm || 100) * phase.value.ratio))
const favorite = computed(() => !!current.value && preferences.favorites.includes(mediaKey(current.value)))
const active = computed(() => player.mode === 'playing' && !player.paused && player.ready && !player.error)
const remaining = computed(() => Math.max(0, (options.value?.minutes || 0) * 60000 - player.elapsed))
const playerElement = ref<HTMLElement>()
const imageViewport = ref<HTMLElement>()
const video = ref<HTMLVideoElement>()
const controls = ref<HTMLButtonElement>()
let request = new AbortController()
let timer: ReturnType<typeof setInterval>
let previousTick = 0
let nextBeat = 0
let audio: AudioContext | undefined
let disposed = false
let pointer: { id: number; x: number; y: number; left: number; top: number; moved: boolean } | undefined
let suppressClick = false

function persist() {
  if (!setupModel.ready || setupModel.storageBlocked) return
  if (!preferences.playlists.every(validPlaylist)) {
    setupModel.storageError = '播放列表有尚未填完的名称或设置，修正后会自动保存。'; return
  }
  try { localStorage.setItem(playbackStorageKey, JSON.stringify(preferences)); setupModel.storageError = '' }
  catch { setupModel.storageError = '无法保存到本机，请检查浏览器存储空间或隐私设置；当前编辑仍可用于播放。' }
}
watch(preferences, persist, { deep: true })
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
  preferences.playlists = []; preferences.selected = ''; preferences.favorites = []
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
  if (!options.value?.metronome) return
  try {
    audio ||= new AudioContext()
    if (audio.state === 'suspended') await audio.resume()
  } catch { player.note = '节拍器无法启用，可检查浏览器声音权限，或关闭节拍器继续。' }
}
function speak() {
  if (!options.value?.speech || !('speechSynthesis' in window)) return
  speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(phase.value.label)
  utterance.lang = 'zh-CN'; utterance.rate = .95
  utterance.onerror = event => { if (!['canceled', 'interrupted'].includes(event.error) && !disposed) player.note = '语音提示不可用，请检查系统中文语音和浏览器权限。' }
  speechSynthesis.speak(utterance)
}
function silence() {
  nextBeat = 0; player.beat = false
  if ('speechSynthesis' in window && options.value?.speech) speechSynthesis.cancel()
}
function beat(now: number) {
  if (!bpm.value) { player.beat = false; return }
  if (now < nextBeat) { player.beat = nextBeat - now > 60000 / bpm.value - 120; return }
  nextBeat = now + 60000 / bpm.value; player.beat = true
  if (!options.value?.metronome || audio?.state !== 'running') return
  const oscillator = audio.createOscillator(), gain = audio.createGain()
  oscillator.frequency.value = 660
  gain.gain.setValueAtTime(.055, audio.currentTime)
  gain.gain.exponentialRampToValueAtTime(.001, audio.currentTime + .045)
  oscillator.connect(gain); gain.connect(audio.destination)
  oscillator.start(); oscillator.stop(audio.currentTime + .05)
  oscillator.onended = () => { oscillator.disconnect(); gain.disconnect() }
}
async function start() {
  if (!playlist.value || setupModel.starting) return
  setupModel.error = ''
  const item = playlist.value
  if (!item.roots.length) { setupModel.error = '请至少勾选一个图库。'; return }
  if (item.roots.some(id => !setupModel.galleries.some(gallery => gallery.id === id))) {
    setupModel.error = '列表包含已移除的图库，请取消勾选后重新开始。'; return
  }
  if (!validPlaylist(item)) {
    setupModel.error = '请填写列表名称，并检查图片间隔（1–300 秒）、总时长（0–180 分钟）和快速节拍（30–180 BPM），数值请使用整数。'; return
  }
  setupModel.starting = true
  player.note = ''
  options.value = { ...item, roots: item.roots.slice() }
  // Unlock audio while the start button's user activation is still available.
  void prepareAudio()
  try {
    const result = await api<{ items: PlaybackMedia[] }>('/playback/queue', { roots: item.roots, kind: item.kind }, 'POST', request.signal)
    if (disposed) return
    const items = item.favoritesOnly ? result.items.filter(media => preferences.favorites.includes(mediaKey(media))) : result.items
    if (!items.length) { setupModel.error = item.favoritesOnly ? '所选图库中没有符合类型的喜欢收藏，可关闭“仅播放喜欢”。' : '所选图库中没有符合类型的媒体，请调整图库或媒体类型。'; return }
    queue.value = orderedMedia(items, item.order)
    Object.assign(player, { mode: 'playing', index: 0, paused: document.hidden, ready: false, error: '', elapsed: 0, imageElapsed: 0,
      phaseElapsed: 0, phaseDuration: 24000, phase: 0, autoImages: true, imageSeconds: item.imageSeconds, zoom: 1, finishedReason: '', beat: false })
    previousTick = performance.now(); nextBeat = 0
    if (item.speech && !('speechSynthesis' in window)) player.note = '当前浏览器不支持语音提示。'
    await nextTick(); controls.value?.focus(); if (!player.paused) speak()
  } catch (error) { if (!disposed) setupModel.error = (error as Error).message }
  finally { if (!disposed) setupModel.starting = false }
}
function pause() {
  if (player.mode !== 'playing') return
  player.paused = true; video.value?.pause(); silence()
}
async function resume() {
  if (player.mode !== 'playing' || player.error) return
  player.paused = false; player.note = ''; previousTick = performance.now()
  await prepareAudio()
  if (current.value?.kind === 'video') await playVideo()
  if (!player.paused) speak()
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
function finish(reason: string) {
  pause(); player.mode = 'finished'; player.finishedReason = reason; player.error = ''
}
function step(delta: number) {
  if (player.mode !== 'playing') return
  let target = player.index + delta
  if (target >= queue.value.length) {
    if (!options.value?.loop) { finish('已播放完列表'); return }
    target = 0
  } else if (target < 0) target = options.value?.loop ? queue.value.length - 1 : 0
  if (target === player.index && queue.value.length > 1) return
  if (queue.value.length === 1 && player.error) { retryMedia(); return }
  const ready = player.ready
  player.index = target; player.imageElapsed = 0; player.zoom = 1; player.error = ''; player.ready = false
  void nextTick(() => {
    imageViewport.value?.scrollTo(0, 0)
    // A single-item loop retains its DOM element.
    if (queue.value.length === 1) {
      if (video.value) { video.value.currentTime = 0; player.ready = video.value.readyState >= 2; void playVideo() }
      else player.ready = ready
    }
  })
}
function changePhase() {
  const candidates = [0, 1, 2].filter(value => value !== player.phase)
  player.phase = candidates[Math.floor(Math.random() * candidates.length)]!
  player.phaseElapsed = 0; nextBeat = 0
  player.phaseDuration = (player.phase === 2 ? 10 + Math.random() * 6 : 18 + Math.random() * 13) * 1000
  speak()
}
function tick() {
  const now = performance.now(), elapsed = now - previousTick
  previousTick = now
  if (!active.value) return
  player.elapsed += elapsed; player.phaseElapsed += elapsed
  if (options.value?.minutes && remaining.value <= 0) { finish('本次计时已完成'); return }
  if (player.phaseElapsed >= player.phaseDuration) changePhase()
  beat(now)
  if (current.value?.kind === 'image' && player.autoImages) {
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
  if (event.currentTarget === imageViewport.value?.querySelector('img')) player.ready = true
}
function videoStarted(event: Event) {
  if (event.currentTarget !== video.value) return
  if (player.mode !== 'playing' || document.hidden) { video.value?.pause(); return }
  if (player.paused) {
    player.paused = false; player.note = ''; previousTick = performance.now()
    void prepareAudio(); speak()
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
  if (event.currentTarget === video.value) player.ready = event.type === 'canplay'
}
function retryMedia() {
  player.error = ''; player.ready = false
  if (video.value) video.value.load()
  else {
    const image = imageViewport.value?.querySelector('img')
    if (image && current.value) image.src = mediaUrl(current.value)
  }
}
function updateInterval(event: Event) {
  const input = event.target as HTMLInputElement
  const seconds = Number(input.value)
  if (!Number.isInteger(seconds) || seconds < 1 || seconds > 300) {
    player.note = '图片间隔请输入 1–300 之间的整数秒。'; input.value = String(player.imageSeconds); return
  }
  player.imageSeconds = seconds; player.imageElapsed = 0; player.note = ''
  const saved = preferences.playlists.find(item => item.id === options.value?.id)
  if (saved) saved.imageSeconds = seconds
}
function toggleFavorite() {
  if (!current.value) return
  const key = mediaKey(current.value)
  preferences.favorites = favorite.value ? preferences.favorites.filter(value => value !== key) : [...preferences.favorites, key]
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
function backToLists() {
  pause(); player.mode = 'setup'; queue.value = []; player.error = ''; player.note = ''
  if (document.fullscreenElement === playerElement.value) void document.exitFullscreen()
}
function keydown(event: KeyboardEvent) {
  if (player.mode !== 'playing' || event.altKey || event.ctrlKey || event.metaKey
    || (event.target as HTMLElement).closest('input,select,textarea,video,[contenteditable]')) return
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
  previousTick = performance.now(); timer = setInterval(tick, 100)
  document.addEventListener('keydown', keydown)
  document.addEventListener('visibilitychange', visibilityChanged)
  document.addEventListener('fullscreenchange', fullscreenChanged)
})
onBeforeUnmount(() => {
  disposed = true; request.abort(); clearInterval(timer); pause()
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
        <fieldset :disabled="setupModel.starting" class="playlist-fields">
          <label class="playlist-name">名称<input v-model.trim="playlist.name" maxlength="80" required /></label>
          <fieldset class="media-types"><legend>播放内容</legend><label v-for="choice in ([['mixed', '混合'], ['image', '仅图片'], ['video', '仅视频']] as const)" :key="choice[0]" :class="{ chosen: playlist.kind === choice[0] }"><input v-model="playlist.kind" type="radio" name="media-kind" :value="choice[0]" />{{ choice[1] }}</label></fieldset>
          <div class="gallery-heading"><span>图库</span><button class="text-button" type="button" :disabled="setupModel.loading" @click="loadGalleries"><Icon name="refresh" :size="16" />{{ setupModel.loading ? '正在刷新…' : '刷新' }}</button></div>
          <p v-if="setupModel.loading && !setupModel.galleries.length" class="muted" role="status">正在读取图库…</p>
          <div class="gallery-choices"><label v-for="gallery in setupModel.galleries" :key="gallery.id" :class="{ chosen: playlist.roots.includes(gallery.id) }"><input type="checkbox" :checked="playlist.roots.includes(gallery.id)" @change="checkGallery(gallery.id, ($event.target as HTMLInputElement).checked)" /><Icon name="folder" :size="22" /><span><strong>{{ galleryName(gallery) }}</strong><small>{{ gallery.path }}</small></span></label><label v-for="id in playlist.roots.filter(id => !setupModel.galleries.some(gallery => gallery.id === id))" :key="id" class="missing-gallery"><input type="checkbox" checked @change="checkGallery(id, false)" /><span>图库已移除，取消勾选后可继续</span></label></div>
          <p class="gallery-help muted">包含子目录。其他图库可在小米云相册中绑定本地目录后选择。</p>
          <details class="playback-settings"><summary>播放设置</summary><div class="settings-grid">
            <label>播放顺序<select v-model="playlist.order"><option value="shuffle">随机</option><option value="sequential">文件名顺序</option></select></label>
            <label>图片间隔（秒）<input v-model.number="playlist.imageSeconds" type="number" min="1" max="300" required /></label>
            <label>总时长（分钟，0 为不限）<input v-model.number="playlist.minutes" type="number" min="0" max="180" required /></label>
            <label>快速节拍（BPM）<input v-model.number="playlist.bpm" type="number" min="30" max="180" required /></label>
          </div><div class="playback-toggles"><label><input v-model="playlist.loop" type="checkbox" />循环列表</label><label><input v-model="playlist.favoritesOnly" type="checkbox" />仅播放喜欢</label><label><input v-model="playlist.metronome" type="checkbox" />节拍器</label><label><input v-model="playlist.speech" type="checkbox" />语音提示</label></div></details>
        </fieldset>
        <p v-if="setupModel.error" class="notice error" role="alert">{{ setupModel.error }}</p>
        <div class="playback-start"><span class="muted">已选 {{ playlist.roots.length }} 个图库</span><button class="primary" :disabled="setupModel.loading || setupModel.starting || !playlist.roots.length"><Icon :name="setupModel.starting ? 'loader' : 'play'" :size="18" />{{ setupModel.starting ? '正在读取媒体…' : '开始播放' }}</button></div>
      </template>
    </form>

    <section v-else ref="playerElement" class="rhythm-player" aria-label="媒体播放器">
      <div class="player-top"><button class="player-button" @click="backToLists"><Icon name="chevron" class="previous-icon" :size="18" />播放列表</button><span class="player-name">{{ options?.name }}</span><button class="player-button" @click="fullscreen"><Icon name="fullscreen" :size="19" /><span>{{ player.fullscreen ? '退出全屏' : '全屏' }}</span></button></div>
      <div class="media-stage">
        <div v-if="current?.kind === 'image'" ref="imageViewport" class="image-viewport" :class="{ zoomed: player.zoom > 1 }" @pointerdown="pointerDown" @pointermove="pointerMove" @pointerup="pointerUp" @pointercancel="pointer = undefined; suppressClick = true" @click="imageClick">
          <div class="image-canvas" :style="{ width: `${player.zoom * 100}%`, height: `${player.zoom * 100}%` }"><img :key="mediaKey(current)" :src="mediaUrl(current)" :alt="current.name" draggable="false" @load="imageLoaded" @error="mediaFailed" /></div>
        </div>
        <video v-else-if="current" :key="mediaKey(current)" ref="video" :src="mediaUrl(current)" controls playsinline preload="metadata" @loadedmetadata="$event.currentTarget === video && playVideo()" @canplay="videoReady" @play="videoStarted" @playing="videoPlaying" @waiting="videoReady" @pause="videoPaused" @ended="$event.currentTarget === video && step(1)" @error="mediaFailed" />
        <p v-if="!player.ready && !player.error && player.mode === 'playing'" class="media-loading" role="status">正在加载{{ current?.kind === 'video' ? '视频' : '图片' }}…</p>
        <div v-if="player.error" class="media-message" role="alert"><Icon name="file" :size="30" /><p>{{ player.error }}</p><div><button class="player-button" @click="retryMedia">重新加载</button><button class="player-button" @click="step(1)">下一项</button></div></div>
        <div v-else-if="player.mode === 'finished'" class="media-message finished-message"><Icon name="check" :size="32" /><h2>{{ player.finishedReason }}</h2><p>本次播放 {{ clockTime(player.elapsed) }}</p><button class="primary" @click="backToLists">返回播放列表</button></div>
      </div>
      <div class="player-bottom">
        <div class="rhythm-status"><span class="beat-dot" :class="{ pulse: active && player.beat }" aria-hidden="true"></span><strong aria-live="polite">{{ player.mode === 'finished' ? '已结束' : player.paused ? '已暂停' : phase.label }}</strong><span>{{ bpm ? `${bpm} BPM` : '放松片刻' }}</span><time :aria-label="options?.minutes ? '剩余时间' : '已播放时间'">{{ options?.minutes ? clockTime(remaining) : clockTime(player.elapsed) }}</time></div>
        <progress v-if="options?.minutes" :value="player.elapsed" :max="options.minutes * 60000" aria-label="本次播放进度" />
        <div class="player-file"><span :title="current?.path">{{ current?.name }}</span><small>{{ player.index + 1 }} / {{ queue.length }}</small></div>
        <div class="player-controls"><button class="player-button" :disabled="player.mode !== 'playing' || (!options?.loop && player.index === 0)" aria-label="上一项" title="上一项（←）" @click="step(-1)"><Icon name="chevron" class="previous-icon" /></button><button ref="controls" class="player-button main-play" :disabled="player.mode !== 'playing' || !!player.error" :aria-label="player.paused ? '继续播放' : '暂停播放'" @click="player.paused ? resume() : pause()"><Icon :name="player.paused ? 'play' : 'pause'" :size="24" /></button><button class="player-button" :disabled="player.mode !== 'playing'" aria-label="下一项" title="下一项（→）" @click="step(1)"><Icon name="chevron" /></button><span class="control-divider"></span><button class="player-button" :class="{ liked: favorite }" :aria-pressed="favorite" :aria-label="favorite ? '取消喜欢' : '喜欢'" @click="toggleFavorite"><Icon name="heart" /><span class="favorite-label">{{ favorite ? '已喜欢' : '喜欢' }}</span></button><button class="player-button stop-button" :disabled="player.mode !== 'playing'" @click="finish('已结束播放')">结束</button></div>
        <div v-if="current?.kind === 'image' && player.mode === 'playing'" class="image-controls"><label><input v-model="player.autoImages" type="checkbox" @change="player.imageElapsed = 0; player.zoom = 1" />自动切图</label><label class="interval-control"><input :value="player.imageSeconds" type="number" min="1" max="300" aria-label="自动切图间隔（秒）" @change="updateInterval" />秒</label><span class="zoom-controls"><button class="player-button" :disabled="player.zoom <= 1" aria-label="缩小图片" @click="zoom(-.5)">−</button><button class="player-button" title="还原图片" @click="zoom(0)">{{ Math.round(player.zoom * 100) }}%</button><button class="player-button" :disabled="player.zoom >= 4" aria-label="放大图片" @click="zoom(.5)">＋</button></span></div>
        <p v-if="player.note" class="player-note" role="status">{{ player.note }}</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.playlist-editor { max-width: 920px; margin: 0 auto; }
.playlist-picker { display: flex; align-items: end; gap: 16px; margin-bottom: 24px; }
.playlist-picker > label { flex: 1; min-width: 0; }
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
.playback-settings { margin: 24px 0; border-block: 1px solid var(--color-hairline); }
.playback-settings summary { padding: 16px 0; cursor: pointer; font-size: 14px; }
.settings-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.playback-toggles { display: flex; flex-wrap: wrap; gap: 16px 24px; margin: 20px 0; }
.playback-toggles label { flex-direction: row; align-items: center; min-height: 44px; }
.playback-start { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.rhythm-player { background: #000; color: #fff; border-radius: 18px; overflow: hidden; max-width: 1200px; margin: 0 auto; }
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
.zoom-controls { display: flex; align-items: center; gap: 0; }
.zoom-controls button { font-variant-numeric: tabular-nums; padding-inline: 8px; }
.player-note { margin-top: 8px; text-align: center; color: #dccbd3; font-size: 14px; }
@media (max-width: 600px) {
  .playlist-picker { gap: 10px; }
  .media-types { width: 100%; }
  .media-types label { flex: 1; justify-content: center; padding-inline: 12px; }
  .gallery-choices label { gap: 10px; padding-inline: 6px; }
  .gallery-choices label > svg { display: none; }
  .settings-grid { grid-template-columns: 1fr; }
  .rhythm-player { margin-inline: -12px; border-radius: 12px; }
  .player-top { gap: 4px; padding-inline: 4px; }
  .player-top > button { gap: 4px; padding-inline: 8px; }
  .player-bottom { padding-inline: 12px; }
  .player-controls { gap: 4px; }
  .control-divider { margin-inline: 2px; }
  .stop-button { padding-inline: 8px; }
  .image-controls { gap: 6px; flex-wrap: wrap; }
  .image-controls label { gap: 6px; }
  .image-controls .interval-control input { width: 52px; }
  .zoom-controls button { min-width: 44px; padding-inline: 5px; }
}
@media (max-width: 380px) { .favorite-label { display: none; } }
@media (prefers-reduced-motion: reduce) { .beat-dot { transition: none; } .beat-dot.pulse { background: #735d69; } }
</style>
