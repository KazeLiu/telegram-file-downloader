<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { newPlaylist } from './playback'
import type { Playlist } from './playback'
import { commandPoolNotice, settingsSummary } from './playback/summary'
import {
  adjustMix, beatVolumeMax, bpmRandomMax, bpmRandomMin, categoryHints, categoryLabels, categoryOrder,
  textOpacityMin, textScaleMax, textScaleMin, formatClock,
  customCommandLimit, customCommandTextLimit, difficultyHints, difficultyLabels, difficultyOrder,
  durationMax, durationMin, extendLengthLabels, extendLengthOrder, finaleHints, finaleLabels, finaleOrder, instructionLengthLabels,
  instructionLengthOrder, mixOf, modeColors, modeLabels, modeOrder, presetLabels, presetNone, presetNotes, presets, presetOrder,
  randomTimeNote,
  redBeatLabels, redBeatOrder, restMax, restMin, restModeLabels, restModeOrder, restRangeChoices,
  rewardChoices, toneAfterLabels, toneAfterOrder, difficulties, permitRate,
  toneLabels, toneOrder,
  type Difficulty, type EdgeMode,
} from './playback/engine'
import { maleCommands } from './playback/commands'
import { defaultEdgeSettings, readEdgeSettings } from './playback/settings'
import { toneNotes } from './playback/tones'
import { focusAreas, focusLabels, focusLegend, focusNotes, focusSectionsOff } from './playback/focus'
import {
  MIRROR_CONSTRAINTS, classifyMirrorError, mirrorErrorLabels, mirrorPlaceLabels, mirrorPlaces, mirrorSupport, mirrorText,
  stopStream, type MirrorError
} from './playback/mirror'
import { emptyLost, emptyStats, lostStorageKey, readLost, readStats, statsStorageKey, statsSummary } from './playback/history'
import { daysStorageKey, daysSummary, emptyDays, readDays } from './playback/days'
import PlaybackHistory from './playback/PlaybackHistory.vue'
import { readTally, recordsText, tallyStorageKey } from './playback/records'
import type { EdgeSettings } from './playback/settings'

const settings = defineModel<EdgeSettings>({ required: true })
const props = defineProps<{ runtime?: boolean; media?: Playlist }>()

const selected = ref('play')
const search = ref('')
// 分组顺序对齐参考站：玩法 / 指令 / 视频·图片 / 声音 / 其他。
const groups = computed(() => [
  { id: 'play', label: '玩法', keywords: '推荐 第一次 标准 慢慢来 时间 分钟 随机 难度 简单 普通 困难 地狱 许可率 自己调 混合 可以撸 慢慢来 不许碰 结局 抽签 必定 松手 连续 加时 允许射精 秒 等待 随机 固定 指令时长 较长 很长 乳头 龟头 整局 单部位 一个部位 focus' },
  { id: 'command', label: '指令', keywords: '分类 寸止 挑逗 姿势 羞耻 轻度疼痛 惯用手 左右手 自定义 口令 启停 禁用 口吻 强势 挑逗 羞辱 温柔 足控 短句' },
  { id: 'media', label: '视频·图片', keywords: '视频 图片 混合 仅图片 仅视频 顺序 随机 文件名 每轮 数量 间隔 切图 BPM 循环 喜欢 收藏' },
  { id: 'sound', label: '声音', keywords: '节拍 音量 心跳 红 媒体 视频 音量 变暗 混音' },
  { id: 'other', label: '其他', keywords: '隐藏 剩余 时间 进度 画面 亮度 变暗 混音 镜子 摄像头 前置 相机 mirror' },
])
const visible = computed(() => groups.value.filter(group => (search.value.trim()
  ? `${group.label} ${group.keywords}`.toLowerCase().includes(search.value.trim().toLowerCase())
  : group.id === selected.value) && !(props.runtime && group.id === 'media')))
const summary = computed(() => settingsSummary(settings.value))
const poolNotice = computed(() => commandPoolNotice(settings.value))
const activeTones = computed(() => toneOrder.filter(key => settings.value.tones[key]))
const activeToneCount = computed(() => activeTones.value.length)

/** 本机成绩：只读给设置页顶部那行看，清除要再点一次确认。 */
const stats = ref(readStats(typeof localStorage === 'undefined' ? null : localStorage.getItem(statsStorageKey)))
const statsLine = computed(() => statsSummary(stats.value))
/** 「射了」的记录：中途结束次数与最长坚持（只存在本机）。 */
const lost = ref(readLost(typeof localStorage === 'undefined' ? null : localStorage.getItem(lostStorageKey)))
/** 连续天数：顶部那几行「已连续 N 天 · 下一个目标」。 */
const days = ref(readDays(typeof localStorage === 'undefined' ? null : localStorage.getItem(daysStorageKey)))
const dayLines = computed(() => daysSummary(days.value))
const lostLine = computed(() => (lost.value.count
  ? `中途结束 ${lost.value.count} 次 · 最长坚持 ${formatClock(lost.value.bestMs)}（只存在这台设备里）`
  : ''))
const history = ref<InstanceType<typeof PlaybackHistory>>()
const historyOpen = ref(false)
/** 累计局数（顶部「记录 N」按钮上的数字）：只读一次，打开弹窗时再刷新。 */
function historyNumber() {
  if (typeof localStorage === 'undefined') return 0
  return readTally(localStorage.getItem(tallyStorageKey)).n
}
const historyCount = ref(historyNumber())
function openHistory() {
  history.value?.reload()
  historyCount.value = historyNumber()
  historyOpen.value = true
}
const statsArmed = ref(false)
function clearStats() {
  if (!statsArmed.value) { statsArmed.value = true; return }
  statsArmed.value = false
  try { localStorage.setItem(statsStorageKey, JSON.stringify(emptyStats)) } catch { /* 存不进去就当没清 */ }
  try { localStorage.setItem(lostStorageKey, JSON.stringify(emptyLost)) } catch { /* 同上 */ }
  try { localStorage.setItem(daysStorageKey, JSON.stringify(emptyDays)) } catch { /* 同上 */ }
  stats.value = { ...emptyStats }
  lost.value = { ...emptyLost }
  days.value = { ...emptyDays }
}

function selectGroup(id: string) {
  selected.value = id
  search.value = ''
  resetArmed.value = false
}

/** 与默认设置不同的项目数：参考站顶部那行「与默认不同的项目：N」。 */
const changedCount = computed(() => {
  const base = defaultEdgeSettings as unknown as Record<string, unknown>
  const current = settings.value as unknown as Record<string, unknown>
  return Object.keys(base).filter((key) => {
    if (key === 'custom' || key === 'seed') return false
    return JSON.stringify(base[key]) !== JSON.stringify(current[key])
  }).length
})
const allArmed = ref(false)
const resetDone = ref(false)
watch(settings, () => { allArmed.value = false; resetDone.value = false }, { deep: true, flush: 'sync' })
/** 参考站是先弹出确认条再执行，所以按钮本身只负责展开确认条。 */
function askResetAll() {
  resetDone.value = false
  allArmed.value = true
}
/** 恢复全部默认：保留自己的指令（与参考站的恢复默认一致）。 */
function resetAll() {
  allArmed.value = false
  const keep = settings.value.custom.map(item => ({ ...item }))
  Object.assign(settings.value, { ...defaultEdgeSettings, custom: keep, seed: settings.value.seed, tune: { chance: null, stop: null, mix: null } })
  resetDone.value = true
}

