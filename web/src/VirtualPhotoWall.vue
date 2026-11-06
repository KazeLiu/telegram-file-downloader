<script setup lang="ts" generic="T extends WallPhoto">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { defaultRangeExtractor, useWindowVirtualizer } from '@tanstack/vue-virtual'
import Icon from './Icon.vue'
import { groupPhotos, photoRows, type WallPhoto } from './photoWall'

const props = defineProps<{ items: T[]; caption?: boolean; disabled: boolean; isSelected: (item: T) => boolean }>()
const emit = defineEmits<{ toggleDay: [day: string, items: T[]] }>()
const wall = ref<HTMLDivElement>()
const columns = ref(1)
const width = ref(0)
const gap = ref(0)
const margin = ref(0)
const focusedRow = ref<string | null>(null)
const groups = computed(() => groupPhotos(props.items))
const rows = computed(() => photoRows(groups.value, columns.value))
const photoHeight = computed(() => (width.value - gap.value * (columns.value - 1)) / columns.value + (props.caption ? 20 : 0) + gap.value)
const dayStates = computed(() => new Map(groups.value.map(group => {
  const count = group.items.filter(props.isSelected).length
  return [group.key, count === 0 ? false : count === group.items.length ? true : 'mixed'] as const
})))
const virtualizer = useWindowVirtualizer(computed(() => {
  const data = rows.value
  const height = photoHeight.value
  const focus = data.findIndex(row => row.key === focusedRow.value)
  return {
    count: data.length, overscan: 4, scrollMargin: margin.value,
    getItemKey: (index: number) => data[index]!.key,
    estimateSize: (index: number) => data[index]!.kind === 'day' ? 44 : height,
    rangeExtractor: (range: Parameters<typeof defaultRangeExtractor>[0]) => {
      const indexes = defaultRangeExtractor(range)
      // Keep keyboard focus and its neighbouring rows mounted when scrolling with the mouse.
      if (focus >= 0) for (let i = Math.max(0, focus - 1); i <= Math.min(data.length - 1, focus + 1); i++) indexes.push(i)
      return [...new Set(indexes)].sort((a, b) => a - b)
    },
  }
}))
const visibleRows = computed(() => virtualizer.value.getVirtualItems().flatMap(virtual => {
  const row = rows.value[virtual.index]
  return row ? [{ virtual, row }] : []
}))
const totalHeight = computed(() => virtualizer.value.getTotalSize())
let observer: ResizeObserver
let layoutRevision = 0

function measure() {
  const element = wall.value!
  const rect = element.getBoundingClientRect()
  if (!rect.width) return
  const style = getComputedStyle(element)
  const nextColumns = style.gridTemplateColumns.split(' ').filter(Boolean).length
  const resizing = width.value > 0 && (width.value !== rect.width || columns.value !== nextColumns)
  const anchor = resizing && window.scrollY > margin.value
    ? virtualizer.value.getVirtualItems().find(item => item.end > window.scrollY && rows.value[item.index]?.kind === 'photos') : undefined
  const photo = anchor ? rows.value[anchor.index]!.items[0] : undefined
  const fraction = anchor ? (window.scrollY - anchor.start) / anchor.size : 0
  width.value = rect.width
  columns.value = nextColumns
  gap.value = parseFloat(style.columnGap)
  margin.value = rect.top + window.scrollY
  if (photo) {
    let top = margin.value
    for (const row of rows.value) {
      if (row.items.some(item => item.id === photo.id)) { top += fraction * photoHeight.value; break }
      top += row.kind === 'day' ? 44 : photoHeight.value
    }
    const revision = ++layoutRevision
    // Apply the anchor after the spacer grows, otherwise the browser clamps the new scroll offset.
    void nextTick(() => { if (wall.value?.isConnected && revision === layoutRevision) window.scrollTo({ top, behavior: 'instant' }) })
  }
}
function focus(event: FocusEvent) {
  focusedRow.value = (event.target as HTMLElement).closest<HTMLElement>('[data-wall-row]')?.dataset.wallRow || null
}
function blur(event: FocusEvent) {
  if (!wall.value?.contains(event.relatedTarget as Node | null)) focusedRow.value = null
}
onMounted(() => {
  measure()
  observer = new ResizeObserver(measure)
  observer.observe(wall.value!)
  observer.observe(wall.value!.parentElement!)
  window.addEventListener('resize', measure)
})
onUnmounted(() => { observer.disconnect(); window.removeEventListener('resize', measure) })
</script>

<template>
  <div ref="wall" class="virtual-photo-wall" role="list" @focusin="focus" @focusout="blur">
    <div class="virtual-photo-space" role="presentation" :style="{ height: `${totalHeight}px` }">
      <div v-for="{ virtual, row } in visibleRows" :key="row.key" class="virtual-photo-row" :data-wall-row="row.key" role="presentation"
        :style="{ height: `${virtual.size}px`, transform: `translateY(${virtual.start - margin}px)`, gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`, columnGap: `${gap}px` }">
        <h3 v-if="row.kind === 'day'" class="wall-day">
          <button type="button" role="checkbox" class="day-select" :aria-checked="dayStates.get(row.group.key)" :disabled="disabled"
            :aria-label="`${dayStates.get(row.group.key) === true ? '取消选择' : '选择'} ${row.group.key} 已加载的 ${row.group.items.length} 项`"
            title="选择这一天已加载的图片，后续加载的同日图片会继续选中" @click="emit('toggleDay', row.group.key, row.group.items)">
            <span class="day-check" :class="{ checked: dayStates.get(row.group.key) !== false }"><Icon v-if="dayStates.get(row.group.key) === true" name="check" :size="14" /><span v-else-if="dayStates.get(row.group.key) === 'mixed'" class="day-mixed" /></span>
            <span>{{ row.group.key }}</span><span class="text-xs text-muted">{{ row.group.items.length }} 项</span>
          </button>
        </h3>
        <div v-for="(item, index) in row.items" :key="item.id" class="virtual-photo-cell" role="listitem" :aria-posinset="row.start + index + 1" :aria-setsize="items.length"><slot :item="item" /></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@reference '../app/assets/main.css';
.virtual-photo-wall { overflow-anchor: none; }
.virtual-photo-space { @apply relative col-span-full min-w-0; }
.virtual-photo-row { @apply absolute top-0 left-0 grid w-full items-start; }
.virtual-photo-cell { @apply min-w-0; }
.wall-day { @apply col-span-full m-0 min-w-0 text-sm font-medium; }
.day-select { @apply flex min-h-[44px] max-w-full items-center gap-2 p-0 text-left; }
.day-check { @apply grid size-[18px] shrink-0 place-items-center rounded-sm border border-solid border-hairline bg-canvas; }
.day-check.checked { @apply border-blue bg-blue text-white; }
.day-mixed { @apply h-0.5 w-2 bg-current; }
</style>
