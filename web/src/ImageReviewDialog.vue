<script setup lang="ts">
import { animate, AnimatePresence, MotionConfig, motion, useMotionValue, useReducedMotion } from 'motion-v'
import { computed, reactive, ref, shallowRef, watch } from 'vue'
import { bytes, imageThumbnail, type LibraryPicture as Picture } from './api'
import Icon from './Icon.vue'

type Decision = 'keep' | 'recycle'
type Direction = 'previous' | 'next' | Decision
type Pan = { offset: { x: number; y: number } }
const props = defineProps<{
  loadPage: (after: number) => Promise<{ items: Picture[]; next_cursor: number | null; total: number }>
}>()
const emit = defineEmits<{ finish: [items: Picture[], submit: boolean]; change: [id: number] }>()
const dialog = ref<HTMLDialogElement>()
const stage = ref<HTMLDivElement>()
const queue = shallowRef<Picture[]>([])
const index = ref(0)
const total = ref(0)
const cursor = ref<number | null>(null)
const direction = ref<Direction>('next')
const loading = ref(false)
const error = ref('')
const reducedMotion = useReducedMotion()
const centeredPosition = () => ({ x: useMotionValue(0), y: useMotionValue(0) })
const position = shallowRef(centeredPosition())
let panning: typeof position.value | undefined
const decisions = reactive(new Map<number, Decision>())
const history = reactive<{ index: number; previous?: Decision }[]>([])
const broken = reactive(new Set<number>())
const current = computed<Picture | undefined>(() => queue.value[index.value])
watch(current, item => { if (item && dialog.value?.open) emit('change', item.id) })
const pending = computed(() => queue.value.filter((_, i) => needsRecycle(i)))
const canAdvance = computed(() => index.value + 1 < queue.value.length || cursor.value !== null)
const filmstrip = computed(() => {
  const center = Math.min(index.value, queue.value.length - 1)
  return Array.from({ length: 7 }, (_, slot) => center + slot - 3)
})
const slide = {
  enter: (way: Direction) => way === 'keep' || way === 'recycle'
    ? { opacity: 0, scale: .93 }
    : { opacity: 0, x: way === 'previous' ? -32 : 32 },
  visible: { opacity: 1, x: 0, y: 0, scale: 1 },
  exit: (way: Direction) => {
    const width = stage.value?.clientWidth ?? 0
    const height = stage.value?.clientHeight ?? 0
    const outgoing = { opacity: 0, zIndex: 1, transition: { duration: .24, zIndex: { duration: 0 } } }
    if (way === 'recycle') return { ...outgoing, x: 0, y: height * .4, scale: .14, rotate: -8 }
    if (way === 'keep') return { ...outgoing, x: 0, y: -height, scale: .96 }
    return { ...outgoing, x: way === 'previous' ? width : -width, y: 0 }
  },
}

function open(items: Picture[], item: Picture, nextCursor: number | null, count: number) {
  queue.value = items.slice()
  index.value = items.indexOf(item)
  cursor.value = nextCursor
  total.value = count
  direction.value = 'next'
  position.value = centeredPosition()
  panning = undefined
  loading.value = false
  error.value = ''
  decisions.clear(); history.length = 0; broken.clear()
  dialog.value!.returnValue = ''
  dialog.value!.showModal()
}
defineExpose({ open, close: () => dialog.value?.close() })

