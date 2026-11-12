<script setup lang="ts">
import { animate, AnimatePresence, MotionConfig, motion, useMotionValue, useReducedMotion, useTransform } from 'motion-v'
import { computed, reactive, ref, shallowRef, watch } from 'vue'
import { bytes, imageThumbnail, type LibraryPicture as Picture } from './api'
import { takenAt } from './xiaomiMedia'
import { reviewNeedsRecycle, type ReviewDecision as Decision } from './reviewSelection'
import { reviewAxis, reviewDrag, reviewWheelStep, type ReviewAxis } from './reviewGestures'
import { useBeforeUnload } from './useBeforeUnload'
import Icon from './Icon.vue'

type Navigation = 'previous' | 'next'
type ExitAction = { decision: Decision; edge: -1 | 1 }
type SlideTransition = { way: Navigation; action?: ExitAction }
type Pan = { offset: { x: number; y: number } }
const props = defineProps<{
  loadPage: (after: number) => Promise<{ items: Picture[]; next_cursor: number | null; total: number }>
  isSelected: (item: Picture) => boolean
}>()
const emit = defineEmits<{ finish: [items: Picture[], submit: boolean, kept: Picture[]]; change: [id: number] }>()
const dialog = ref<HTMLDialogElement>()
const stage = ref<HTMLDivElement>()
const queue = shallowRef<Picture[]>([])
const index = ref(0)
const total = ref(0)
const cursor = ref<number | null>(null)
const direction = shallowRef<SlideTransition>({ way: 'next' })
const step = ref<Navigation>('next')
const loading = ref(false)
const error = ref('')
const reducedMotion = useReducedMotion()
const centeredPosition = () => ({ y: useMotionValue(0) })
const position = shallowRef(centeredPosition())
const topProgress = useMotionValue(0)
const bottomProgress = useMotionValue(0)
const topOffset = useTransform(topProgress, [0, 1], [-24, 0])
const bottomOffset = useTransform(bottomProgress, [0, 1], [24, 0])
const armedEdge = ref<-1 | 0 | 1>(0)
let panning: { position: typeof position.value; axis: ReviewAxis; height: number; marked: boolean; origin: number } | undefined
const decisions = reactive(new Map<number, Decision>())
const history = reactive<{ index: number; previous?: Decision }[]>([])
const broken = reactive(new Set<number>())
const referenceFailed = ref(false)
const current = computed<Picture | undefined>(() => queue.value[index.value])
const timeSources = { taken: '拍摄时间', digitized: '数字化时间', image: '图片日期', created: '文件创建时间', modified: '修改时间' }
watch(current, item => { referenceFailed.value = false; if (item && dialog.value?.open) emit('change', item.id) })
const pending = computed(() => queue.value.filter((_, i) => needsRecycle(i)))
const currentMarked = computed(() => needsRecycle(index.value))
useBeforeUnload(() => pending.value.length > 0)
const canAdvance = computed(() => index.value + 1 < queue.value.length || cursor.value !== null)
const filmstrip = computed(() => {
  const center = Math.min(index.value, queue.value.length - 1)
  return Array.from({ length: 7 }, (_, slot) => center + slot - 3)
})
const slide = {
  enter: ({ way }: SlideTransition) => ({ opacity: 0, x: way === 'previous' ? -32 : 32, y: 0, scale: 1 }),
  visible: { opacity: 1, x: 0, y: 0, scale: 1 },
  exit: ({ way, action }: SlideTransition) => {
    const height = stage.value?.clientHeight ?? 0
    const outgoing = { opacity: 0, zIndex: 1, transition: { duration: reducedMotion.value ? 0 : .2, zIndex: { duration: 0 } } }
    if (action) return { ...outgoing, x: 0, y: action.edge * height * .2, scale: action.decision === 'recycle' ? .25 : .92 }
    return { ...outgoing, x: way === 'previous' ? 80 : -80, y: 0 }
  },
}

function open(items: Picture[], item: Picture, nextCursor: number | null, count: number) {
  queue.value = items.slice()
  index.value = items.indexOf(item)
  cursor.value = nextCursor
  total.value = count
  direction.value = { way: 'next' }
  position.value = centeredPosition()
  resetPan()
  loading.value = false
  error.value = ''
  decisions.clear(); history.length = 0; broken.clear()
  dialog.value!.returnValue = ''
  dialog.value!.showModal()
}
defineExpose({ open, close: () => dialog.value?.close() })