// 「恢复本组」要求再点一次确认，避免误触清掉还没记住的设置。
const resetArmed = ref(false)
const canReset = computed(() => !search.value.trim() && visible.value.length === 1)
const resetLabel = computed(() => resetArmed.value ? '确认恢复？' : '恢复本组')
watch([selected, search], () => { resetArmed.value = false })
watch(settings, () => { resetArmed.value = false }, { deep: true })
function resetGroup() {
  if (!resetArmed.value) { resetArmed.value = true; return }
  resetArmed.value = false
  draftCommand.value = ''
  const item = settings.value
  const base = defaultEdgeSettings
  if (selected.value === 'play') {
    item.minutes = base.minutes
    item.durationRandom = base.durationRandom
    item.difficulty = base.difficulty
    item.instructionLength = base.instructionLength
    item.finale = base.finale
    item.tune = { chance: null, stop: null, mix: null }
    item.allowRuin = base.allowRuin
    item.extendLen = base.extendLen
    item.rewardSeconds = base.rewardSeconds
    item.rest = { ...base.rest }
    item.nipple = { ...base.nipple }
    item.glans = { ...base.glans }
    item.focus = base.focus
    item.toy = base.toy
    item.aneros = base.aneros
  } else if (selected.value === 'command') {
    item.categories = { ...base.categories }
    item.hand = base.hand
    item.custom.splice(0, item.custom.length)
    item.disabled.splice(0, item.disabled.length)
    item.tones = { ...base.tones }
    item.toneLine = { ...base.toneLine }
    item.bpm = {}
  } else if (selected.value === 'media') {
    const defaults = newPlaylist()
    const media = props.media
    if (media) {
      media.order = defaults.order
      media.imageCount = defaults.imageCount
      media.imageTiming = defaults.imageTiming
      media.imageSeconds = defaults.imageSeconds
      media.bpm = defaults.bpm
      media.loop = defaults.loop
      media.favoritesOnly = defaults.favoritesOnly
    }
    item.keepVideoOnStop = base.keepVideoOnStop
    item.switchVideoPerCommand = base.switchVideoPerCommand
    item.keepVideoWhileCooling = base.keepVideoWhileCooling
    item.fit = base.fit
    item.pos = base.pos
    item.textOpacity = base.textOpacity
    item.textScale = base.textScale
    item.videoSound = base.videoSound
    item.skipIntro = base.skipIntro
  } else if (selected.value === 'sound') {
    item.metronome = base.metronome
    item.beatVolume = base.beatVolume
    item.redBeat = base.redBeat
    item.heartbeat = base.heartbeat
    item.heartbeatVolume = base.heartbeatVolume
    item.mediaVolume = base.mediaVolume
    item.bpmRandom = { ...base.bpmRandom }
    item.heartbeatSync = base.heartbeatSync
    item.vibrate = base.vibrate
    item.vibrateOn = { ...base.vibrateOn }
  } else {
    item.hideRemaining = base.hideRemaining
    item.pipOffer = base.pipOffer
    item.pipSite = base.pipSite
    item.dim = base.dim
    item.mixAudio = base.mixAudio
    item.mirror = { ...base.mirror }
  }
}

// 每次变换节奏的上下限：20～300，按 5 取整。
function clampBpm(value: string, fallback: number) {
  const parsed = Math.round(Number(value))
  if (!Number.isFinite(parsed)) return fallback
  return Math.min(bpmRandomMax, Math.max(bpmRandomMin, 5 * Math.round(parsed / 5)))
}

// 当前命中哪一档推荐预设（没有命中就是「自定义设置」）。
const activePreset = computed<keyof typeof presets | null>(() => {
  const item = settings.value
  for (const key of presetOrder) {
    const preset = presets[key]
    if (item.minutes !== preset.minutes || item.durationRandom) continue
    if (item.difficulty !== preset.difficulty || item.finale !== preset.finale) continue
    if (Object.keys(preset.categories).some(cat => item.categories[cat as keyof typeof preset.categories] !== preset.categories[cat as keyof typeof preset.categories])) continue
    return key
  }
  return null
})

// 推荐预设：只覆盖时长/难度/结局与三类开关，微调值（tune）一并归零，与参考站一致。
function applyPreset(key: keyof typeof presets) {
  const preset = presets[key]
  const item = settings.value
  item.minutes = preset.minutes
  item.durationRandom = false
  item.difficulty = preset.difficulty
  item.finale = preset.finale
  Object.assign(item.categories, preset.categories)
  item.tune = { chance: null, stop: null, mix: null }
}

// 自己调：滑杆直接写 tune；「恢复成难度的数值」把三项清空回落到难度预设。
const mix = computed(() => mixOf(settings.value.difficulty, settings.value.tune))
const chancePercent = computed(() => settings.value.tune.chance ?? Math.round(difficulties[settings.value.difficulty].chance * 100))
function setChance(value: number) { settings.value.tune.chance = Math.round(value) }
function setMix(mode: EdgeMode, value: number) {
  settings.value.tune.mix = adjustMix({ ...mix.value }, mode, Math.round(value))
}
function restoreTune() { settings.value.tune = { chance: null, stop: null, mix: null } }
const derivedMix = computed(() => mixOf(settings.value.difficulty, { chance: null, stop: null, mix: null }))

const timeChoices = computed(() => [3, 5, 10, 15, 20, 30])
function setMinutes(value: number) {
  settings.value.minutes = Math.min(durationMax, Math.max(durationMin, Math.round(value)))
  settings.value.durationRandom = false
}
// 等待时长：预设档改写上下限，数字输入在提交时夹取。
function setRestRange(value: [number, number]) {
  settings.value.rest.min = value[0]
  settings.value.rest.max = value[1]
}
function clampRest(raw: number) {
  const value = Number.isFinite(raw) ? Math.round(raw) : 8
  return Math.min(120, Math.max(3, value))
}
function syncRestMin() {
  const value = clampRest(settings.value.rest.min)
  settings.value.rest.min = value
  if (settings.value.rest.max < value) settings.value.rest.max = value
}
function syncRestMax() {
  const value = clampRest(settings.value.rest.max)
  settings.value.rest.max = Math.max(value, settings.value.rest.min)
}
function syncRestFixed() {
  const value = clampRest(settings.value.rest.seconds)
  settings.value.rest.seconds = value
}

// 指令分类：只抽选中的分类（傲气/道具类始终启用）。
function toggleCategory(key: keyof EdgeSettings['categories']) {
  settings.value.categories[key] = !settings.value.categories[key]
}

// 自定义口令：上限 30 条、单条 60 字。
const draftCommand = ref('')
const draftMode = ref<EdgeMode>('go')
const canAddCommand = computed(() => !!draftCommand.value.trim() && settings.value.custom.length < customCommandLimit)
function addCommand() {
  const text = draftCommand.value.trim().slice(0, customCommandTextLimit)
  if (!text || settings.value.custom.length >= customCommandLimit) return
  settings.value.custom.push({ text, mode: draftMode.value })
  draftCommand.value = ''
}
function removeCommand(index: number) {
  settings.value.custom.splice(index, 1)
}

// 逐条启停内置口令：存的是停用下标，点一处在启用/停用间切换。
const commandGroups = computed(() => modeOrder.map(mode => ({
  mode,
  label: modeLabels[mode],
  items: maleCommands.map((command, index) => ({ index, command })).filter(item => item.command.mode === mode),
})))
function toggleCommand(index: number) {
  const at = settings.value.disabled.indexOf(index)
  if (at >= 0) settings.value.disabled.splice(at, 1)
  else settings.value.disabled.push(index)
}
function enableAllCommands() { settings.value.disabled.splice(0) }
/** 逐条 BPM：0 表示这条不打节拍，写回原值时从覆盖表里删掉。 */
function setCommandBpm(index: number, raw: string, fallback: number) {
  const parsed = Number(raw)
  if (!Number.isFinite(parsed)) return
  const value = Math.min(300, Math.max(0, Math.round(parsed)))
  if (value === fallback) delete settings.value.bpm[String(index)]
  else settings.value.bpm[String(index)] = value
  if (!Object.keys(settings.value.bpm).length) settings.value.bpm = {}
}

