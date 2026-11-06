<script setup lang="ts">
import { AnimatePresence, MotionConfig, motion } from 'motion-v'
import { computed, reactive, ref, shallowRef } from 'vue'
import { bytes, imageThumbnail, type LibraryPicture as Picture } from './api'
import Icon from './Icon.vue'

type Decision = 'keep' | 'recycle'
type Direction = 'previous' | 'next' | Decision
const props = defineProps<{
  loadPage: (after: number) => Promise<{ items: Picture[]; next_cursor: number | null; total: number }>
}>()
const emit = defineEmits<{ finish: [items: Picture[], submit: boolean] }>()
const dialog = ref<HTMLDialogElement>()
const queue = shallowRef<Picture[]>([])
const index = ref(0)
const total = ref(0)
const cursor = ref<number | null>(null)
const direction = ref<Direction>('next')
const loading = ref(false)
const error = ref('')
const decisions = reactive(new Map<number, Decision>())
const history = reactive<{ index: number; previous?: Decision }[]>([])
const broken = reactive(new Set<number>())
const current = computed<Picture | undefined>(() => queue.value[index.value])
const pending = computed(() => queue.value.filter((_, i) => decisions.get(i) === 'recycle'))
const canAdvance = computed(() => index.value + 1 < queue.value.length || cursor.value !== null)
const filmstrip = computed(() => {
  const center = Math.min(index.value, queue.value.length - 1)
  return Array.from({ length: 7 }, (_, slot) => center + slot - 3)
})
const slide = {
  enter: (way: Direction) => ({ opacity: 0, x: way === 'previous' ? -22 : way === 'next' ? 22 : 0 }),
  visible: { opacity: 1, x: 0 },
  exit: (way: Direction) => {
    if (way === 'recycle') return { opacity: 0, y: '40%', scale: .14, rotate: -8 }
    if (way === 'keep') return { opacity: 0, y: -44, scale: .96 }
    return { opacity: 0, x: way === 'previous' ? 22 : -22 }
  },
}

function open(items: Picture[], item: Picture, nextCursor: number | null, count: number) {
  queue.value = items.slice()
  index.value = items.indexOf(item)
  cursor.value = nextCursor
  total.value = count
  direction.value = 'next'
  loading.value = false
  error.value = ''
  decisions.clear(); history.length = 0; broken.clear()
  dialog.value!.returnValue = ''
  dialog.value!.showModal()
}
defineExpose({ open })