function finish() {
  resetPan()
  const kept = queue.value.filter((_, i) => decisions.get(i) === 'keep')
  emit('finish', pending.value, dialog.value?.returnValue === 'recycle', kept)
  queue.value = []
}
function go(target: number, action?: ExitAction) {
  if (target === index.value) { centerSlide(); return }
  direction.value = { way: target < index.value ? 'previous' : 'next', action }
  position.value = centeredPosition()
  resetPan()
  index.value = target
}
async function advance(action?: ExitAction) {
  if (loading.value || !current.value) return
  if (index.value + 1 < queue.value.length) { go(index.value + 1, action); return }
  if (cursor.value !== null) {
    const batch = queue.value
    centerSlide()
    loading.value = true
    error.value = ''
    let page: Awaited<ReturnType<typeof props.loadPage>>
    try {
      page = await props.loadPage(cursor.value)
    } catch (failure) {
      if (queue.value === batch) error.value = (failure as Error).message
      return
    } finally {
      if (queue.value === batch) loading.value = false
    }
    if (!dialog.value?.open || queue.value !== batch) return
    queue.value = batch.concat(page.items)
    cursor.value = page.next_cursor
    total.value = page.total
  }
  if (index.value + 1 < queue.value.length || action) go(index.value + 1, action)
}
function previous(action?: ExitAction) {
  if (loading.value) return
  if (index.value > 0) go(index.value - 1, action)
  else centerSlide()
}
function decide(decision: Decision, edge: -1 | 1 = 1) {
  if (loading.value || !current.value) return
  const before = decisions.get(index.value)
  if (before !== decision) {
    history.push({ index: index.value, previous: before })
    decisions.set(index.value, decision)
  }
  const action = { decision, edge }
  if (step.value === 'previous') previous(action)
  else void advance(action)
}
function undo() {
  if (loading.value) return
  const last = history.pop()
  if (!last) return
  if (last.previous) decisions.set(last.index, last.previous)
  else decisions.delete(last.index)
  go(last.index)
}
function resetPan() {
  panning = undefined
  armedEdge.value = 0
  for (const value of [topProgress, bottomProgress]) {
    value.stop()
    if (reducedMotion.value) value.jump(0)
    else animate(value, 0, { duration: .16 })
  }
}
function centerSlide() {
  resetPan()
  const value = position.value.y
  if (reducedMotion.value) value.jump(0)
  else animate(value, 0, { type: 'spring', stiffness: 480, damping: 36 })
}
function startPan() {
  if (!current.value || loading.value) return
  topProgress.jump(0); bottomProgress.jump(0)
  armedEdge.value = 0
  position.value.y.stop()
  panning = { position: position.value, axis: null, height: stage.value!.clientHeight, marked: currentMarked.value, origin: position.value.y.get() }
}
function trackPan(_: PointerEvent, { offset: { x, y } }: Pan) {
  if (!panning || panning.position !== position.value || loading.value || !dialog.value?.open) return
  panning.axis = reviewAxis(panning.axis, x, y)
  if (panning.axis === 'horizontal') { position.value.y.jump(0); return }
  if (panning.axis !== 'vertical') return
  const drag = reviewDrag(panning.origin + y, panning.height, panning.marked)
  position.value.y.set(drag.y)
  topProgress.set(drag.top); bottomProgress.set(drag.bottom)
  armedEdge.value = drag.edge
}
function panEnd(event: PointerEvent, info: Pan) {
  if (!panning || panning.position !== position.value || !dialog.value?.open) return
  if (event.type === 'pointerup') trackPan(event, info)
  const { axis, marked } = panning
  const edge = armedEdge.value
  panning = undefined
  if (event.type !== 'pointerup' || loading.value) { centerSlide(); return }
  const { x } = info.offset
  if (axis === 'horizontal' && Math.abs(x) >= 56) {
    if (x > 0 && index.value > 0) { previous(); return }
    if (x < 0 && canAdvance.value) { void advance(); return }
  } else if (axis === 'vertical' && edge) {
    decide(marked ? 'keep' : 'recycle', edge)
    return
  }
  centerSlide()
}
function keys(event: KeyboardEvent) {
  if (event.altKey || event.shiftKey) return
  if (event.ctrlKey || event.metaKey) {
    if (event.key.toLowerCase() === 'z') {
      event.preventDefault()
      if (!event.repeat) undo()
    }
    return
  }
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
  event.preventDefault()
  if (event.repeat) return
  if (event.key === 'ArrowLeft') previous()
  else if (event.key === 'ArrowRight') void advance()
  else decide(currentMarked.value ? 'keep' : 'recycle', event.key === 'ArrowUp' ? -1 : 1)
}
function wheel(event: WheelEvent) {
  if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return
  const offset = reviewWheelStep(event.deltaX, event.deltaY)
  if (!offset) return
  event.preventDefault()
  if (offset < 0) previous()
  else void advance()
}
function hasPreview(item: Picture) { return !!item.width && !item.error && !broken.has(item.id) }
function markBroken(event: Event) { broken.add(Number((event.currentTarget as HTMLImageElement).dataset.imageId)) }
function needsRecycle(i: number) {
  const item = queue.value[i]
  return !!item && reviewNeedsRecycle(decisions.get(i), props.isSelected(item))
}
</script>