// 视频·图片组只在不播放时出现：播放中改图库/顺序需要重新取队列，必须回列表。
const media = computed(() => props.media)

const positionChoices: { value: EdgeSettings['pos']; label: string }[] = [
  { value: 'top', label: '上' },
  { value: 'center', label: '中' },
  { value: 'bottom', label: '下' },
]

const videoSoundChoices: { value: EdgeSettings['videoSound']; label: string }[] = [
  { value: 'off', label: '关' },
  { value: 'end', label: '只在最后（获得许可时）' },
  { value: 'always', label: '一直开' },
]

/* ---- 镜子：打开前先征得同意，再让浏览器请求摄像头 ---- */
const mirrorAsk = ref(false)
const mirrorError = ref<MirrorError | null>(null)

function toggleMirror(event: Event) {
  const input = event.target as HTMLInputElement
  mirrorError.value = null
  if (!input.checked) { settings.value.mirror.on = false; mirrorAsk.value = false; return }
  const problem = mirrorSupport()
  if (problem) { input.checked = false; settings.value.mirror.on = false; mirrorError.value = problem; return }
  // 打开前先征得同意：真正的开关由 allowMirror 置位，这里先把勾选退回去。
  input.checked = false
  mirrorAsk.value = true
}

function cancelMirror() {
  mirrorAsk.value = false
  settings.value.mirror.on = false
  mirrorError.value = null
}

async function allowMirror() {
  mirrorAsk.value = false
  const problem = mirrorSupport()
  if (problem) { mirrorError.value = problem; settings.value.mirror.on = false; return }
  try {
    // 设置页只做一次授权与环境校验：拿到流立刻停掉，真正的画面由播放层接管。
    const stream = await navigator.mediaDevices.getUserMedia(MIRROR_CONSTRAINTS)
    stopStream(stream)
    mirrorError.value = null
    settings.value.mirror.on = true
  } catch (error) {
    mirrorError.value = classifyMirrorError(error)
    settings.value.mirror.on = false
  }
}
/** 逐项搜索：命中的设置项留下，其余隐藏（与参考站的按键搜索一致）。 */
const root = ref<HTMLElement>()
const hitCount = ref(-1)
function applyFind() {
  const card = root.value
  if (!card) return
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) {
    card.querySelectorAll<HTMLElement>('[data-sundome-find-item]').forEach(item => { item.hidden = false })
    hitCount.value = -1
    return
  }
  let hits = 0
  for (const section of card.querySelectorAll<HTMLElement>('.settings-section')) {
    let showGroup = false
    for (const child of Array.from(section.children) as HTMLElement[]) {
      if (child.classList.contains('section-title')) { child.hidden = false; continue }
      const text = (child.textContent ?? '').toLowerCase()
      if (child.tagName === 'H5') {
        showGroup = text.includes(keyword)
        child.hidden = !showGroup
        continue
      }
      const show = showGroup || text.includes(keyword)
      child.hidden = !show
      if (show) hits += 1
    }
  }
  hitCount.value = hits
}
watch([search, visible], () => { void nextTick(applyFind) }, { immediate: true })

const beatsImages = computed(() => !!media.value && media.value.kind === 'image' && media.value.imageTiming === 'beat')
const secondsLabel = computed(() => readEdgeSettings(null) ? '' : '')
void secondsLabel
</script>

