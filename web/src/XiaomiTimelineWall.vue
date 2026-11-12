<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from '#imports'
import { api } from './api'
import VirtualPhotoWall from './VirtualPhotoWall.vue'
import { albumView, invalidateOtherAlbums, mergeDay, removeDayItems, timelineLabel, type TimelineDay } from './xiaomiTimeline'
import type { CloudMedia } from './xiaomiMedia'
import type { PhotoDemand } from './photoWall'

const props = defineProps<{ connection: string; album: string; disabled: boolean; isSelected: (item: CloudMedia) => boolean }>()
const emit = defineEmits<{ items: [items: CloudMedia[]]; ready: [ready: boolean]; toggleDay: [day: string, items: CloudMedia[]] }>()
const view = albumView(props.connection, props.album)
const wall = ref<{ jump: (day: string) => void }>()
const navigation = ref<HTMLElement>()
const topInset = ref(0)
const loading = ref(false)
const visible = ref<PhotoDemand[]>([])
const items = computed(() => view.days.flatMap(day => day.items))
const groups = computed(() => view.days.filter(day => day.count > 0).map(day => ({ key: day.date, label: timelineLabel(day.date), count: day.count, items: day.items })))
const months = computed(() => {
  const result = new Map<string, { key: string; date: string; count: number }>()
  for (const day of view.days) {
    if (!day.count) continue
    const key = day.date.slice(0, 6)
    if (!result.has(key)) result.set(key, { key, date: day.date, count: 0 })
    result.get(key)!.count += day.count
  }
  return [...result.values()]
})
const total = computed(() => view.days.reduce((sum, day) => sum + day.count, 0))
const controller = new AbortController()
let disposed = false
let running = 0
let revision = 0
let restoring = true
let leaving = false

function query(values: Record<string, string>) { return new URLSearchParams({ connection: props.connection, album: props.album, ...values }) }
watch(items, value => emit('items', value), { immediate: true })
watch(() => view.ready, value => emit('ready', value), { immediate: true })
watch(() => props.disabled, () => pump())
watch(() => view.days.map(day => day.loading), () => pump(), { flush: 'post' })
function measureNavigation() {
  topInset.value = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--workbench-top'))
    + (window.innerWidth < 760 ? navigation.value?.offsetHeight ?? 0 : 0)
}
watch(navigation, measureNavigation, { flush: 'post' })

async function index() {
  const current = ++revision
  loading.value = true; view.error = ''; view.ready = false
  try {
    const result = await api<{ days: { date: string; count: number }[] }>(`/xiaomi/timeline?${query({})}`, undefined, 'GET', controller.signal)
    if (disposed || current !== revision) return
    view.days = result.days.map(day => ({ ...day, items: [], page: 0, removed: 0, last: false, loading: false, error: '' }))
    view.ready = true; view.stale = false; view.active = view.days[0]?.date || ''; view.scroll = 0; view.used = Date.now()
    await nextTick()
    pump()
  } catch (error) {
    if (!disposed && current === revision) view.error = (error as Error).message
  } finally { if (current === revision) loading.value = false }
}

function demand(ranges: PhotoDemand[]) {
  visible.value = ranges
  pump()
}
function pump() {
  if (disposed || restoring || props.disabled || !view.ready) return
  for (const { day: date, end } of visible.value) {
    if (running >= 2) break
    const day = view.days.find(day => day.date === date)
    // A visible day may contain thousands of photos; fetch only through the last needed row.
    if (day && day.items.length < end && !day.last && !day.loading && !day.error) void load(day)
  }
}
async function load(day: TimelineDay) {
  const current = revision
  const page = Math.max(0, day.page - Math.ceil(day.removed / 30))
  day.loading = true; running++
  try {
    const result = await api<{ items: CloudMedia[]; last: boolean }>(`/xiaomi/day?${query({ date: day.date, page: String(page) })}`, undefined, 'GET', controller.signal)
    if (disposed || current !== revision) return
    mergeDay(day, result.items, result.last, page)
  } catch (error) {
    if (!disposed && current === revision) day.error = (error as Error).message
  } finally {
    day.loading = false; running--
    if (!disposed) pump()
  }
}
function retry(day: TimelineDay) { day.error = ''; pump() }
function jump(date: string) { wall.value?.jump(date); view.active = date }
function saveScroll() { if (!restoring && !leaving) { view.scroll = window.scrollY; view.used = Date.now() } }
function leave() { saveScroll(); leaving = true }
onBeforeRouteUpdate(leave)
onBeforeRouteLeave(leave)
async function refresh() {
  view.days = []; visible.value = []; view.scroll = 0
  window.scrollTo({ top: 0, behavior: 'instant' })
  await index()
}
function remove(ids: string[]) {
  const removed = new Set(ids)
  if (items.value.filter(item => removed.has(item.id)).length !== removed.size) { void refresh(); invalidateOtherAlbums(props.connection, props.album); return }
  // A pending page may still contain recycled files; discard it before requesting the shifted page.
  revision++
  for (const day of view.days) removeDayItems(day, removed)
  invalidateOtherAlbums(props.connection, props.album)
  pump()
}
defineExpose({ refresh, remove })