<template>
  <dialog ref="dialog" class="task-dialog image-review" aria-labelledby="review-title" @close="finish" @keydown="keys">
    <div class="review-layout">
      <header class="review-heading">
        <h2 id="review-title">快速审阅</h2>
        <span class="muted review-count">{{ Math.min(index + 1, queue.length) }} / {{ Math.max(queue.length, total) }}</span>
        <button class="icon-button" autofocus aria-label="关闭快速审阅" @click="dialog?.close()"><Icon name="close" /></button>
      </header>

      <MotionConfig reduced-motion="user" :transition="{ duration: reducedMotion ? 0 : .2 }">
        <div ref="stage" class="review-stage" @wheel="wheel"
          @mousedown.middle.prevent="decide(currentMarked ? 'keep' : 'recycle')" @auxclick.middle.prevent>
          <motion.div class="review-swipe" @panStart="startPan" @pan="trackPan" @panEnd="panEnd">
            <AnimatePresence :initial="false" :custom="direction">
              <motion.div v-if="current" :key="current.id" class="review-slide" :custom="direction" :variants="slide" initial="enter" animate="visible" exit="exit">
                <motion.div class="review-drag" :style="current.saved_match ? undefined : position"><div class="review-picture" :class="{ 'in-recycle-zone': !current.saved_match && armedEdge !== 0 && !currentMarked }">
                <div v-if="current.saved_match && hasPreview(current)" class="review-comparison">
                  <motion.figure class="comparison-current" :style="position" :class="{ 'in-recycle-zone': armedEdge !== 0 && !currentMarked }"><figcaption>下载图片 · {{ current.width }} × {{ current.height }} · {{ bytes(current.size) }}</figcaption><img :src="/\.(tif|tiff)$/i.test(current.name) ? imageThumbnail(current) : `/api/images/${current.id}/original?version=${encodeURIComponent(current.version)}`" :alt="current.name" :data-image-id="current.id" draggable="false" @error="markBroken" /></motion.figure>
                  <figure><figcaption>已存图片 · {{ current.saved_match.width }} × {{ current.saved_match.height }} · {{ bytes(current.saved_match.size) }}</figcaption><img v-if="!referenceFailed" :src="`/api/images/${current.id}/saved/${/\.(tif|tiff)$/i.test(current.saved_match.path) ? 'thumbnail' : 'original'}?version=${encodeURIComponent(current.version)}`" :alt="current.saved_match.path" draggable="false" @error="referenceFailed = true" /><p v-else class="review-empty">已存原图不可用，请刷新后重新检查</p></figure>
                </div>
                <img v-else-if="hasPreview(current)" :src="imageThumbnail(current)" :alt="current.name" :data-image-id="current.id" draggable="false" @error="markBroken" />
                <p v-else class="review-empty"><Icon name="photo" :size="34" />{{ current.error || (broken.has(current.id) ? '图片预览加载失败' : '图片预览尚未生成') }}</p>
                </div></motion.div>
              </motion.div>
              <motion.div v-else-if="queue.length" key="end" class="review-slide review-empty" :custom="direction" :variants="slide" initial="enter" animate="visible" exit="exit">
                已到队列末尾
              </motion.div>
            </AnimatePresence>
            <motion.div class="review-drop-zone top" :class="{ armed: armedEdge === -1 }" :style="{ opacity: topProgress, y: topOffset }" aria-hidden="true"><Icon name="trash" :size="26" /><span>{{ armedEdge === -1 ? '松手标记回收' : '拖入回收区' }}</span></motion.div>
            <motion.div class="review-drop-zone bottom" :class="{ armed: armedEdge === 1 }" :style="{ opacity: bottomProgress, y: bottomOffset }" aria-hidden="true"><Icon name="trash" :size="26" /><span>{{ armedEdge === 1 ? '松手标记回收' : '拖入回收区' }}</span></motion.div>
          </motion.div>
          <span v-if="currentMarked" class="review-mark" :class="{ releasing: armedEdge !== 0 }"><Icon :name="armedEdge ? 'restore' : 'trash'" :size="18" />{{ armedEdge ? '松手取消回收' : '已标记回收' }}</span>
          <button class="icon-button review-arrow review-previous" :disabled="!index || loading" aria-label="上一张" @click="previous()"><Icon name="chevron" /></button>
          <button class="icon-button review-arrow review-next" :disabled="!canAdvance || loading" aria-label="下一张" @click="advance()"><Icon name="chevron" /></button>
        </div>
      </MotionConfig>

      <div class="review-caption" aria-live="polite">
        <template v-if="current">
          <div class="min-w-0 flex-1"><strong :title="current.name">{{ current.name }}</strong><small class="block text-xs text-muted">{{ current.time_source ? timeSources[current.time_source] : '索引时间' }} · {{ takenAt(current.sort_time) }}</small></div>
          <span v-if="needsRecycle(index)" class="text-danger">待回收</span>
          <span class="muted">{{ bytes(current.size) }}</span>
        </template>
        <span v-else class="muted">已审阅 {{ decisions.size }} 张</span>
      </div>

      <div v-if="current?.saved_match" class="saved-evidence"><span class="badge">重复图</span><span class="min-w-0 truncate" :title="`${current.saved_match.root}/${current.saved_match.path}`">已存于 {{ current.saved_match.root }}/{{ current.saved_match.path }}</span><span class="shrink-0">SSIM {{ current.saved_match.ssim.toFixed(5) }}</span></div>
      <p v-if="current?.saved_error" class="notice error" role="alert">已存检查未完成：{{ current.saved_error }}</p>

      <div class="review-filmstrip" role="group" aria-label="审阅队列">
        <div v-for="(position, slot) in filmstrip" :key="slot" class="review-slot">
          <button v-if="queue[position]" :key="queue[position].id" :aria-current="position === index ? 'true' : undefined" :disabled="loading"
            :aria-label="queue[position].name + (needsRecycle(position) ? '，待回收' : '')"
            @click="go(position)">
            <img v-if="hasPreview(queue[position])" :src="imageThumbnail(queue[position])" :data-image-id="queue[position].id" alt="" draggable="false" decoding="async" @error="markBroken" />
            <Icon v-else name="photo" :size="17" />
            <span v-if="needsRecycle(position)" class="review-stamp"><Icon name="trash" :size="13" /></span>
          </button>
        </div>
      </div>

      <p v-if="error" class="notice error review-status" role="alert">加载下一批图片失败：{{ error }}</p>
      <p v-else-if="loading" class="muted review-status" role="status">正在加载下一批图片…</p>
      <footer class="review-actions">
        <div class="review-options">
          <span class="text-sm text-muted">操作后</span>
          <div class="review-order" role="group" aria-label="标记或取消回收后的跳转方向">
            <button type="button" :aria-pressed="step === 'previous'" :disabled="loading" @click="step = 'previous'"><Icon name="chevron" class="rotate-180" :size="14" />上一张</button>
            <button type="button" :aria-pressed="step === 'next'" :disabled="loading" @click="step = 'next'">下一张<Icon name="chevron" :size="14" /></button>
          </div>
        </div>
        <button class="secondary recycle" :disabled="!current || loading" aria-keyshortcuts="ArrowUp ArrowDown" @click="decide(currentMarked ? 'keep' : 'recycle')"><Icon :name="currentMarked ? 'restore' : 'trash'" :size="17" />{{ currentMarked ? '取消回收' : current?.saved_match ? '标记回收下载图' : '标记回收' }} <kbd>↑ / ↓</kbd></button>
        <button class="secondary" :disabled="!history.length || loading" aria-keyshortcuts="Control+Z Meta+Z" @click="undo">撤销</button>
        <button v-if="pending.length" class="danger" @click="dialog?.close('recycle')">移入回收站 · {{ pending.length }} 张</button>
      </footer>
    </div>
  </dialog>