<template>
  <div ref="root" class="settings-card" :class="{ runtime }">
    <header class="card-head">
      <div class="card-heading">
        <h3 class="card-title">玩法设置</h3>
        <p class="card-summary" data-sundome-summary>{{ summary }}</p>
        <p v-if="poolNotice" class="card-pool-empty" role="alert" data-sundome-pool-empty>{{ poolNotice }}</p>
        <p v-if="statsLine" class="card-stats" data-sundome-stats>{{ statsLine }}</p>
        <div v-if="dayLines.length" class="card-days" data-sundome-days>
          <p v-for="(line, index) in dayLines" :key="index" :class="{ 'card-days-strong': index === 0 }">{{ line }}</p>
        </div>
      </div>
      <div class="head-actions">
        <button v-if="historyCount" type="button" class="card-history" data-sundome-history-open="setup" @click="openHistory">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <polyline points="12 7 12 12 15 14" />
          </svg>
          {{ recordsText.open }}<span class="card-history-count">{{ historyCount }}</span>
        </button>
        <p v-if="changedCount" class="card-changed" data-sundome-changed :data-sundome-changed-count="changedCount">与默认不同的项目：{{ changedCount }}</p>
        <button type="button" class="text-button card-reset-all" data-sundome-reset-open-head title="恢复全部默认设置，保留自己的指令" @click="askResetAll">恢复默认设置</button>
        <span v-if="resetDone" class="card-reset-done" data-sundome-reset-done>已恢复默认设置</span>
        <button v-if="canReset" type="button" class="text-button card-reset" :title="resetArmed ? '再点一次把本组恢复为默认值' : '只把本组恢复为默认值，其他分组不变'" @click="resetGroup">{{ resetLabel }}</button>
      </div>
    </header>
    <div v-if="allArmed" class="card-reset-confirm" data-sundome-reset="confirm">
      <p>要把设置恢复成默认吗？</p>
      <button type="button" class="secondary" data-sundome-reset-yes @click="resetAll">恢复</button>
      <button type="button" class="text-button" data-sundome-reset-no @click="allArmed = false">取消</button>
    </div>
    <label class="settings-search">查找设置<input v-model="search" type="search" data-sundome-settings-search placeholder="例如：乳头、左手、速度、视频" /></label>
    <div class="settings-tabs" role="tablist" aria-label="设置分类" data-sundome-tabs :data-sundome-hits="hitCount < 0 ? visible.length : hitCount">
      <button v-for="group in groups" :key="group.id" type="button" role="tab" :id="`settings-tab-${group.id}`" :aria-controls="`settings-panel-${group.id}`" :aria-selected="!search && selected === group.id" :aria-pressed="!search && selected === group.id" @click="selectGroup(group.id)">{{ group.label }}</button>
    </div>
    <p v-if="!visible.length || (search.trim() && hitCount === 0)" class="muted" role="status" data-sundome-find-none>没有匹配的设置，请换个关键词。</p>
    <section v-for="group in visible" :key="group.id" class="settings-section" role="tabpanel" :id="`settings-panel-${group.id}`" :aria-labelledby="`settings-tab-${group.id}`" :data-sundome-find="group.label" :data-sundome-tab-panel="group.id" :aria-label="`${group.label}设置`">
      <h4 v-if="search" class="section-title">{{ group.label }}</h4>

      <template v-if="group.id === 'play'">
        <h5 class="field-label">推荐</h5>
        <div class="chips">
          <button v-for="key in presetOrder" :key="key" type="button" class="chip" :data-sundome-choice="`preset-${key}`" :aria-pressed="settings.minutes === presets[key].minutes && settings.difficulty === presets[key].difficulty && settings.finale === presets[key].finale" @click="applyPreset(key)">{{ presetLabels[key] }}</button>
        </div>
        <p v-if="activePreset" class="muted" data-sundome-preset-note>{{ presetNotes[activePreset] }}</p>
        <p v-else class="muted" data-sundome-preset-note>{{ presetNone }}</p>

        <h5 class="field-label">{{ focusLegend }}</h5>
        <div class="chips">
          <button v-for="area in focusAreas" :key="area" type="button" class="chip" :data-sundome-choice="`focus-${area}`" :aria-pressed="settings.focus === area" data-sundome-focus @click="settings.focus = area">{{ focusLabels[area] }}</button>
        </div>
        <p v-if="settings.focus !== 'none'" class="muted" data-sundome-focus-note>{{ focusNotes[settings.focus] }}</p>

        <h5 class="field-label">只玩乳头 / 只玩龟头</h5>
        <div v-if="settings.focus !== 'none'" class="muted">{{ focusSectionsOff }}</div>
        <div v-else class="settings-grid">
          <label class="toggle"><input :checked="settings.nipple.on" type="checkbox" data-sundome-switch="nipple-promo" @change="settings.nipple.on = ($event.target as HTMLInputElement).checked" />只玩乳头</label>
          <label v-if="settings.nipple.on">插入段数<input :value="settings.nipple.times" type="number" min="1" max="4" @change="settings.nipple.times = Math.min(4, Math.max(1, Math.round(Number(($event.target as HTMLInputElement).value) || 1)))" /></label>
          <label class="toggle"><input :checked="settings.glans.on" type="checkbox" data-sundome-switch="glans" @change="settings.glans.on = ($event.target as HTMLInputElement).checked" />只玩龟头</label>
          <label v-if="settings.glans.on">插入段数<input :value="settings.glans.times" type="number" min="1" max="4" @change="settings.glans.times = Math.min(4, Math.max(1, Math.round(Number(($event.target as HTMLInputElement).value) || 1)))" /></label>
        </div>

        <h5 class="field-label">道具模式</h5>
        <div class="settings-grid">
          <label class="toggle"><input :checked="settings.toy" type="checkbox" data-sundome-switch="toy" @change="settings.toy = ($event.target as HTMLInputElement).checked" />使用飞机杯</label>
          <label class="toggle"><input :checked="settings.aneros" type="checkbox" data-sundome-switch="aneros" @change="settings.aneros = ($event.target as HTMLInputElement).checked" />我有前列腺按摩器</label>
        </div>
        <p class="muted">开飞机杯会混入适合飞机杯的指令，例如套到底后停住、取下等；只能用手直接做的指令不会出现。开按摩器后，红色（不许碰）的指令里会加入夹紧、放松的指令。</p>

        <h5 class="field-label">时间</h5>
        <div class="chips">
          <button v-for="value in timeChoices" :key="value" type="button" class="chip" :data-sundome-choice="`duration-${value}`" :aria-pressed="!settings.durationRandom && settings.minutes === value" @click="setMinutes(value)">{{ value }} 分钟</button>
          <button type="button" class="chip" data-sundome-choice="duration-random" :aria-pressed="settings.durationRandom" @click="settings.durationRandom = true; settings.minutes = 5 + Math.floor(Math.random() * 16)">随机</button>
        </div>
        <div class="settings-grid">
          <label>自定义时长（分钟，{{ durationMin }}–{{ durationMax }}）<input :value="settings.minutes" type="number" :min="durationMin" :max="durationMax" @change="setMinutes(Number(($event.target as HTMLInputElement).value))" /></label>
          <span v-if="settings.durationRandom" class="hint-cell muted" data-sundome-random-note>{{ randomTimeNote }}</span>
        </div>

        <h5 class="field-label">难度</h5>
        <div class="chips">
          <button v-for="key in difficultyOrder" :key="key" type="button" class="chip" :data-sundome-choice="`difficulty-${key}`" :aria-pressed="settings.difficulty === key" @click="settings.difficulty = key as Difficulty">{{ difficultyLabels[key] }}</button>
        </div>
        <p class="muted">{{ difficultyHints[settings.difficulty] }}</p>

        <details class="fold">
          <summary>自己调（许可概率 {{ chancePercent }}% · 可以撸 {{ mix.go }}% · 慢慢来 {{ mix.slow }}% · 不许碰 {{ mix.stop }}%）</summary>
          <div class="settings-grid">
            <label>许可概率 {{ chancePercent }}%<input :value="chancePercent" type="range" min="10" max="100" step="5" @input="setChance(Number(($event.target as HTMLInputElement).value))" /></label>
            <label>可以撸 {{ mix.go }}%<input :value="mix.go" type="range" min="0" max="100" step="5" @input="setMix('go', Number(($event.target as HTMLInputElement).value))" /></label>
            <label>慢慢来 {{ mix.slow }}%<input :value="mix.slow" type="range" min="0" max="100" step="5" @input="setMix('slow', Number(($event.target as HTMLInputElement).value))" /></label>
            <label>不许碰 {{ mix.stop }}%<input :value="mix.stop" type="range" min="0" max="60" step="5" @input="setMix('stop', Number(($event.target as HTMLInputElement).value))" /></label>
          </div>
          <p class="muted">三项合计 100%；难度默认是 {{ derivedMix.go }} / {{ derivedMix.slow }} / {{ derivedMix.stop }}。不许碰占比超过 45% 时会允许「不许碰」连续出现。</p>
          <button type="button" class="text-button" @click="restoreTune">恢复成难度的数值</button>
        </details>

        <h5 class="field-label">结局</h5>
        <div class="chips">
          <button v-for="key in finaleOrder" :key="key" type="button" class="chip" :data-sundome-choice="`finale-${key}`" :aria-pressed="settings.finale === key" @click="settings.finale = key">{{ finaleLabels[key] }}</button>
        </div>
        <p class="muted">{{ finaleHints[settings.finale] }}</p>
        <template v-if="settings.finale === 'overtime'">
          <h5 class="field-label">加时长度</h5>
          <div class="chips">
            <button v-for="key in extendLengthOrder" :key="key" type="button" class="chip" :data-sundome-extend-len="key" :aria-pressed="settings.extendLen === key" @click="settings.extendLen = key">{{ extendLengthLabels[key] }}</button>
          </div>
        </template>
        <label class="toggle"><input :checked="settings.allowRuin" type="checkbox" data-sundome-switch="allow-ruin" @change="settings.allowRuin = ($event.target as HTMLInputElement).checked" />落选时以「松手射精」结束</label>

        <h5 class="field-label">允许射精的时间 / 忍住后等待</h5>
        <div class="settings-grid">
          <label>允许射精的时间（秒）<select :value="settings.rewardSeconds" @change="settings.rewardSeconds = Number(($event.target as HTMLSelectElement).value)">
            <option v-for="value in rewardChoices" :key="value" :value="value">{{ value }} 秒</option>
          </select></label>
          <label>等待模式<select :value="settings.rest.mode" @change="settings.rest.mode = ($event.target as HTMLSelectElement).value as 'random'">
            <option v-for="key in restModeOrder" :key="key" :value="key">{{ restModeLabels[key] }}</option>
          </select></label>
        </div>
        <div v-if="settings.rest.mode === 'random'" class="settings-grid">
          <label>等待区间<select :value="`${settings.rest.min}-${settings.rest.max}`" @change="setRestRange(restRangeChoices.find(item => `${item[0]}-${item[1]}` === ($event.target as HTMLSelectElement).value) ?? [8, 16])">
            <option v-for="item in restRangeChoices" :key="item.join('-')" :value="`${item[0]}-${item[1]}`">{{ item[0] }}～{{ item[1] }} 秒</option>
          </select></label>
          <span class="hint-cell muted">选预设会同时改写下面两个数字，也可以直接改。</span>
          <label>最短等待（秒）<input :value="settings.rest.min" type="number" inputmode="numeric" :min="restMin" :max="restMax" @change="settings.rest.min = Number(($event.target as HTMLInputElement).value); syncRestMin()" /></label>
          <label>最长等待（秒）<input :value="settings.rest.max" type="number" inputmode="numeric" :min="restMin" :max="restMax" @change="settings.rest.max = Number(($event.target as HTMLInputElement).value); syncRestMax()" /></label>
        </div>
        <div v-else class="settings-grid">
          <label>固定等待（秒）<input :value="settings.rest.seconds" type="number" inputmode="numeric" :min="restMin" :max="restMax" data-sundome-rest-seconds @change="settings.rest.seconds = Number(($event.target as HTMLInputElement).value); syncRestFixed()" /></label>
        </div>
        <p class="muted">按下「忍住了」之后进入红色，等这段时长过去再回到循环。</p>

        <label>指令时长<select :value="settings.instructionLength" @change="settings.instructionLength = ($event.target as HTMLSelectElement).value as 'standard'">
          <option v-for="key in instructionLengthOrder" :key="key" :value="key">{{ instructionLengthLabels[key] }}</option>
        </select></label>
        <p class="muted">撸的指令会持续更久。红色（不许碰）、写明秒数的指令和整局结束时间不会改变。</p>

        <ul class="play-legend">
          <li><span class="legend-dot" style="background: #5ee3a1" />屏幕是绿色时可以撸。手跟着光和声音的节拍</li>
          <li><span class="legend-dot" style="background: #f0c35a" />黄色是放慢、挑逗</li>
          <li><span class="legend-dot" style="background: #ff6b7d" />变红就松手。结束前不许碰</li>
          <li v-if="settings.nipple.on"><span class="legend-dot" style="background: #ff6b7d" />只玩乳头</li>
          <li v-if="settings.glans.on"><span class="legend-dot" style="background: #f0c35a" />只玩龟头</li>
        </ul>
        <p class="play-rules">
          时间到之前射了就输。忍住了就按「忍住了」（每次最后的许可率 +5%）。拿到许可后要在
          {{ settings.rewardSeconds }} 秒内射出来。当前设置的许可率从
          {{ Math.round(permitRate(settings.difficulty, 0, settings.tune.chance) * 100) }}% 起。
        </p>
      </template>

      <template v-else-if="group.id === 'command'">
        <h5 class="field-label">指令类型（可多选）</h5>
        <div class="chips">
          <button v-for="key in categoryOrder" :key="key" type="button" class="chip" :data-sundome-choice="`category-${key}`" :aria-pressed="settings.categories[key]" @click="toggleCategory(key)">{{ categoryLabels[key] }}</button>
        </div>
        <p class="muted">基础指令（绿·黄·红）始终包含在内，关掉的类型不会再被抽到。{{ categoryHints.edge }}；{{ categoryHints.tease }}；{{ categoryHints.pose }}；{{ categoryHints.pain }}。</p>

        <div class="settings-grid">
          <label>惯用手<select :value="settings.hand" @change="settings.hand = ($event.target as HTMLSelectElement).value as 'right'">
            <option value="right">右手</option>
            <option value="left">左手</option>
          </select></label>
        </div>
        <p class="muted">选左手时，指令里的左右手会自动对调。</p>

        <h5 class="field-label">口吻</h5>
        <p class="muted">“强硬”会在指令前后加一句命令式的短句；“挑逗”则是一个女人一边调侃你、一边撩你继续的短句；“辱骂”会出现很重的话；“温柔”像恋人在旁边陪着；“足控”只有话语、指令不变。</p>
        <p v-if="activeToneCount > 1" class="muted">同时打开两个以上时，每条指令轮流使用。</p>
        <div class="chips">
          <button v-for="key in toneOrder" :key="key" type="button" class="chip" :data-sundome-choice="`tone-${key}`" :aria-pressed="settings.tones[key]" @click="settings.tones[key] = !settings.tones[key]">{{ toneLabels[key] }}</button>
        </div>
        <div v-if="activeTones.length" class="tone-tuning">
          <p class="muted">{{ activeTones.map(key => `${toneLabels[key]}：${toneNotes[key]}`).join('　') }}</p>
          <label class="toggle"><input :checked="settings.toneLine.show" type="checkbox" data-sundome-switch="tone-show" @change="settings.toneLine.show = ($event.target as HTMLInputElement).checked" />显示在屏幕上</label>
          <label class="toggle"><input :checked="settings.toneLine.before" type="checkbox" data-sundome-switch="tone-before" @change="settings.toneLine.before = ($event.target as HTMLInputElement).checked" />放在指令前</label>
          <div class="settings-grid">
            <label>放在指令后<select :value="settings.toneLine.after" @change="settings.toneLine.after = ($event.target as HTMLSelectElement).value as 'never'">
              <option v-for="key in toneAfterOrder" :key="key" :value="key">{{ toneAfterLabels[key] }}</option>
            </select></label>
          </div>
          <p class="muted">指令类型是「寸止指令」时不会加后置短句，避免把“松手”冲淡。</p>
        </div>

        <h5 class="field-label">自定义口令（{{ settings.custom.length }}/{{ customCommandLimit }}）</h5>
        <div class="command-form">
          <label>口令内容<input v-model="draftCommand" type="text" :maxlength="customCommandTextLimit" placeholder="例如：停三秒再继续" data-sundome-custom-input @keydown.enter.prevent="addCommand" /></label>
          <label>类型<select v-model="draftMode">
            <option v-for="key in modeOrder" :key="key" :value="key">{{ modeLabels[key] }}</option>
          </select></label>
          <button type="button" class="secondary" :disabled="!canAddCommand" data-sundome-custom-add="add" @click="addCommand">添加</button>
        </div>
        <p v-if="settings.custom.length >= customCommandLimit" class="muted">已到 {{ customCommandLimit }} 条上限，删掉一条再添加。</p>
        <p v-else class="muted">单条最多 {{ customCommandTextLimit }} 字；要改就删掉重新添加。</p>
        <ul v-if="settings.custom.length" class="command-list">
          <li v-for="(item, index) in settings.custom" :key="`${item.text}-${index}`">
            <small class="badge">{{ modeLabels[item.mode] }}</small>
            <span>{{ item.text }}</span>
            <button type="button" class="text-button" @click="removeCommand(index)">删除</button>
          </li>
        </ul>

        <details class="fold">
          <summary>逐条启停内置口令（已停用 {{ settings.disabled.length }} 条）</summary>
          <p class="muted">亮着表示启用，点一下停用；停用的口令不会再被抽到。</p>
          <div v-for="commandGroup in commandGroups" :key="commandGroup.mode" class="command-group">
            <h6 class="command-group-title"><span class="legend-dot" :style="{ background: modeColors[commandGroup.mode] }" />{{ commandGroup.label }}（{{ commandGroup.items.length }} 条）</h6>
            <ul class="command-rows">
              <li v-for="item in commandGroup.items" :key="item.index">
                <span class="command-text">{{ item.command.text }}<small v-if="item.command.category !== 'basic'" class="command-cat">{{ categoryLabels[item.command.category as 'edge'] }}</small></span>
                <input
                  class="command-bpm"
                  type="number"
                  inputmode="numeric"
                  min="0"
                  max="300"
                  :value="settings.bpm[String(item.index)] ?? item.command.bpm ?? 0"
                  :title="`BPM（0=无节拍）`"
                  :aria-label="`${item.command.text} BPM（0=无节拍）`"
                  :data-sundome-bpm-input="item.index"
                  @change="setCommandBpm(item.index, ($event.target as HTMLInputElement).value, item.command.bpm ?? 0)"
                />
                <button
                  type="button"
                  role="switch"
                  class="command-switch"
                  :aria-checked="!settings.disabled.includes(item.index)"
                  :aria-label="item.command.text"
                  :data-sundome-cmd="item.index"
                  @click="toggleCommand(item.index)"
                ><span /></button>
              </li>
            </ul>
          </div>
          <button v-if="settings.disabled.length" type="button" class="text-button" @click="enableAllCommands">全部启用</button>
        </details>
      </template>

      <template v-else-if="group.id === 'media'">
        <template v-if="media">
          <div class="settings-grid">
            <label>内容类型<select v-model="media.kind">
              <option value="mixed">混合内容</option>
              <option value="image">仅图片</option>
              <option value="video">仅视频</option>
            </select></label>
            <label>播放顺序<select v-model="media.order">
              <option value="shuffle">随机</option>
              <option value="sequential">文件名顺序</option>
            </select></label>
            <label v-if="media.kind !== 'video'">每轮图片数（0 为全部）<input v-model.number="media.imageCount" type="number" min="0" max="100000" required /></label>
            <label v-if="media.kind === 'image'">图片切换<select v-model="media.imageTiming">
              <option value="time">按时间</option>
              <option value="beat">按 BPM · 每拍一张</option>
            </select></label>
            <label v-if="media.kind !== 'video' && (media.kind !== 'image' || media.imageTiming === 'time')">图片间隔（秒）<input v-model.number="media.imageSeconds" type="number" min="1" max="300" required /></label>
            <label>节拍上限（BPM）<input v-model.number="media.bpm" type="number" min="20" max="300" required /></label>
          </div>
          <p v-if="beatsImages" class="muted">每拍发声并切一张；慢速为快速的 60%，红色时不发声、不自动切图。</p>
          <label class="toggle"><input v-model="media.loop" type="checkbox" data-sundome-switch="loop" />循环列表</label>
          <label class="toggle"><input v-model="media.favoritesOnly" type="checkbox" data-sundome-switch="favorites" />仅播放喜欢</label>
          <label class="toggle"><input :checked="settings.keepVideoOnStop" type="checkbox" data-sundome-switch="video-stop" @change="settings.keepVideoOnStop = ($event.target as HTMLInputElement).checked" />红色（不许碰）时也继续播放视频</label>
          <p class="muted">开＝红色指令时视频不暂停、不变暗。关＝红色时暂停并变暗（和以前一样）。</p>
          <label class="toggle"><input :checked="settings.keepVideoWhileCooling" type="checkbox" data-sundome-switch="video-cooldown" @change="settings.keepVideoWhileCooling = ($event.target as HTMLInputElement).checked" />记住后视频的等待时间也播放</label>
          <p class="muted">开＝按「忍住了」后松手等待时视频不停。关＝这段等待时间暂停并变暗。其他红色指令按「红色期间也播放」的设置执行。</p>
          <label class="toggle"><input :checked="settings.switchVideoPerCommand" type="checkbox" data-sundome-switch="video-switch-each" @change="settings.switchVideoPerCommand = ($event.target as HTMLInputElement).checked" />每换一条指令就换一个视频</label>
          <p class="muted">开＝每换一条指令就切到下一个视频。关＝一个视频播完再换（和以前一样）。</p>
          <div class="field">
            <span class="field-label">视频大小</span>
            <div class="chips">
              <button class="chip" data-sundome-choice="video-fit-cover" :class="{ on: settings.fit === 'cover' }" type="button" @click="settings.fit = 'cover'">铺满屏幕</button>
              <button class="chip" data-sundome-choice="video-fit-contain" :class="{ on: settings.fit === 'contain' }" type="button" @click="settings.fit = 'contain'">显示完整画面（不裁切）</button>
            </div>
            <p class="muted">关=铺满屏幕（竖屏时左右被裁）。开=显示完整视频（上下留黑边）。</p>
          </div>
          <div v-if="settings.fit === 'contain'" class="field">
            <span class="field-label">显示位置</span>
            <div class="chips">
              <button v-for="item in positionChoices" :key="item.value" class="chip" :data-sundome-choice="`video-pos-${item.value}`" :class="{ on: settings.pos === item.value }" type="button" @click="settings.pos = item.value">{{ item.label }}</button>
            </div>
            <p class="muted">选「上」时指令显示在下方，选「下」时指令显示在上方（不会与视频重叠）。</p>
          </div>
          <label>指令文字不透明度 · {{ settings.textOpacity }}%<input :value="settings.textOpacity" type="range" :min="textOpacityMin" max="100" step="5" @input="settings.textOpacity = Number(($event.target as HTMLInputElement).value)" /></label>
          <p class="muted">视频上方的文字和周围暗色光晕的浓度。调低后能透过文字看到视频（{{ textOpacityMin }}～100%）。</p>
          <label>指令文字大小 · {{ settings.textScale }}%<input :value="settings.textScale" type="range" :min="textScaleMin" :max="textScaleMax" step="5" @input="settings.textScale = Number(($event.target as HTMLInputElement).value)" /></label>
          <p class="muted">把视频上方的指令、口白和补充一起缩小（{{ textScaleMin }}～{{ textScaleMax }}%）。</p>
          <div class="field">
            <span class="field-label">视频声音</span>
            <div class="chips">
              <button v-for="choice in videoSoundChoices" :key="choice.value" class="chip" :data-sundome-choice="`video-sound-${choice.value}`" :class="{ on: settings.videoSound === choice.value }" type="button" @click="settings.videoSound = choice.value">{{ choice.label }}</button>
            </div>
            <p class="muted">只在最后＝红色与黄色时静音，拿到许可后才有声音。一直开会和节拍声混在一起。</p>
          </div>
          <label class="toggle"><input :checked="settings.skipIntro" type="checkbox" data-sundome-switch="video-skip-intro" @change="settings.skipIntro = ($event.target as HTMLInputElement).checked" />视频从中间开始播放</label>
          <p class="muted">跳过试看片前半段的打招呼和采访，从中间附近开始播放。</p>
          <p class="muted">指令自带的手速（BPM）优先，这里只是上限与切图节拍。已展示图片不再入选。</p>
        </template>
        <p v-else class="muted">先选一个播放列表。</p>
      </template>

      <template v-else-if="group.id === 'sound'">
        <label class="toggle"><input :checked="settings.metronome" type="checkbox" data-sundome-switch="sound" @change="settings.metronome = ($event.target as HTMLInputElement).checked" />节拍声（节拍器）</label>
        <p class="muted">按指令的速度轻声打拍子。灯光节拍始终显示。</p>
        <div class="settings-grid">
          <label>节拍音量 · {{ settings.beatVolume }}%<input :value="settings.beatVolume" type="range" min="0" :max="beatVolumeMax" step="5" @input="settings.beatVolume = Number(($event.target as HTMLInputElement).value)" /></label>
          <label v-if="media?.kind !== 'image'">视频音量 · {{ settings.mediaVolume }}%<input :value="settings.mediaVolume" type="range" min="0" max="100" step="5" @input="settings.mediaVolume = Number(($event.target as HTMLInputElement).value)" /></label>
        </div>
        <p class="muted">节拍音量最高 {{ beatVolumeMax }}%，比默认响得多；觉得吵就往下拉。</p>
        <label class="toggle"><input :checked="settings.bpmRandom.on" type="checkbox" data-sundome-switch="bpm-random" @change="settings.bpmRandom.on = ($event.target as HTMLInputElement).checked" />每次变换节奏</label>
        <p class="muted">绿色和黄色指令的节奏会在设定范围内每次变化。绿色取较快的一半，黄色取较慢的一半。</p>
        <div v-if="settings.bpmRandom.on" class="settings-grid">
          <label>最慢 · {{ settings.bpmRandom.min }}<input :value="settings.bpmRandom.min" type="number" :min="bpmRandomMin" :max="bpmRandomMax" step="5" @change="settings.bpmRandom.min = clampBpm(($event.target as HTMLInputElement).value, settings.bpmRandom.min)" /></label>
          <label>最快 · {{ settings.bpmRandom.max }}<input :value="settings.bpmRandom.max" type="number" :min="bpmRandomMin" :max="bpmRandomMax" step="5" @change="settings.bpmRandom.max = clampBpm(($event.target as HTMLInputElement).value, settings.bpmRandom.max)" /></label>
        </div>
        <h5 class="field-label">高级设置</h5>
        <p class="muted">一般不用改。保持默认即可。</p>
        <label class="toggle"><input :checked="settings.heartbeat" type="checkbox" data-sundome-switch="heartbeat" @change="settings.heartbeat = ($event.target as HTMLInputElement).checked" />心跳声（氛围）</label>
        <p class="muted">「不许碰」时播放低沉的心跳声。</p>
        <div v-if="settings.heartbeat" class="settings-grid">
          <label>心跳声音量 · {{ settings.heartbeatVolume }}%<input :value="settings.heartbeatVolume" type="range" min="0" :max="beatVolumeMax" step="5" @input="settings.heartbeatVolume = Number(($event.target as HTMLInputElement).value)" /></label>
          <label>红色时<select :value="settings.redBeat" @change="settings.redBeat = ($event.target as HTMLSelectElement).value as 'heartbeat'">
            <option v-for="key in redBeatOrder" :key="key" :value="key">{{ redBeatLabels[key] }}</option>
          </select></label>
        </div>
        <p class="muted">「不许碰」带 BPM 时用什么声音打拍子。关掉心跳声的话就用节拍器。</p>
        <p class="muted">心跳声音量 100% 与以前一样，可以和节拍声分开调整（最高 {{ beatVolumeMax }}%）。</p>
        <label class="toggle"><input :checked="settings.heartbeatSync" type="checkbox" data-sundome-switch="heartbeat-sync" @change="settings.heartbeatSync = ($event.target as HTMLInputElement).checked" />心跳跟随 BPM</label>
        <p class="muted">关掉后，即使红色带 BPM，心跳也保持固定节奏。</p>
        <label class="toggle"><input :checked="settings.vibrate" type="checkbox" data-sundome-switch="vibrate" @change="settings.vibrate = ($event.target as HTMLInputElement).checked" />切换时振动</label>
        <p class="muted">仅限手机。“不许碰”时振动更久。</p>
        <h5 v-if="settings.vibrate" class="field-label">振动的时机</h5>
        <div v-if="settings.vibrate" class="settings-grid">
          <label class="toggle"><input :checked="settings.vibrateOn.command" type="checkbox" data-sundome-switch="vib-command" @change="settings.vibrateOn.command = ($event.target as HTMLInputElement).checked" />指令切换时</label>
          <label class="toggle"><input :checked="settings.vibrateOn.edge" type="checkbox" data-sundome-switch="vib-edge" @change="settings.vibrateOn.edge = ($event.target as HTMLInputElement).checked" />按“忍住了”时</label>
          <label class="toggle"><input :checked="settings.vibrateOn.finish" type="checkbox" data-sundome-switch="vib-finish" @change="settings.vibrateOn.finish = ($event.target as HTMLInputElement).checked" />结局（许可·结束）时</label>
        </div>
        <p class="muted">全部是浏览器实时合成的音，不加载任何音频文件。</p>
      </template>

      <template v-else>
        <label class="toggle"><input :checked="settings.hideRemaining" type="checkbox" data-sundome-switch="hide-remaining" @change="settings.hideRemaining = ($event.target as HTMLInputElement).checked" />隐藏剩余时间与进度</label>
        <label>视频变暗程度 · {{ settings.dim }}%<input :value="settings.dim" type="range" min="0" max="100" step="5" data-sundome-dim @input="settings.dim = Number(($event.target as HTMLInputElement).value)" /></label>
        <p class="muted">0%＝完全透明，不加暗色遮罩（视频原本的亮度）。100%＝和以前一样。只影响播放器画面，不改原文件。</p>
        <label class="toggle"><input :checked="settings.mixAudio" type="checkbox" data-sundome-switch="mix-audio" @change="settings.mixAudio = ($event.target as HTMLInputElement).checked" />边听音乐边玩</label>
        <div class="pip-card" :data-sundome-pip-section="settings.pipOffer ? 'on' : 'off'">
          <p class="pip-title">边看别的视频边玩</p>
          <p class="pip-lead">把指令放进悬浮小窗。在别的网站看视频时，也能照着指令继续。</p>
          <label class="toggle"><input :checked="settings.pipOffer" type="checkbox" data-sundome-switch="pip-want" @change="settings.pipOffer = ($event.target as HTMLInputElement).checked" />开始后提示我打开小窗</label>
          <label class="field">
            <span>常看的网站（选填）</span>
            <input :value="settings.pipSite" type="url" placeholder="https://" @input="settings.pipSite = ($event.target as HTMLInputElement).value" />
          </label>
          <p class="muted">只保存在这台设备上。打开小窗后，点一下就能跳过去。</p>
        </div>
        <p class="muted">打开后播放器不会抢占系统的音频焦点。</p>
        <h5 class="field-label">{{ mirrorText.legend }}</h5>
        <label class="toggle"><input :checked="settings.mirror.on" type="checkbox" data-sundome-switch="mirror" @change="toggleMirror" />{{ mirrorText.label }}</label>
        <p class="muted">{{ mirrorText.note }}</p>
        <div v-if="mirrorAsk" class="mirror-consent" data-sundome-mirror-consent>
          <p class="mirror-consent-title">{{ mirrorText.consentTitle }}</p>
          <p class="muted">{{ mirrorText.consentBody }}</p>
          <div class="chips">
            <button class="chip on" type="button" @click="allowMirror">{{ mirrorText.consentYes }}</button>
            <button class="chip" type="button" @click="cancelMirror">{{ mirrorText.consentNo }}</button>
          </div>
        </div>
        <p v-if="mirrorError" class="muted mirror-error" role="alert">{{ mirrorErrorLabels[mirrorError] }}</p>
        <div v-if="settings.mirror.on && !mirrorAsk" class="field">
          <span class="field-label">{{ mirrorText.placeLegend }}</span>
          <div class="chips">
            <button v-for="place in mirrorPlaces" :key="place" class="chip" :data-sundome-choice="`mirror-place-${place}`" :class="{ on: settings.mirror.place === place }" type="button" @click="settings.mirror.place = place">{{ mirrorPlaceLabels[place] }}</button>
          </div>
          <p class="muted">{{ mirrorText.placeNote }}</p>
        </div>
        <template v-if="statsLine">
          <h5 class="field-label">本机成绩</h5>
          <p class="muted" data-sundome-stats-line>{{ statsLine }}</p>
          <p v-if="lostLine" class="muted" data-sundome-lost-line>{{ lostLine }}</p>
          <button type="button" class="text-button" data-sundome-stats-clear @click="clearStats">{{ statsArmed ? '确认清除？' : '清除本机成绩' }}</button>
        </template>
        <template v-else-if="lostLine">
          <h5 class="field-label">本机成绩</h5>
          <p class="muted" data-sundome-lost-line>{{ lostLine }}</p>
          <button type="button" class="text-button" data-sundome-stats-clear @click="clearStats">{{ statsArmed ? '确认清除？' : '清除本机成绩' }}</button>
        </template>
      </template>
    </section>
    <PlaybackHistory ref="history" :open="historyOpen" @close="historyOpen = false" />
  </div>