onMounted(async () => {
  if (!view.ready) await index()
  await nextTick()
  if (disposed) return
  window.scrollTo({ top: view.scroll, behavior: 'instant' })
  restoring = false
  window.addEventListener('scroll', saveScroll, { passive: true })
  window.addEventListener('resize', measureNavigation)
  pump()
})
onBeforeUnmount(() => { saveScroll(); disposed = true; revision++; controller.abort(); window.removeEventListener('scroll', saveScroll); window.removeEventListener('resize', measureNavigation) })
</script>

<template>
  <div v-if="loading" class="timeline-message muted" role="status">正在读取日期索引…</div>
  <div v-else-if="view.error" class="notice error" role="alert">{{ view.error }} <button class="text-button" :disabled="disabled" @click="index">重试日期索引</button></div>
  <template v-else-if="view.ready && total">
    <div class="timeline-summary"><span>共 {{ total.toLocaleString() }} 项 · 已加载 {{ items.length.toLocaleString() }} 项</span><span>按日期加载</span></div>
    <div class="timeline-layout">
      <nav ref="navigation" class="timeline-nav" aria-label="相册时间线">
        <label class="timeline-picker">跳转年月<select :value="view.active.slice(0, 6)" @change="jump(months.find(month => month.key === ($event.target as HTMLSelectElement).value)!.date)"><option v-for="month in months" :key="month.key" :value="month.key">{{ month.key.slice(0, 4) }}年{{ Number(month.key.slice(4)) }}月 · {{ month.count }} 项</option></select></label>
        <div class="timeline-months">
          <template v-for="(month, i) in months" :key="month.key">
            <span v-if="!i || month.key.slice(0, 4) !== months[i - 1]!.key.slice(0, 4)" class="timeline-year">{{ month.key.slice(0, 4) }}</span>
            <button type="button" class="timeline-month" :class="{ active: view.active.startsWith(month.key) }" :aria-current="view.active.startsWith(month.key) ? 'date' : undefined" :aria-label="`${month.key.slice(0, 4)}年${Number(month.key.slice(4))}月，${month.count} 项`" @click="jump(month.date)"><span>{{ Number(month.key.slice(4)) }}月</span><span>{{ month.count.toLocaleString() }}</span></button>
          </template>
        </div>
      </nav>
      <div class="timeline-content">
        <div class="timeline-errors"><div v-for="day in view.days.filter(day => day.error)" :key="day.date" class="notice error" role="alert">{{ timelineLabel(day.date) }}：{{ day.error }} <button class="text-button" :disabled="disabled" @click="retry(day)">重试当日</button></div></div>
        <VirtualPhotoWall ref="wall" class="timeline-wall" :items="items" :groups="groups" :top-inset="topInset" caption :disabled="disabled" :is-selected="isSelected" @toggle-day="(day, items) => emit('toggleDay', day, items)" @demand="demand" @active-day="view.active = $event">
          <template #default="{ item }"><slot :item="item" /></template>
        </VirtualPhotoWall>
      </div>
    </div>
  </template>
  <div v-else-if="view.ready" class="empty-list">这个相册还没有图片或视频</div>
</template>

<style scoped>
@reference '../app/assets/main.css';
.timeline-message { @apply py-6 text-sm; }
.timeline-summary { @apply mb-3 flex flex-wrap justify-between gap-2 text-sm text-muted; }
.timeline-layout { @apply relative grid min-w-0 gap-4; grid-template-columns: minmax(0, 1fr) 100px; }
.timeline-content { @apply col-start-1 row-start-1 min-w-0; }
.timeline-errors { @apply sticky z-10 bg-canvas; top: var(--workbench-top); }
.timeline-nav { @apply sticky col-start-2 row-start-1 self-start overflow-auto border-l border-solid border-hairline pl-3; top: calc(var(--workbench-top) + 16px); max-height: calc(100dvh - var(--workbench-top) - 32px); }
.timeline-year { @apply mt-4 mb-1 block text-sm font-semibold first:mt-0; }
.timeline-month { @apply flex min-h-11 w-full items-center justify-between gap-2 rounded-md px-2 text-sm text-muted; }
.timeline-month span:last-child { @apply text-xs; }
.timeline-month.active { @apply bg-primary/10 font-semibold text-primary; }
.timeline-picker { @apply hidden; }
.timeline-wall { @apply grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-8 xl:grid-cols-10; }
@media (max-width: 759px) {
  .timeline-layout { @apply block; }
  .timeline-nav { @apply z-10 mb-3 border-0 bg-canvas p-0; top: var(--workbench-top); }
  .timeline-picker { @apply flex min-h-11 flex-row items-center gap-3 py-2 text-sm; }
  .timeline-picker select { @apply min-h-11 min-w-0 flex-1; }
  .timeline-months { @apply hidden; }
}
</style>
