<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { newPlaylist } from './playback'
import type { Playlist } from './playback'
import { playbackSummary } from './playback/summary'

const settings = defineModel<Playlist>({ required: true })
const props = defineProps<{ runtime?: boolean }>()
const selected = ref('playback')
const search = ref('')
const groups = computed(() => [
  { id: 'playback', label: '播放', keywords: '总时长 分钟 循环 图片 切换 时间 间隔 BPM 节奏' },
  ...(!props.runtime ? [{ id: 'media', label: '媒体', keywords: '顺序 随机 文件名 每轮 图片 数量 喜欢 收藏 去重' }] : []),
  { id: 'sound', label: '声音', keywords: '音量 视频 媒体 静音 节拍器 BPM 语音 语速 提示' },
  { id: 'display', label: '显示', keywords: '隐藏 时间 进度 明暗 亮度 画面' },
])
const visible = computed(() => groups.value.filter(group => search.value.trim()
  ? `${group.label} ${group.keywords}`.toLowerCase().includes(search.value.trim().toLowerCase()) : group.id === selected.value))
const summary = computed(() => playbackSummary(settings.value))
// 「恢复本组」只动当前分组，且要求再点一次确认，避免误触清掉还没记住的设置。
const resetArmed = ref(false)
const canReset = computed(() => !search.value.trim() && visible.value.length === 1)
const resetLabel = computed(() => resetArmed.value ? '确认恢复？' : '恢复本组')
watch([selected, search], () => { resetArmed.value = false })
watch(settings, () => { resetArmed.value = false }, { deep: true })
function selectGroup(id: string) {
  selected.value = id
  search.value = ''
  resetArmed.value = false
}
function resetGroup() {
  if (!resetArmed.value) { resetArmed.value = true; return }
  resetArmed.value = false
  const defaults = newPlaylist()
  const item = settings.value
  if (selected.value === 'playback') {
    item.imageTiming = defaults.imageTiming
    item.imageSeconds = defaults.imageSeconds
    item.minutes = defaults.minutes
    item.bpm = defaults.bpm
    item.loop = defaults.loop
  } else if (selected.value === 'media') {
    item.order = defaults.order
    item.imageCount = defaults.imageCount
    item.favoritesOnly = defaults.favoritesOnly
  } else if (selected.value === 'sound') {
    item.metronome = defaults.metronome
    item.beatVolume = defaults.beatVolume
    item.mediaVolume = defaults.mediaVolume
    item.speech = defaults.speech
    item.speechVolume = defaults.speechVolume
    item.speechRate = defaults.speechRate
  } else {
    item.hideTime = defaults.hideTime
    item.brightness = defaults.brightness
  }
}
</script>