function finish() {
  emit('finish', pending.value, dialog.value?.returnValue === 'recycle')
  queue.value = []
}
function go(target: number, way: Direction) {
  if (target === index.value) return
  direction.value = way
  position.value = centeredPosition()
  index.value = target
}
async function advance(way: 'next' | Decision) {
  if (loading.value || !current.value) return
  if (index.value + 1 < queue.value.length) { go(index.value + 1, way); return }
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
  if (index.value + 1 < queue.value.length || way !== 'next') go(index.value + 1, way)
}
function previous() {
  if (!loading.value && index.value > 0) go(index.value - 1, 'previous')
}
function decide(decision: Decision) {
  if (loading.value || !current.value) return
  const previous = decisions.get(index.value)
  if (previous !== decision) {
    history.push({ index: index.value, previous })
    decisions.set(index.value, decision)
  }
  void advance(decision)
}
function undo() {
  if (loading.value) return
  const last = history.pop()
  if (!last) return
  if (last.previous) decisions.set(last.index, last.previous)
  else decisions.delete(last.index)
  go(last.index, 'previous')
}
function centerSlide() {
  for (const value of [position.value.x, position.value.y]) {
    if (reducedMotion.value) value.jump(0)
    else if (value.get()) animate(value, 0, { type: 'spring', stiffness: 480, damping: 36 })
  }
}
function startPan() {
  if (!current.value || loading.value) return
  panning = position.value
  panning.x.stop()
  panning.y.stop()
}
function trackPan(_: PointerEvent, { offset: { x, y } }: Pan) {
  if (panning !== position.value || loading.value || !dialog.value?.open) return
  panning.x.set(x)
  panning.y.set(y)
}
function panEnd(event: PointerEvent, info: Pan) {
  if (panning !== position.value || !dialog.value?.open) return
  if (event.type === 'pointerup') trackPan(event, info)
  panning = undefined
  if (event.type !== 'pointerup' || loading.value) { centerSlide(); return }
  const { x, y } = info.offset
  const horizontal = Math.abs(x), vertical = Math.abs(y)
  if (horizontal >= 56 && horizontal > vertical * 1.25) {
    if (x > 0 && index.value > 0) { previous(); return }
    if (x < 0 && canAdvance.value) { void advance('next'); return }
  } else if (vertical >= 56 && vertical > horizontal * 1.25) {
    decide(y < 0 ? 'keep' : 'recycle')
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
  else if (event.key === 'ArrowRight') void advance('next')
  else decide(event.key === 'ArrowUp' ? 'keep' : 'recycle')
}
function hasPreview(item: Picture) { return !!item.width && !item.error && !broken.has(item.id) }
function markBroken(event: Event) { broken.add(Number((event.currentTarget as HTMLImageElement).dataset.imageId)) }
function needsRecycle(i: number) { return decisions.get(i) === 'recycle' }
</script>

<template>
  <dialog ref="dialog" class="task-dialog image-review" aria-labelledby="review-title" @close="finish" @keydown="keys">
    <div class="review-layout">
      <header class="review-heading">
        <h2 id="review-title">快速审阅</h2>
        <span class="muted review-count">{{ Math.min(index + 1, queue.length) }} / {{ Math.max(queue.length, total) }}</span>
        <button class="icon-button" autofocus aria-label="关闭快速审阅" @click="dialog?.close()"><Icon name="close" /></button>
      </header>

      <MotionConfig reduced-motion="user" :transition="{ duration: .2 }">
        <div ref="stage" class="review-stage">
          <motion.div class="review-swipe" @panStart="startPan" @pan="trackPan" @panEnd="panEnd">
            <AnimatePresence :initial="false" :custom="direction">
              <motion.div v-if="current" :key="current.id" class="review-slide" :style="position" :custom="direction" :variants="slide" initial="enter" animate="visible" exit="exit">
                <img v-if="hasPreview(current)" :src="imageThumbnail(current)" :alt="current.name" :data-image-id="current.id" draggable="false" @error="markBroken" />
                <p v-else class="review-empty"><Icon name="photo" :size="34" />{{ current.error || (broken.has(current.id) ? '图片预览加载失败' : '图片预览尚未生成') }}</p>
              </motion.div>
              <motion.div v-else-if="queue.length" key="end" class="review-slide review-empty" :custom="direction" :variants="slide" initial="enter" animate="visible" exit="exit">
                已到队列末尾
              </motion.div>
            </AnimatePresence>
            <motion.span v-if="direction === 'recycle'" :key="index" class="review-bin" aria-hidden="true" :initial="{ opacity: 0 }"
              :animate="{ opacity: [0, 1, 1, 0] }" :transition="{ duration: .4 }"><Icon name="trash" :size="22" /></motion.span>
          </motion.div>
          <button class="icon-button review-arrow review-previous" :disabled="!index || loading" aria-label="上一张" @click="previous"><Icon name="chevron" /></button>
          <button class="icon-button review-arrow review-next" :disabled="!canAdvance || loading" aria-label="下一张" @click="advance('next')"><Icon name="chevron" /></button>
        </div>
      </MotionConfig>

      <div class="review-caption" aria-live="polite">
        <template v-if="current">
          <strong :title="current.name">{{ current.name }}</strong>
          <span v-if="needsRecycle(index)" class="text-danger">待回收</span>
          <span class="muted">{{ bytes(current.size) }}</span>
        </template>
        <span v-else class="muted">已审阅 {{ decisions.size }} 张</span>
      </div>

      <div class="review-filmstrip" role="group" aria-label="审阅队列">
        <div v-for="(position, slot) in filmstrip" :key="slot" class="review-slot">
          <button v-if="queue[position]" :key="queue[position].id" :aria-current="position === index ? 'true' : undefined" :disabled="loading"
            :aria-label="queue[position].name + (needsRecycle(position) ? '，待回收' : '')"
            @click="go(position, position < index ? 'previous' : 'next')">
            <img v-if="hasPreview(queue[position])" :src="imageThumbnail(queue[position])" :data-image-id="queue[position].id" alt="" draggable="false" decoding="async" @error="markBroken" />
            <Icon v-else name="photo" :size="17" />
            <span v-if="needsRecycle(position)" class="review-stamp"><Icon name="trash" :size="13" /></span>
          </button>
        </div>
      </div>

      <p v-if="error" class="notice error review-status" role="alert">加载下一批图片失败：{{ error }}</p>
      <p v-else-if="loading" class="muted review-status" role="status">正在加载下一批图片…</p>
      <footer class="review-actions">
        <button class="secondary" :disabled="!current || loading" aria-keyshortcuts="ArrowUp" @click="decide('keep')">保留 <kbd>↑</kbd></button>
        <button class="secondary recycle" :disabled="!current || loading" aria-keyshortcuts="ArrowDown" @click="decide('recycle')"><Icon name="trash" :size="17" />标记回收 <kbd>↓</kbd></button>
        <button class="secondary" :disabled="!history.length || loading" aria-keyshortcuts="Control+Z Meta+Z" @click="undo">撤销</button>
        <button v-if="pending.length" class="danger" @click="dialog?.close('recycle')">移入回收站 · {{ pending.length }} 张</button>
      </footer>
    </div>
  </dialog>
</template>

<style scoped>
@reference '../app/assets/main.css';

.image-review {
  width: min(1020px, calc(100% - 32px)); height: min(830px, calc(100dvh - 32px)); max-height: none;
  @apply overscroll-contain bg-canvas p-0;
}
.review-layout { @apply flex h-full min-h-full flex-col gap-3 px-5 py-4; }
.review-heading { @apply grid grid-cols-[1fr_auto_1fr] items-center gap-2; }
.review-heading button { @apply justify-self-end; }
.review-count { @apply tabular-nums; }
.review-stage { @apply relative min-h-[140px] flex-1 overflow-hidden rounded-xl bg-parchment; }
.review-swipe { @apply absolute inset-0 isolate cursor-grab touch-none select-none; }
.review-swipe:active { @apply cursor-grabbing; }
.review-slide { @apply pointer-events-none absolute inset-0 flex items-center justify-center px-[52px] py-2.5; }
.review-slide img { @apply block size-full min-h-0 object-contain; }
.review-empty { @apply flex flex-col items-center justify-center gap-2.5 text-center text-muted; }
.review-bin { @apply pointer-events-none absolute bottom-[10%] left-1/2 z-[2] -translate-x-1/2 translate-y-1/2 rounded-full bg-danger p-2.5 text-white; }
.review-arrow { @apply absolute top-1/2 -translate-y-1/2 bg-canvas shadow-sm; }
.review-previous { @apply left-1.5; }
.review-previous svg { rotate: 180deg; }
.review-next { @apply right-1.5; }
.review-caption { @apply flex min-h-[22px] items-center gap-3; }
.review-caption strong { @apply min-w-0 truncate; }
.review-caption span { @apply flex-none; }
.review-caption .muted { @apply ml-auto; }
.review-actions .recycle { @apply text-danger; }
.review-filmstrip { @apply mx-auto grid w-full max-w-[472px] auto-cols-fr grid-flow-col gap-1.5; }
.review-slot button { @apply relative grid aspect-square w-full place-items-center rounded-lg bg-parchment p-0 text-muted; }
.review-slot button[aria-current] { outline: 2px solid var(--color-blue); outline-offset: 2px; }
.review-slot button:focus-visible { outline: 3px solid var(--color-blue-focus); outline-offset: 3px; }
.review-slot img { @apply absolute inset-0 size-full object-cover; border-radius: inherit; }
.review-stamp { @apply absolute right-[3px] bottom-[3px] grid size-5 place-items-center rounded-full bg-danger text-white; }
.review-status { @apply text-center; }
.review-actions { @apply flex flex-wrap justify-center gap-2; }
.review-actions button { @apply gap-1.5 px-3 py-2; }
.review-actions kbd { @apply text-muted; }
@media (max-width: 600px) {
  .image-review { width: 100%; height: 100dvh; max-width: none; margin: 0; border-radius: 0; }
  .review-layout { padding: max(10px, env(safe-area-inset-top)) 12px max(12px, env(safe-area-inset-bottom)); gap: 10px; }
  .review-slide { padding-inline: 8px; }
  .review-arrow { background: color-mix(in srgb, var(--color-canvas) 88%, transparent); }
  .review-actions kbd { display: none; }
}
@media (max-width: 420px) {
  .review-slot:first-child, .review-slot:last-child { display: none; }
}
</style>