</template>

<style scoped>
.settings-card { padding: 20px 22px; border: 1px solid var(--color-hairline); border-radius: var(--radius-panel); background: var(--color-canvas); }
.settings-card.runtime { background: var(--color-parchment); }
.card-head { display: flex; align-items: start; justify-content: space-between; gap: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--color-hairline); }
.card-heading { display: grid; gap: 6px; min-width: 0; }
.card-title { margin: 0; font-size: 20px; line-height: 1.4; }
.card-summary { margin: 0; font-size: 14px; line-height: 1.6; color: var(--color-muted); overflow-wrap: anywhere; }
.card-pool-empty { margin: 10px 0 0; padding: 12px 14px; border: 1px solid rgba(168, 61, 104, 0.5); border-radius: 12px; background: var(--color-selection); font-size: 13px; font-weight: 600; line-height: 1.6; color: var(--color-primary); overflow-wrap: anywhere; }
.head-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 10px; }
.card-history {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 0;
  padding: 4px 10px;
  border: 1px solid var(--color-selection);
  border-radius: 999px;
  background: var(--color-canvas);
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 500;
  line-height: 1rem;
  white-space: nowrap;
  cursor: pointer;
}
.card-history:hover { border-color: var(--color-primary); }
.card-history-count { color: var(--color-muted); font-variant-numeric: tabular-nums; }
.card-changed { margin: 0; font-size: 12px; color: var(--color-muted); }
.card-reset-done { font-size: 12px; font-weight: 600; color: var(--color-primary); }
.card-reset-confirm { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 0 0 14px; padding: 12px 14px; border: 1px solid var(--color-hairline); border-radius: 14px; background: var(--color-parchment); }
.card-reset-confirm p { margin: 0 auto 0 0; font-size: 13px; font-weight: 600; color: var(--color-ink); }
.card-reset-confirm button { min-height: 0; }
.card-days { margin: 2px 0 0; display: grid; gap: 2px; }
.card-days p { margin: 0; font-size: 12px; line-height: 1.5; color: var(--color-muted); }
.card-days p.card-days-strong { font-size: 13px; font-weight: 600; color: var(--color-ink); }
.card-stats { margin: 0; font-size: 12px; line-height: 1.6; color: var(--color-supporting); overflow-wrap: anywhere; }
.card-reset { flex-shrink: 0; min-height: 44px; font-size: 14px; }
.settings-search { max-width: 440px; margin-top: 18px; font-size: 14px; }
.settings-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 20px; }
.settings-tabs button { min-height: 44px; padding: 8px 20px; border-radius: 999px; border: 1px solid var(--color-hairline); background: var(--color-pearl); }
.settings-tabs button[aria-pressed="true"] { background: var(--color-selection); border-color: var(--color-primary); color: var(--color-primary); font-weight: 600; }
.settings-section + .settings-section { margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--color-hairline); }
.section-title { margin: 0 0 16px; font-size: 16px; color: var(--color-muted); }
.settings-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.toggle { display: flex; flex-direction: row; align-items: center; gap: 10px; min-height: 44px; margin-block: 12px; }
.settings-section p { margin-top: 12px; font-size: 14px; line-height: 1.6; }
input[type="range"] { padding: 0; min-height: 44px; accent-color: var(--color-primary); }
.tone-tuning { margin-top: 4px; }
.field-label { margin: 16px 0 10px; font-size: 14px; font-weight: 600; color: var(--color-supporting); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-block: 4px 0; }
.mirror-consent { margin-top: 12px; padding: 14px 16px; border: 1px solid var(--color-hairline); border-radius: 12px; background: var(--color-soft); }
.mirror-consent-title { margin: 0; font-size: 14px; font-weight: 600; }
.mirror-consent .muted { margin: 8px 0 0; }
.mirror-consent .chips { margin-top: 12px; }
.mirror-error { color: var(--color-danger); }
.chip { min-height: 38px; padding: 6px 14px; border-radius: 999px; border: 1px solid var(--color-hairline); background: var(--color-pearl); font-size: 14px; line-height: 1.4; }
.chip[aria-pressed="true"] { background: var(--color-selection); border-color: var(--color-primary); color: var(--color-primary); font-weight: 600; }
.fold { margin-block: 16px; padding: 0 14px; border: 1px solid var(--color-hairline); border-radius: 12px; background: var(--color-pearl); }
.fold > summary { display: flex; align-items: center; min-height: 44px; font-size: 14px; color: var(--color-muted); cursor: pointer; }
.fold > :last-child { margin-bottom: 14px; }
.command-group + .command-group { margin-top: 12px; }
.command-group-title { margin: 8px 0; font-size: 13px; font-weight: 400; color: var(--color-muted); }
.command-form { display: grid; grid-template-columns: minmax(0, 1fr) 140px auto; gap: 10px; align-items: end; margin-block: 4px 0; }
.command-form button { margin-bottom: 2px; }
.command-list { display: grid; gap: 8px; margin: 12px 0 0; padding: 0; list-style: none; }
.command-list li { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid var(--color-hairline); border-radius: 10px; background: var(--color-pearl); font-size: 14px; }
.command-list li span { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.command-rows { display: grid; margin: 4px 0 0; padding: 0; list-style: none; }
.command-rows li { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 0; border-top: 1px solid var(--color-hairline); }
.command-rows li:first-child { border-top: 0; }
.command-text { min-width: 0; flex: 1; font-size: 14px; line-height: 1.5; color: var(--color-ink); overflow-wrap: anywhere; }
.command-cat { margin-left: 6px; font-size: 10px; color: var(--color-muted); }
.command-bpm { width: 64px; flex: 0 0 auto; min-height: 0; padding: 4px 8px; text-align: right; font-size: 12px; font-variant-numeric: tabular-nums; }
.command-switch { position: relative; width: 40px; height: 24px; flex: 0 0 auto; min-height: 0; padding: 0; border: 0; border-radius: 999px; background: var(--color-soft); cursor: pointer; transition: background-color .15s ease; }
.command-switch span { position: absolute; top: 4px; left: 4px; width: 16px; height: 16px; border-radius: 999px; background: #fff; transition: transform .15s ease; }
.command-switch[aria-checked="true"] { background: var(--color-primary); }
.command-switch[aria-checked="true"] span { transform: translateX(16px); }
/* 玩法页底部的三色图例与规则句，文案照抄参考站。 */
.play-legend { display: grid; gap: 6px; margin: 20px 0 0; padding: 0; list-style: none; }
.play-legend li { display: flex; align-items: center; gap: 8px; font-size: 13px; line-height: 1.5; color: var(--color-muted); }
.legend-dot { flex: none; width: 8px; height: 8px; border-radius: 999px; }
.play-rules { margin-top: 12px; font-size: 13px; line-height: 1.7; color: var(--color-muted); }
.hint-cell { align-self: end; padding-bottom: 12px; }
@media (max-width: 600px) {
  .settings-grid { grid-template-columns: 1fr; gap: 16px; }
  .settings-tabs { gap: 6px; }
  .settings-tabs button { flex: 1 1 auto; padding-inline: 12px; }
  .command-form { grid-template-columns: 1fr; }
}
@media (max-width: 560px) {
  .settings-card { padding: 16px; border-radius: 12px; }
  .card-head { flex-wrap: wrap; gap: 8px; }
  .card-heading { flex: 1 1 100%; }
  .card-title { font-size: 18px; }
  .card-reset { align-self: flex-start; }
  .settings-search { max-width: none; }
}
.pip-card {
  margin-top: 6px;
  padding: 12px 14px;
  border: 1px solid var(--color-hairline);
  border-radius: 14px;
  background: var(--color-parchment);
}
.pip-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-ink);
}
.pip-lead {
  margin: 4px 0 8px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-muted);
}
.pip-card .field {
  display: grid;
  gap: 4px;
  margin-top: 8px;
}
.pip-card .field span {
  font-size: 12px;
  color: var(--color-muted);
}
.pip-card .field input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--color-hairline);
  border-radius: 10px;
  background: var(--color-pearl);
  font-size: 13px;
  color: var(--color-ink);
}
.toggle input[data-sundome-switch] {
  appearance: none;
  width: 48px;
  height: 28px;
  margin-left: auto;
  border-radius: 999px;
  background: var(--color-soft);
  position: relative;
  flex: 0 0 auto;
  cursor: pointer;
  transition: background-color .15s ease;
}
.toggle input[data-sundome-switch]::after {
  content: '';
  position: absolute;
  top: 4px;
  left: 4px;
  width: 20px;
  height: 20px;
  border-radius: 999px;
  background: #fff;
  transition: transform .15s ease;
}
.toggle input[data-sundome-switch]:checked {
  background: var(--color-primary);
}
.toggle input[data-sundome-switch]:checked::after {
  transform: translateX(24px);
}
</style>