<template>
  <div class="settings-card" :class="{ runtime }">
    <header class="card-head">
      <div class="card-heading">
        <h3 class="card-title">播放设置</h3>
        <p class="card-summary">{{ summary }}</p>
      </div>
      <button v-if="canReset" type="button" class="text-button card-reset" :title="resetArmed ? '再点一次把本组恢复为默认值' : '只把本组恢复为默认值，其他分组不变'" @click="resetGroup">{{ resetLabel }}</button>
    </header>
    <label class="settings-search">查找设置<input v-model="search" type="search" placeholder="例如：BPM、音量、图片数量" /></label>
    <div class="settings-tabs" role="group" aria-label="设置分类">
      <button v-for="group in groups" :key="group.id" type="button" :aria-pressed="!search && selected === group.id" @click="selectGroup(group.id)">{{ group.label }}</button>
    </div>
    <p v-if="!visible.length" class="muted" role="status">没有匹配的设置，请换个关键词。</p>
    <section v-for="group in visible" :key="group.id" class="settings-section" :aria-label="`${group.label}设置`">
      <h4 v-if="search" class="section-title">{{ group.label }}</h4>
      <template v-if="group.id === 'playback'">
        <div class="settings-grid">
          <label v-if="settings.kind === 'image'">图片切换<select v-model="settings.imageTiming"><option value="time">按时间</option><option value="beat">按 BPM · 每拍一张</option></select></label>
          <label v-if="settings.kind !== 'video' && (settings.kind !== 'image' || settings.imageTiming === 'time')">图片间隔（秒）<input v-model.number="settings.imageSeconds" type="number" min="1" max="300" required /></label>
          <label>总时长（分钟，0 为不限）<input v-model.number="settings.minutes" type="number" min="0" max="180" required /></label>
          <label>快速节拍（BPM）<input v-model.number="settings.bpm" type="number" min="30" max="180" required /></label>
        </div>
        <p v-if="settings.kind === 'image' && settings.imageTiming === 'beat'" class="muted">每拍发声并切一张，慢速为快速的 60%；休息时不发声、不自动切图。</p>
        <label class="toggle"><input v-model="settings.loop" type="checkbox" />循环列表</label>
      </template>
      <template v-else-if="group.id === 'media'">
        <div class="settings-grid">
          <label>播放顺序<select v-model="settings.order"><option value="shuffle">随机</option><option value="sequential">文件名顺序</option></select></label>
          <label v-if="settings.kind !== 'video'">每轮图片数（0 为全部）<input v-model.number="settings.imageCount" type="number" min="0" max="100000" required /></label>
        </div>
        <label class="toggle"><input v-model="settings.favoritesOnly" type="checkbox" />仅播放喜欢</label>
        <p v-if="settings.kind !== 'video'" class="muted">已展示图片不再入选；未展示的不足一轮时，所选图库中的图片重新参与。视频不计入图片数量。</p>
      </template>
      <template v-else-if="group.id === 'sound'">
        <label v-if="settings.kind !== 'video' && settings.kind === 'image' && settings.imageTiming === 'beat'" class="muted">BPM 切图自动启用节拍器，音量为 0 时仍按拍切图。</label>
        <label v-else class="toggle"><input v-model="settings.metronome" type="checkbox" />节拍器</label>
        <div class="settings-grid">
          <label>节拍音量 · {{ settings.beatVolume }}%<input v-model.number="settings.beatVolume" type="range" min="0" max="100" /></label>
          <label v-if="settings.kind !== 'image'">媒体音量 · {{ settings.mediaVolume }}%<input v-model.number="settings.mediaVolume" type="range" min="0" max="100" /></label>
        </div>
        <label class="toggle"><input v-model="settings.speech" type="checkbox" />语音提示阶段名称</label>
        <div v-if="settings.speech" class="settings-grid">
          <label>语音音量 · {{ settings.speechVolume }}%<input v-model.number="settings.speechVolume" type="range" min="0" max="100" /></label>
          <label>语速<select v-model.number="settings.speechRate"><option :value=".8">0.8×</option><option :value="1">1.0×</option><option :value="1.2">1.2×</option></select></label>
        </div>
      </template>
      <template v-else>
        <label class="toggle"><input v-model="settings.hideTime" type="checkbox" />隐藏时间与进度条</label>
        <label>画面亮度 · {{ settings.brightness }}%<input v-model.number="settings.brightness" type="range" min="20" max="100" /></label>
        <p class="muted">只影响播放器中的画面，不修改原文件，也不改变结束时间。</p>
      </template>
    </section>
  </div>
</template>

<style scoped>
.settings-card { padding: 20px 22px; border: 1px solid var(--color-hairline); border-radius: var(--radius-panel); background: var(--color-canvas); }
.settings-card.runtime { background: var(--color-parchment); }
.card-head { display: flex; align-items: start; justify-content: space-between; gap: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--color-hairline); }
.card-heading { display: grid; gap: 6px; min-width: 0; }
.card-title { margin: 0; font-size: 20px; line-height: 1.4; }
.card-summary { margin: 0; font-size: 14px; line-height: 1.6; color: var(--color-muted); overflow-wrap: anywhere; }
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
@media (max-width: 600px) { .settings-grid { grid-template-columns: 1fr; gap: 16px; } .settings-tabs { gap: 6px; } .settings-tabs button { flex: 1 1 auto; padding-inline: 12px; } }
@media (max-width: 560px) {
  .settings-card { padding: 16px; border-radius: 12px; }
  .card-head { flex-wrap: wrap; gap: 8px; }
  .card-heading { flex: 1 1 100%; }
  .card-title { font-size: 18px; }
  .card-reset { align-self: flex-start; }
  .settings-search { max-width: none; }
}
</style>