function finish() {
  emit('finish', pending.value, dialog.value?.returnValue === 'recycle')
  queue.value = []
}
function go(target: number, way: Direction) {
  if (target === index.value) return
  direction.value = way
  index.value = target
}
async function advance(way: 'next' | Decision) {
  if (loading.value || !current.value) return
  if (index.value + 1 < queue.value.length) { go(index.value + 1, way); return }
  if (cursor.value !== null) {
    const batch = queue.value
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
function panEnd(event: PointerEvent, { offset: { x, y } }: { offset: { x: number; y: number } }) {
  if (event.type !== 'pointerup' || !dialog.value?.open) return
  const horizontal = Math.abs(x), vertical = Math.abs(y)
  if (horizontal >= 56 && horizontal > vertical * 1.25) {
    if (x > 0) previous(); else void advance('next')
  } else if (vertical >= 56 && vertical > horizontal * 1.25) {
    decide(y < 0 ? 'keep' : 'recycle')
  }
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
function decisionLabel(i: number) {
  return decisions.get(i) === 'keep' ? '已保留' : decisions.get(i) === 'recycle' ? '待回收' : ''
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

      <MotionConfig reduced-motion="user" :transition="{ duration: .2 }">
        <div class="review-stage">
          <motion.div class="review-swipe" @panEnd="panEnd">
            <AnimatePresence :initial="false" :custom="direction">
              <motion.div v-if="current" :key="current.id" class="review-slide" :custom="direction" :variants="slide" initial="enter" animate="visible" exit="exit">
                <img v-if="hasPreview(current)" :src="imageThumbnail(current)" :alt="current.name" :data-image-id="current.id" draggable="false" @error="markBroken" />
                <p v-else class="review-empty"><Icon name="photo" :size="34" />{{ current.error || (broken.has(current.id) ? '图片预览加载失败' : '图片预览尚未生成') }}</p>
              </motion.div>
              <motion.div v-else-if="queue.length" key="end" class="review-slide review-empty" :custom="direction" :variants="slide" initial="enter" animate="visible" exit="exit">
                <Icon name="check" :size="34" />已到队列末尾
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
          <span v-if="decisions.has(index)" :class="decisions.get(index)">{{ decisionLabel(index) }}</span>
          <span class="muted">{{ bytes(current.size) }}</span>
        </template>
        <span v-else class="muted">已标记 {{ decisions.size }} 张</span>
      </div>

      <div class="review-filmstrip" role="group" aria-label="审阅队列">
        <div v-for="(position, slot) in filmstrip" :key="slot" class="review-slot">
          <button v-if="queue[position]" :key="queue[position].id" :aria-current="position === index ? 'true' : undefined" :disabled="loading"
            :aria-label="[queue[position].name, decisionLabel(position)].filter(Boolean).join('，')"
            @click="go(position, position < index ? 'previous' : 'next')">
            <img v-if="hasPreview(queue[position])" :src="imageThumbnail(queue[position])" :data-image-id="queue[position].id" alt="" draggable="false" decoding="async" @error="markBroken" />
            <Icon v-else name="photo" :size="17" />
            <span v-if="decisions.has(position)" class="review-stamp" :class="decisions.get(position)"><Icon :name="decisions.get(position) === 'keep' ? 'check' : 'trash'" :size="13" /></span>
          </button>
        </div>
      </div>

      <p v-if="error" class="notice error review-status" role="alert">加载下一批图片失败：{{ error }}</p>
      <p v-else-if="loading" class="muted review-status" role="status">正在加载下一批图片…</p>
      <footer class="review-actions">
        <button class="secondary keep" :disabled="!current || loading" aria-keyshortcuts="ArrowUp" @click="decide('keep')"><Icon name="check" :size="17" />保留 <kbd>↑</kbd></button>
        <button class="secondary recycle" :disabled="!current || loading" aria-keyshortcuts="ArrowDown" @click="decide('recycle')"><Icon name="trash" :size="17" />标记回收 <kbd>↓</kbd></button>
        <button class="secondary" :disabled="!history.length || loading" aria-keyshortcuts="Control+Z Meta+Z" @click="undo">撤销</button>
        <button v-if="pending.length" class="danger" @click="dialog?.close('recycle')">移入回收站 · {{ pending.length }} 张</button>
      </footer>
    </div>
  </dialog>
</template>

<style scoped lang="scss">
.image-review {
  width: min(1020px, calc(100% - 32px)); height: min(830px, calc(100dvh - 32px)); max-height: none;
  padding: 0; background: var(--canvas); overscroll-behavior: contain;
}
.review-layout { min-height: 100%; height: 100%; display: flex; flex-direction: column; gap: 12px; padding: 16px 20px; }
.review-heading { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 8px; }
.review-heading button { justify-self: end; }
.review-count { font-variant-numeric: tabular-nums; }
.review-stage { flex: 1; min-height: 140px; position: relative; border-radius: 14px; background: var(--parchment); overflow: hidden; }
.review-swipe { position: absolute; inset: 0; touch-action: none; user-select: none; cursor: grab; }
.review-swipe:active { cursor: grabbing; }
.review-slide { position: absolute; inset: 0; display: flex; justify-content: center; align-items: center; padding: 10px 52px; pointer-events: none; }
.review-slide img { display: block; width: 100%; height: 100%; min-height: 0; object-fit: contain; }
.review-empty { display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 10px; color: var(--muted); text-align: center; }
.review-bin { position: absolute; bottom: 10%; left: 50%; translate: -50% 50%; border-radius: 50%; background: var(--danger); color: white; padding: 10px; pointer-events: none; }
.review-arrow { position: absolute; top: 50%; translate: 0 -50%; background: var(--canvas); box-shadow: 0 1px 5px #1d1d1f20; }
.review-previous { left: 6px; }
.review-previous svg { rotate: 180deg; }
.review-next { right: 6px; }
.review-caption { min-height: 22px; display: flex; align-items: center; gap: 12px; }
.review-caption strong { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.review-caption span { flex: none; }
.review-caption .muted { margin-left: auto; }
.review-caption .keep, .review-actions .keep { color: var(--success); }
.review-caption .recycle, .review-actions .recycle { color: var(--danger); }
.review-filmstrip { width: min(100%, 472px); margin-inline: auto; display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 6px; }
.review-slot button { position: relative; display: grid; place-items: center; width: 100%; aspect-ratio: 1; padding: 0; border-radius: 8px; background: var(--parchment); color: var(--muted); }
.review-slot button[aria-current] { outline: 2px solid var(--blue); outline-offset: 2px; }
.review-slot button:focus-visible { outline: 3px solid var(--blue-focus); outline-offset: 3px; }
.review-slot img { position: absolute; inset: 0; width: 100%; height: 100%; border-radius: inherit; object-fit: cover; }
.review-stamp { position: absolute; right: 3px; bottom: 3px; display: grid; place-items: center; width: 20px; height: 20px; border-radius: 50%; color: white; }
.review-stamp.keep { background: var(--success); }
.review-stamp.recycle { background: var(--danger); }
.review-status { text-align: center; }
.review-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
.review-actions button { padding: 8px 13px; gap: 5px; }
.review-actions kbd { color: var(--muted); }
@media (max-width: 600px) {
  .image-review { width: 100%; height: 100dvh; max-width: none; margin: 0; border-radius: 0; }
  .review-layout { padding: max(10px, env(safe-area-inset-top)) 12px max(12px, env(safe-area-inset-bottom)); gap: 10px; }
  .review-slide { padding-inline: 8px; }
  .review-arrow { background: color-mix(in srgb, var(--canvas) 88%, transparent); }
  .review-actions kbd { display: none; }
}
@media (max-width: 420px) {
  .review-slot:first-child, .review-slot:last-child { display: none; }
}
</style>