</template>

<style scoped>
@reference '../app/assets/main.css';

.image-review {
  width: min(1020px, calc(100% - 32px)); height: calc(100dvh - 32px); max-height: none;
  @apply overscroll-contain bg-canvas p-0;
}
.review-layout { @apply flex h-full min-h-full flex-col gap-3 overflow-y-auto px-5 py-4; }
.review-heading { @apply grid grid-cols-[1fr_auto_1fr] items-center gap-2; }
.review-heading button { @apply justify-self-end; }
.review-count { @apply tabular-nums; }
.review-stage { @apply relative min-h-[140px] flex-1 shrink-0 overflow-hidden rounded-lg bg-media; }
.review-swipe { @apply absolute inset-0 isolate cursor-grab touch-none select-none; }
.review-swipe:active { @apply cursor-grabbing; }
.review-slide { @apply pointer-events-none absolute inset-0 flex items-center justify-center px-[52px] py-2.5; }
.review-slide img { @apply block size-full min-h-0 object-contain; }
.review-drag, .review-picture { @apply flex size-full min-h-0 items-center justify-center; }
.review-comparison { @apply grid size-full min-h-0 grid-cols-2 gap-3; }
.review-comparison figure { @apply m-0 flex min-h-0 min-w-0 flex-col gap-2; }
.review-comparison figcaption { @apply text-center text-xs text-muted; }
.review-comparison img { @apply h-0 min-h-0 w-full flex-1 object-contain; }
.comparison-current { transition: transform .14s ease-out, filter .14s ease-out, opacity .14s ease-out; }
.comparison-current.in-recycle-zone { transform: scale(.78); opacity: .55; }
.saved-evidence { @apply flex min-w-0 items-center gap-3 text-xs text-muted; }
.review-picture { transition: transform .14s ease-out, filter .14s ease-out, opacity .14s ease-out; }
.review-picture.in-recycle-zone { transform: scale(.78); opacity: .55; }
.review-empty { @apply flex flex-col items-center justify-center gap-2.5 text-center text-muted; }
.review-drop-zone { height: min(25%, 120px); @apply pointer-events-none absolute inset-x-2 z-[2] flex flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-danger/30 bg-danger/10 text-xs text-danger; }
.review-drop-zone.top { @apply top-0; }
.review-drop-zone.bottom { @apply bottom-0; }
.review-drop-zone.armed { @apply border-danger bg-danger/20; }
.review-mark { @apply pointer-events-none absolute bottom-3 left-3 z-[3] inline-flex items-center gap-1.5 rounded-full border border-solid border-danger/30 bg-canvas/95 px-3 py-2 text-sm text-danger; }
.review-mark.releasing { @apply text-success; }
.review-arrow { @apply absolute top-1/2 z-[4] -translate-y-1/2 border border-solid border-hairline bg-canvas; }
.review-previous { @apply left-1.5; }
.review-previous svg { rotate: 180deg; }
.review-next { @apply right-1.5; }
.review-caption { @apply flex min-h-[22px] items-center gap-3; }
.review-caption strong { @apply block min-w-0 truncate; }
.review-caption span { @apply flex-none; }
.review-caption .muted { @apply ml-auto; }
.review-actions .recycle { @apply text-danger; }
.review-filmstrip { @apply mx-auto grid w-full max-w-[472px] auto-cols-fr grid-flow-col gap-1.5; }
.review-slot button { @apply relative grid aspect-square w-full place-items-center rounded-lg bg-media p-0 text-muted; }
.review-slot button[aria-current] { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.review-slot button:focus-visible { outline: 3px solid var(--color-primary-focus); outline-offset: 3px; }
.review-slot img { @apply absolute inset-0 size-full object-cover; border-radius: inherit; }
.review-stamp { @apply absolute right-[3px] bottom-[3px] grid size-5 place-items-center rounded-full bg-danger text-white; }
.review-status { @apply text-center; }
.review-options { @apply flex shrink-0 items-center justify-center gap-3; }
.review-order { @apply inline-flex gap-0.5 rounded-lg bg-soft p-0.5; }
.review-order button { @apply inline-flex min-h-[44px] items-center justify-center gap-1 rounded-md px-3 text-sm text-muted; }
.review-order button[aria-pressed=true] { @apply bg-selection font-semibold text-primary; }
.review-actions { @apply flex shrink-0 flex-wrap items-center justify-center gap-2; }
.review-actions > button { @apply min-h-[44px] gap-1.5 px-3 py-2; }
.review-actions kbd { @apply text-muted; }
@media (max-width: 600px) {
  .image-review { width: 100%; height: 100dvh; max-width: none; margin: 0; border-radius: 0; }
  .review-layout { padding: max(10px, env(safe-area-inset-top)) 12px max(12px, env(safe-area-inset-bottom)); gap: 10px; }
  .review-slide { padding-inline: 8px; }
  .review-arrow { background: color-mix(in srgb, var(--color-canvas) 88%, transparent); }
  .review-options { @apply gap-1.5; }
  .review-order button { @apply px-1.5; }
  .review-order svg { @apply hidden; }
  .review-actions > button { @apply px-2; }
  .review-actions kbd { display: none; }
}
@media (max-width: 420px) {
  .review-slot:first-child, .review-slot:last-child { display: none; }
}
</style>
