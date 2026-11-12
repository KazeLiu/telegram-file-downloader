<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from '#imports'
import { queryText, queryPage } from './routeState'
import { api, bytes, imageThumbnail as thumbnail, type LibraryPicture as Picture } from './api'
import ImageReviewDialog from './ImageReviewDialog.vue'
import VirtualPhotoWall from './VirtualPhotoWall.vue'
import Icon from './Icon.vue'
import { formatNames, photoDay } from './xiaomiMedia'
import { useBeforeUnload } from './useBeforeUnload'

interface Recycled { id: string; original: string; size: number; created: number; reason: string; state: string; is_image: boolean }
type View = 'all' | 'candidates' | 'compressed' | 'recycle'
type Comparison = { running: boolean; phase: string; done: number; total: number; baselines: number; errors: number; error: string; current: string; last_check: number | null }
const route = useRoute()
const router = useRouter()
const imageModel = reactive({ view: 'all' as View, organizing: false, items: [] as Picture[], trash: [] as Recycled[], page: 1,
  total: 0, pageSize: 50, nextCursor: null as number | null, recycleRoot: 'downloads', roots: [] as { id: string; path: string }[],
  cleanup: { running: false, checked: 0, removed: 0, failed: 0 },
  counts: { total: 0, candidates: 0, compressed: 0, comparison_errors: 0, errors: 0, ready: 0 }, scan: { running: false, done: 0, total: 0, error: '', last_scan: null as number | null },
  comparison: null as Comparison | null,
  search: '', appliedSearch: '', loading: false, loadingMore: false, busy: false, error: '', selected: new Map<number, Picture>(), selectedDays: new Set<string>(),
  confirmation: [] as Picture[], broken: {} as Record<number, boolean> })
const props = defineProps<{ lastLocalRecycle: string[] }>()
const emit = defineEmits<{ message: [value: string]; recycled: [names: string[]] }>()
const confirmDialog = ref<HTMLDialogElement>()
const restoreDialog = ref<HTMLDialogElement>()
const restoreModel = reactive({ selected: new Map<string, Recycled>(), targets: [] as Recycled[], root: '', selectionRoot: 'downloads', done: 0, total: 0, note: '', broken: new Set<string>() })
const trashPhotos = computed(() => imageModel.trash.map(item => ({ ...item, sort_time: item.created * 1000 })))
const allTrashSelected = computed(() => imageModel.trash.some(item => item.state !== 'exporting') && imageModel.trash.every(item => item.state === 'exporting' || restoreModel.selected.has(item.id)))
const namesDialog = ref<HTMLDialogElement>()
const namesField = ref<HTMLTextAreaElement>()
const canCopy = typeof navigator !== 'undefined' && !!navigator.clipboard
const reviewDialog = ref<InstanceType<typeof ImageReviewDialog>>()
const moreButton = ref<HTMLButtonElement>()
const selectedCount = computed(() => imageModel.selected.size)
useBeforeUnload(() => imageModel.organizing && selectedCount.value > 0 || restoreModel.selected.size > 0)
const blocked = computed(() => imageModel.loading || imageModel.busy)
const toolbarBlocked = computed(() => blocked.value || imageModel.loadingMore)
const canLoadMore = computed(() => imageModel.view !== 'recycle' && imageModel.nextCursor !== null)
const listedScan = ref<number | null>(null)
const listedComparison = ref<number | null>(null)
const indexUpdated = computed(() => !imageModel.scan.running && !imageModel.scan.error && imageModel.scan.last_scan !== listedScan.value
  || !!imageModel.comparison?.last_check && !imageModel.comparison.running && imageModel.comparison.last_check !== listedComparison.value)
const allSelected = computed(() => imageModel.items.length > 0 && imageModel.items.every(isSelected))
let timer: ReturnType<typeof setInterval>
let observer: IntersectionObserver | undefined
let loadRevision = 0
let polling = false
let press: { pointerId: number; x: number; y: number; timer: ReturnType<typeof setTimeout> } | undefined
let held = false
let loadedScope = ''
let activeReview: number | null = null
let readController = new AbortController()
let disposed = false

function cancelReads() {
  readController.abort(); readController = new AbortController(); ++loadRevision
  imageModel.loading = imageModel.loadingMore = false
  observer?.disconnect(); stopPress()
}

function imageRoute(value = imageModel.view, page = 1, search = imageModel.appliedSearch, root = imageModel.recycleRoot) {
  return router.push({ path: value === 'all' ? '/images' : `/images/${value}`, query: value === 'recycle'
    ? { root: root !== 'downloads' ? root : undefined, page: page > 1 ? String(page) : undefined, search: search || undefined }
    : { search: search || undefined } })
}
async function readRoute() {
  if (disposed || !route.path.startsWith('/images')) return
  const value = route.path.split('/')[2]
  const view: View = value === 'candidates' || value === 'compressed' || value === 'recycle' ? value : 'all'
  const search = queryText(route.query.search)
  const root = queryText(route.query.root) || 'downloads'
  const page = queryPage(route.query.page)
  const scope = JSON.stringify([view, search, root, page])
  let signal = readController.signal
  if (scope !== loadedScope) {
    if (view !== imageModel.view || root !== restoreModel.selectionRoot || search !== imageModel.appliedSearch) { restoreModel.selected.clear(); restoreModel.broken.clear(); restoreModel.note = ''; restoreModel.selectionRoot = root }
    loadedScope = scope; cancelReads()
    signal = readController.signal
    Object.assign(imageModel, { view, page, search, appliedSearch: search, recycleRoot: root, items: [], trash: [], total: 0, nextCursor: null })
    clearSelection(); reviewDialog.value?.close(); activeReview = null
    if (view === 'recycle') imageModel.organizing = false
    await load()
  }
  if (signal.aborted || disposed) return
  const photo = Number(queryText(route.query.photo))
  if (view === 'recycle' || !Number.isSafeInteger(photo) || photo < 1) { reviewDialog.value?.close(); return }
  if (photo === activeReview) return
  try {
    const item = imageModel.items.find(item => item.id === photo) || await api<Picture>(`/images/${photo}`, undefined, 'GET', signal)
    if (signal.aborted || disposed || queryText(route.query.photo) !== String(photo)) return
    const listed = imageModel.items.includes(item)
    activeReview = photo
    reviewDialog.value?.open(listed ? imageModel.items : [item], item, listed ? imageModel.nextCursor : item.id, imageModel.total)
  } catch (error) { if (!disposed && (error as Error).name !== 'AbortError') imageModel.error = (error as Error).message }
}
watch(() => route.fullPath, () => void readRoute())
function reviewChanged(id: number) {
  activeReview = id
  void router.replace({ query: { ...route.query, photo: String(id) } })
}

function isSelected(item: Picture) { return imageModel.selected.get(item.id)?.version === item.version }
function clearSelection() { imageModel.selected.clear(); imageModel.selectedDays.clear() }
function imageQuery() {
  return new URLSearchParams({ candidate: String(imageModel.view === 'candidates'), compressed: String(imageModel.view === 'compressed'), search: imageModel.appliedSearch })
}
function listImages(after?: number | null) {
  const query = imageQuery()
  if (after != null) query.set('after', String(after))
  return api<{ items: Picture[]; total: number; next_cursor: number | null;
    scan: typeof imageModel.scan; counts: typeof imageModel.counts; comparison: Comparison | null }>(`/images?${query}`, undefined, 'GET', readController.signal)
}
async function load({ append = false } = {}) {
  if (disposed || imageModel.loading || imageModel.loadingMore || (append && (!canLoadMore.value || blocked.value))) return
  const revision = ++loadRevision
  const signal = readController.signal
  if (append) imageModel.loadingMore = true
  else imageModel.loading = true
  imageModel.error = ''
  try {
    if (imageModel.view === 'recycle') {
      const roots = await api<{ items: typeof imageModel.roots }>('/recycle/roots', undefined, 'GET', signal)
      if (signal.aborted || revision !== loadRevision) return
      imageModel.roots = roots.items
      const query = new URLSearchParams({ page: String(imageModel.page), root: imageModel.recycleRoot, search: imageModel.appliedSearch })
      const result = await api(`/recycle?${query}`, undefined, 'GET', signal)
      if (revision !== loadRevision) return
      imageModel.trash = result.items; imageModel.total = result.total; imageModel.pageSize = result.page_size
      imageModel.cleanup = result.cleanup
    } else {
      const result = await listImages(append ? imageModel.nextCursor : null)
      if (revision !== loadRevision) return
      imageModel.scan = result.scan; imageModel.counts = result.counts
      imageModel.comparison = result.comparison
      if (append) {
        const loaded = new Set(imageModel.items.map(item => item.id))
        const added = result.items.filter(item => !loaded.has(item.id))
        imageModel.items.push(...added)
        for (const item of added) if (imageModel.selectedDays.has(photoDay(item.sort_time))) imageModel.selected.set(item.id, item)
        imageModel.total = result.total; imageModel.nextCursor = result.next_cursor
      } else {
        imageModel.items = result.items; imageModel.total = result.total; imageModel.nextCursor = result.next_cursor; imageModel.broken = {}
        listedScan.value = result.scan.last_scan
        listedComparison.value = result.comparison?.last_check ?? null
      }
    }
  } catch (error) { if (revision === loadRevision) imageModel.error = (error as Error).message }
  finally {
    if (revision === loadRevision && append) imageModel.loadingMore = false
    else if (revision === loadRevision) imageModel.loading = false
  }
}
async function pollStatus() {
  if (polling || toolbarBlocked.value || imageModel.view === 'recycle') return
  polling = true
  const revision = loadRevision
  try {
    const result = await api<{ total: number; scan: typeof imageModel.scan; counts: typeof imageModel.counts; comparison: Comparison | null }>(`/images/status?${imageQuery()}`, undefined, 'GET', readController.signal)
    if (revision !== loadRevision) return
    imageModel.scan = result.scan; imageModel.counts = result.counts; imageModel.total = result.total
    imageModel.comparison = result.comparison
    if (!imageModel.items.length && result.total && activeReview === null && !confirmDialog.value?.open) await load()
  } catch (error) { if (revision === loadRevision) imageModel.error = (error as Error).message }
  finally { polling = false }
}
async function updateImages() {
  if (toolbarBlocked.value || activeReview !== null || confirmDialog.value?.open) return
  clearSelection()
  await load()
}
async function scan() {
  if (toolbarBlocked.value) return
  clearSelection(); imageModel.error = ''
  imageModel.scan.running = true
  try { imageModel.scan = await api('/images/scan', {}); await load() }
  catch (error) { imageModel.error = (error as Error).message; imageModel.scan.running = false }
}
async function view(value: View) {
  if (imageModel.busy || imageModel.view === value) return
  await imageRoute(value)
}
async function filter() {
  if (toolbarBlocked.value) return
  await imageRoute(imageModel.view, 1, imageModel.search)
}
async function page(delta: number) { await imageRoute(imageModel.view, imageModel.page + delta) }
function toggleOrganizing() {
  imageModel.organizing = !imageModel.organizing
  if (!imageModel.organizing) clearSelection()
}
function selectLoaded() {
  imageModel.selectedDays.clear()
  const selecting = !allSelected.value
  for (const item of imageModel.items) {
    if (selecting) imageModel.selected.set(item.id, item)
    else imageModel.selected.delete(item.id)
  }
}
function select(item: Picture, checked: boolean) {
  if (checked) imageModel.selected.set(item.id, item)
  else { imageModel.selected.delete(item.id); imageModel.selectedDays.delete(photoDay(item.sort_time)) }
}
function selectDay(day: string, items: Picture[]) {
  if (blocked.value) return
  imageModel.organizing = true
  const selecting = !items.every(isSelected)
  if (selecting) imageModel.selectedDays.add(day)
  else imageModel.selectedDays.delete(day)
  for (const item of items) {
    if (selecting) imageModel.selected.set(item.id, item)
    else imageModel.selected.delete(item.id)
  }
}
function stopPress(event?: PointerEvent) {
  if (!press || (event && press.pointerId !== event.pointerId)) return
  clearTimeout(press.timer)
  press = undefined
}
function startPress(event: PointerEvent, item: Picture) {
  if (!event.isPrimary || event.button !== 0) return
  stopPress()
  held = false
  const button = event.currentTarget as HTMLButtonElement
  const timer = setTimeout(() => {
    press = undefined
    if (!button.isConnected || button.disabled) return
    held = true
    review(item)
  }, 450)
  press = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, timer }
}
function movePress(event: PointerEvent) {
  if (press && Math.hypot(event.clientX - press.x, event.clientY - press.y) > 9) stopPress(event)
}
function activateImage(event: MouseEvent, item: Picture) {
  if (held && event.detail) { held = false; return }
  if (imageModel.organizing) select(item, !isSelected(item))
  else review(item)
}
function review(item: Picture) {
  void router.push({ query: { ...route.query, photo: String(item.id) } })
}
function finishReview(items: Picture[], submit: boolean, kept: Picture[]) {
  if (activeReview === null || !route.path.startsWith('/images')) return
  activeReview = null
  if (route.query.photo) void router.replace({ query: { ...route.query, photo: undefined } })
  for (const item of kept) select(item, false)
  if (!items.length) return
  imageModel.organizing = true
  for (const item of items) select(item, true)
  if (submit) void confirm(items)
}
async function confirm(items?: Picture[]) {
  if (!imageModel.organizing || blocked.value) return
  imageModel.confirmation = items || [...imageModel.selected.values()]
  if (!imageModel.confirmation.length) return
  await nextTick(); confirmDialog.value?.showModal()
}
async function recycle() {
  if (toolbarBlocked.value) return
  ++loadRevision
  imageModel.busy = true; imageModel.error = ''
  const moved = new Set<number>()
  const failures: string[] = []
  const targets = imageModel.confirmation
  try {
    for (let offset = 0; offset < targets.length; offset += 200) {
      const batch = targets.slice(offset, offset + 200)
      const result = await api<{ moved: number[]; failures: { id: number; error: string }[] }>(
        '/images/recycle', { items: batch.map(({ id, version }) => ({ id, version })) },
      )
      result.moved.forEach(id => moved.add(id))
      failures.push(...result.failures.map(failure => `${batch.find(item => item.id === failure.id)?.name || failure.id}：${failure.error}`))
    }
    confirmDialog.value?.close()
  } catch (error) { failures.push((error as Error).message) }
  finally {
    if (moved.size) {
      confirmDialog.value?.close()
      const removed = targets.filter(item => moved.has(item.id))
      emit('recycled', removed.map(item => item.name))
      moved.forEach(id => imageModel.selected.delete(id))
      imageModel.items = imageModel.items.filter(item => !moved.has(item.id))
      imageModel.total = Math.max(0, imageModel.total - moved.size)
      imageModel.counts.total = Math.max(0, imageModel.counts.total - moved.size)
      imageModel.counts.candidates = Math.max(0, imageModel.counts.candidates - removed.filter(item => item.monochrome).length)
      imageModel.counts.compressed = Math.max(0, imageModel.counts.compressed - removed.filter(item => item.saved_match).length)
      imageModel.counts.errors = Math.max(0, imageModel.counts.errors - removed.filter(item => item.error).length)
      emit('message', `已将 ${moved.size} 张图片移入回收站`)
    }
    imageModel.error = failures.join('；'); imageModel.busy = false
  }
}
async function copyRecycledNames() {
  if (navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(formatNames(props.lastLocalRecycle))
      emit('message', '已复制最近回收的文件名')
      return
    } catch { /* Clipboard access can be unavailable on a local HTTP address. */ }
  }
  namesField.value?.focus()
  namesField.value?.select()
}
function trashSelected(item: Recycled) { return restoreModel.selected.has(item.id) }
function toggleTrash(item: Recycled) {
  if (item.state === 'exporting') return
  if (trashSelected(item)) restoreModel.selected.delete(item.id)
  else restoreModel.selected.set(item.id, item)
}
function selectTrashDay(_day: string, items: Recycled[]) {
  const selecting = !items.filter(item => item.state !== 'exporting').every(trashSelected)
  for (const item of items) {
    if (item.state === 'exporting') continue
    if (selecting) restoreModel.selected.set(item.id, item)
    else restoreModel.selected.delete(item.id)
  }
}
function selectTrashPage() {
  const selecting = !allTrashSelected.value
  for (const item of imageModel.trash) {
    if (item.state === 'exporting') continue
    if (selecting) restoreModel.selected.set(item.id, item)
    else restoreModel.selected.delete(item.id)
  }
}
async function selectAllTrash() {
  imageModel.busy = true; imageModel.error = ''
  const root = imageModel.recycleRoot
  const search = imageModel.appliedSearch
  const signal = readController.signal
  try {
    for (let page = 1; ; page++) {
      const result = await api<{ items: Recycled[]; total: number; page_size: number }>(`/recycle?${new URLSearchParams({ root, search, page: String(page) })}`, undefined, 'GET', signal)
      if (signal.aborted || disposed) return
      for (const item of result.items) if (item.state !== 'exporting') restoreModel.selected.set(item.id, item)
      restoreModel.note = `已选择 ${restoreModel.selected.size} 项`
      if (page * result.page_size >= result.total || !result.items.length) break
    }
  } catch (error) { if (!signal.aborted) imageModel.error = (error as Error).message }
  finally { imageModel.busy = false }
}
function confirmRestore(item?: Recycled) {
  restoreModel.targets = item ? [item] : [...restoreModel.selected.values()]
  restoreModel.root = imageModel.recycleRoot
  restoreModel.done = 0; restoreModel.total = restoreModel.targets.length
  restoreDialog.value?.showModal()
}
async function restore() {
  imageModel.busy = true; imageModel.error = ''
  const scope = loadedScope
  const targets = restoreModel.targets
  const failures: string[] = []
  let restored = 0
  try {
    for (let offset = 0; offset < targets.length; offset += 200) {
      const batch = targets.slice(offset, offset + 200)
      const result = await api<{ restored: string[]; failures: { id: string; error: string }[] }>(`/recycle/restore?root=${encodeURIComponent(restoreModel.root)}`, { ids: batch.map(item => item.id) })
      restored += result.restored.length
      if (restoreModel.root === imageModel.recycleRoot) for (const id of result.restored) restoreModel.selected.delete(id)
      failures.push(...result.failures.map(failure => `${batch.find(item => item.id === failure.id)!.original}：${failure.error}`))
      restoreModel.done += batch.length
    }
  } catch (error) { failures.push((error as Error).message) }
  finally {
    restoreDialog.value?.close()
    restoreModel.note = `已还原 ${restored} 项${restored < targets.length ? `，${targets.length - restored} 项未完成` : ''}`
    if (restored) emit('message', `已还原 ${restored} 项到原路径`)
    imageModel.busy = false
    if (disposed || scope !== loadedScope) return
    await load()
    const last = Math.max(1, Math.ceil(imageModel.total / imageModel.pageSize))
    if (imageModel.view === 'recycle' && imageModel.page > last) await imageRoute('recycle', last)
    if (failures.length) imageModel.error = [imageModel.error, ...failures].filter(Boolean).join('；')
  }
}
function loadMore() { void load({ append: true }) }
// Re-observing after every completed page fires again even when the user has not scrolled.
watch(moreButton, button => {
  observer?.disconnect()
  if (button) observer?.observe(button)
}, { flush: 'post' })
onMounted(() => {
  if ('IntersectionObserver' in window) {
    observer = new IntersectionObserver(entries => {
      if (!disposed && !imageModel.error && entries.some(entry => entry.isIntersecting && entry.target === moreButton.value)) loadMore()
    }, { rootMargin: '0px 0px 80px' })
  }
  timer = setInterval(() => {
    if (!document.hidden) void pollStatus()
  }, 2000)
  void readRoute()
})
onBeforeUnmount(() => { disposed = true; clearInterval(timer); cancelReads() })
</script>

<template>
  <section class="image-library" :class="{ 'has-floating-actions': imageModel.view !== 'recycle' }">
    <div class="image-library-toolbar">
      <div class="image-tabs" role="tablist" aria-label="图片视图">
        <button role="tab" :aria-selected="imageModel.view === 'all'" :disabled="imageModel.busy" @click="view('all')">全部图片 <span>{{ imageModel.counts.total || 0 }}</span></button>
        <button role="tab" :aria-selected="imageModel.view === 'candidates'" :disabled="imageModel.busy" @click="view('candidates')">黑白候选 <span>{{ imageModel.counts.candidates || 0 }}</span></button>
        <button role="tab" :aria-selected="imageModel.view === 'compressed'" :disabled="imageModel.busy" @click="view('compressed')">重复图 <span>{{ imageModel.counts.compressed || 0 }}</span></button>
        <button role="tab" :aria-selected="imageModel.view === 'recycle'" :disabled="imageModel.busy" @click="view('recycle')">回收站</button>
      </div>
      <div class="image-toolbar-actions">
        <template v-if="imageModel.view !== 'recycle'">
          <button class="secondary" :disabled="toolbarBlocked || imageModel.scan.running" @click="scan"><Icon :name="imageModel.scan.running ? 'loader' : 'refresh'" :class="{ 'loading-icon': imageModel.scan.running }" :size="16" />{{ imageModel.scan.running ? '正在扫描' : '刷新图片' }}</button>
          <button class="floating-manage" :class="imageModel.organizing ? 'primary' : 'secondary'" :aria-pressed="imageModel.organizing" :disabled="blocked" @click="toggleOrganizing">{{ imageModel.organizing ? '完成' : '整理' }}</button>
        </template>
        <button v-else class="secondary" :disabled="blocked" @click="load()"><Icon name="refresh" :size="16" />刷新</button>
        <button v-if="lastLocalRecycle.length" class="text-button" @click="namesDialog?.showModal()">最近回收清单</button>
      </div>
    </div>
    <p v-if="imageModel.error" class="notice error" role="alert">{{ imageModel.error }}</p>
    <p v-if="imageModel.scan.error && imageModel.view !== 'recycle'" class="notice error" role="alert">扫描失败：{{ imageModel.scan.error }}</p>
    <p v-if="imageModel.comparison?.error && imageModel.view !== 'recycle'" class="notice error" role="alert">已存图片检查：{{ imageModel.comparison.error }}</p>
    <div v-if="imageModel.comparison?.running && imageModel.view !== 'recycle'" class="image-scan" role="status"><span><Icon name="compare" :size="16" />{{ imageModel.comparison.phase === 'indexing' ? `正在缓存绑定目录图片 · ${imageModel.comparison.baselines} 张` : `正在与已存图片比对 · ${imageModel.comparison.done} / ${imageModel.comparison.total} 张` }}</span><progress v-if="imageModel.comparison.phase === 'comparing'" :value="imageModel.comparison.done" :max="imageModel.comparison.total" aria-label="已存图片比对进度" /></div>
    <p v-if="imageModel.counts.comparison_errors && imageModel.view !== 'recycle'" class="notice">{{ imageModel.counts.comparison_errors }} 张图片的已存检查未完成，可点“刷新图片”重试；原文件保留。</p>
    <p v-if="imageModel.counts.errors && imageModel.view !== 'recycle'" class="notice">{{ imageModel.counts.errors }} 张图片读取失败，可在“全部图片”中查看；原文件保留。</p>
    <div v-if="imageModel.scan.running && imageModel.view !== 'recycle'" class="image-scan" role="status"><span><Icon name="loader" class="loading-icon" :size="16" />{{ imageModel.scan.total ? `后台已检查 ${imageModel.scan.done} / ${imageModel.scan.total} 张 · 已就绪 ${imageModel.counts.ready || 0} 张，可继续浏览` : '正在后台读取根目录图片…' }}</span><progress v-if="imageModel.scan.total" :value="imageModel.scan.done" :max="imageModel.scan.total" aria-label="图片分析进度" /></div>
    <p v-if="indexUpdated && imageModel.view !== 'recycle'" class="notice" role="status">后台图片检查已完成。<button class="text-button" :disabled="toolbarBlocked || selectedCount > 0" @click="updateImages">更新图片列表</button><span v-if="selectedCount">请先处理或清空已选图片。</span></p>
    <template v-if="imageModel.view !== 'recycle'">
      <div class="image-actions">
        <form class="search-box" @submit.prevent="filter"><Icon name="search" :size="17" /><input v-model="imageModel.search" :disabled="toolbarBlocked" maxlength="255" placeholder="搜索根目录图片" aria-label="搜索根目录图片" /><button class="text-button" :disabled="toolbarBlocked">搜索</button></form>
        <span class="muted" title="拍摄时间优先，其次图片日期，缺失时使用原修改时间">{{ imageModel.total }} 张 · 按照片时间从新到旧</span>
        <button v-if="imageModel.organizing" class="text-button" :disabled="blocked || !imageModel.items.length" @click="selectLoaded">{{ allSelected ? '取消已加载选择' : '全选已加载' }}</button>
      </div>
      <VirtualPhotoWall :class="imageModel.view === 'compressed' ? 'compressed-wall' : 'image-grid'" :items="imageModel.items" :disabled="blocked" :is-selected="isSelected" :aria-busy="imageModel.loading || imageModel.loadingMore" @toggle-day="selectDay">
        <template #default="{ item }">
        <article class="image-card">
          <button type="button" class="image-preview" :title="(item.saved_match ? '重复图 · ' : '') + item.name" :disabled="blocked"
            :aria-label="(imageModel.organizing ? '选择 ' : '快速审阅 ') + (item.saved_match ? '重复图 ' : '') + item.name" :aria-pressed="imageModel.organizing ? isSelected(item) : undefined"
            aria-keyshortcuts="Shift+Enter" @click="activateImage($event, item)" @keydown.shift.enter.prevent="!$event.repeat && review(item)"
            @pointerdown="startPress($event, item)" @pointermove="movePress" @pointerup="stopPress" @pointerleave="stopPress" @pointercancel="stopPress" @contextmenu.prevent>
            <span v-if="imageModel.view === 'compressed' && item.saved_match" class="compressed-pair">
              <span><strong>下载图片</strong><img :src="thumbnail(item)" alt="下载图片" draggable="false" loading="lazy" /><small>{{ item.width }} × {{ item.height }} · {{ bytes(item.size) }}</small></span>
              <span><strong>已存图片</strong><img :src="`/api/images/${item.id}/saved/thumbnail?version=${encodeURIComponent(item.version)}`" alt="绑定目录中的已存图片" draggable="false" loading="lazy" /><small>{{ item.saved_match.width }} × {{ item.saved_match.height }} · {{ bytes(item.saved_match.size) }}</small></span>
            </span>
            <span v-else class="image-thumb">
              <img v-if="item.width && !item.error && !imageModel.broken[item.id]" :src="thumbnail(item)" alt="" draggable="false" loading="lazy" decoding="async" @error="imageModel.broken[item.id] = true" />
              <Icon v-else name="photo" class="text-muted" :size="16" />
              <span v-if="item.saved_match" class="compressed-mark" title="重复图"><Icon name="compare" :size="13" /></span>
            </span>
          </button>
        </article>
        </template>
      </VirtualPhotoWall>
      <div v-if="canLoadMore" class="image-more"><button ref="moreButton" class="text-button" :disabled="toolbarBlocked" @click="loadMore">{{ imageModel.loadingMore ? '正在加载…' : '加载更多' }}</button></div>
      <div v-if="!imageModel.items.length && !canLoadMore && !imageModel.loading && !imageModel.error" class="empty-list tall">
        <Icon name="photo" :size="38" />
        <h2>{{ imageModel.scan.running ? '正在整理图片索引' : imageModel.appliedSearch ? '没有匹配的图片' : imageModel.view === 'compressed' ? imageModel.comparison?.running ? '正在与已存图片比对' : imageModel.comparison?.phase === 'disabled' ? '工作流自动检查已关闭' : imageModel.comparison?.phase === 'unbound' ? '尚未选择有效的工作流检查目录' : imageModel.comparison?.phase === 'waiting' ? '等待目录索引和当前文件操作完成' : '暂无重复图' : imageModel.view === 'candidates' ? '暂无黑白候选' : '根目录还没有图片' }}</h2>
        <button v-if="imageModel.view === 'compressed' && ['disabled', 'unbound'].includes(imageModel.comparison?.phase ?? '')" class="secondary" @click="router.push('/dedup')">设置工作流自动检查</button>
        <p v-if="!imageModel.scan.running && !imageModel.appliedSearch && imageModel.view === 'all'">这里只展示直接放在下载根目录的图片，不进入子文件夹。</p>
      </div>
      <button v-if="imageModel.organizing && selectedCount" class="danger recycle-selection" :disabled="blocked" @click="confirm()"><Icon name="trash" :size="16" />移入回收站 · {{ selectedCount }} 张</button>
    </template>
    <template v-else>
      <p class="muted recycle-help">文件在项目回收站保留 15 天，期间可还原到原路径且不覆盖同名文件。到期后由容器自动永久删除，不进入 Windows 回收站，也无法再从这里恢复。</p>
      <p v-if="imageModel.cleanup.running" class="muted mt-2" role="status">正在检查到期文件…</p>
      <p v-else-if="imageModel.cleanup.checked" class="muted mt-2">最近检查：{{ new Date(imageModel.cleanup.checked * 1000).toLocaleString('zh-CN') }} · 本轮已永久清理 {{ imageModel.cleanup.removed }} 项</p>
      <p v-if="imageModel.cleanup.failed" class="notice error" role="alert">自动清理有 {{ imageModel.cleanup.failed }} 项异常，请查看运行日志。</p>
      <div class="recycle-toolbar">
        <label v-if="imageModel.roots.length > 1">回收目录<select v-model="imageModel.recycleRoot" :disabled="blocked" @change="imageRoute('recycle')"><option v-for="root in imageModel.roots" :key="root.id" :value="root.id">{{ root.path }}</option></select></label>
        <form class="search-box" @submit.prevent="filter"><Icon name="search" :size="17" /><input v-model="imageModel.search" type="search" :disabled="blocked" maxlength="255" placeholder="搜索回收文件名" aria-label="搜索回收文件名" /><button class="text-button" :disabled="blocked">搜索</button></form>
        <span role="status">共 {{ imageModel.total }} 项 · 已选 {{ restoreModel.selected.size }} 项</span>
      </div>
      <div class="recycle-actions">
        <button class="secondary" :disabled="blocked || !imageModel.trash.length" @click="selectTrashPage">{{ allTrashSelected ? '取消本页选择' : '全选本页' }}</button>
        <button class="text-button" :disabled="blocked || !imageModel.total" @click="selectAllTrash">{{ imageModel.appliedSearch ? '全选筛选结果' : '全选本目录' }}</button>
        <button v-if="restoreModel.selected.size" class="text-button" :disabled="blocked" @click="restoreModel.selected.clear()">清空选择</button>
        <button class="primary" :disabled="blocked || !restoreModel.selected.size" @click="confirmRestore()"><Icon name="restore" :size="16" />还原所选 {{ restoreModel.selected.size }} 项</button>
      </div>
      <p v-if="restoreModel.note" class="muted my-3" role="status">{{ restoreModel.note }}</p>
      <VirtualPhotoWall v-if="trashPhotos.length" class="recycle-wall" :items="trashPhotos" caption :disabled="blocked" :is-selected="trashSelected" @toggle-day="selectTrashDay">
        <template #default="{ item }"><article class="relative min-w-0">
          <button class="image-preview" :disabled="blocked || item.state === 'exporting'" :aria-label="'选择还原 ' + item.original" :aria-pressed="trashSelected(item)" @click="toggleTrash(item)"><span class="image-thumb">
            <img v-if="item.is_image && !restoreModel.broken.has(item.id)" :src="`/api/recycle/${item.id}/thumbnail?root=${encodeURIComponent(imageModel.recycleRoot)}`" alt="" loading="lazy" decoding="async" @error="restoreModel.broken.add(item.id)" />
            <Icon v-else :name="item.is_image ? 'photo' : 'file'" class="text-muted" :size="28" />
          </span><span v-if="item.state !== 'exporting'" class="recycle-check" :class="{ checked: trashSelected(item) }"><Icon v-if="trashSelected(item)" name="check" :size="15" /></span></button>
          <button v-if="item.state !== 'exporting'" class="recycle-one" :disabled="blocked" :aria-label="'还原 ' + item.original" @click="confirmRestore(item)"><Icon name="restore" :size="17" /></button>
          <p class="h-[20px] truncate text-xs leading-[20px] text-muted" :title="`${item.original} · ${bytes(item.size)} · ${new Date(item.created * 1000).toLocaleString('zh-CN')} · ${item.state === 'exporting' ? '文件已移出，需手动核对' : item.reason === 'xiaomi_upload' ? '上传后回收' : item.reason === 'xiaomi_cloud' ? '云端联动回收' : '本地回收'}`">{{ item.original }}</p>
        </article></template>
      </VirtualPhotoWall>
      <div v-else-if="!imageModel.loading && !imageModel.error" class="empty-list tall"><Icon name="trash" :size="38" /><h2>{{ imageModel.appliedSearch ? '没有匹配的回收文件' : '回收站是空的' }}</h2></div>
    </template>
    <div v-if="imageModel.view === 'recycle'" class="pagination"><span>第 {{ imageModel.page }} / {{ Math.max(1, Math.ceil(imageModel.total / imageModel.pageSize)) }} 页</span><button class="secondary" :disabled="blocked || imageModel.page === 1" @click="page(-1)">上一页</button><button class="secondary" :disabled="blocked || imageModel.page * imageModel.pageSize >= imageModel.total" @click="page(1)">下一页</button></div>
    <ImageReviewDialog ref="reviewDialog" :load-page="listImages" :is-selected="isSelected" @change="reviewChanged" @finish="finishReview" />
    <dialog ref="restoreDialog" class="task-dialog" @cancel="imageModel.busy && $event.preventDefault()">
      <h2>还原 {{ restoreModel.targets.length }} 项文件？</h2><p class="my-3">还原到各自的原路径，不覆盖已有同名文件。未成功的项目继续保留在回收站。</p>
      <div class="recycle-confirm-list"><p v-for="item in restoreModel.targets" :key="item.id">{{ item.original }}</p></div>
      <p v-if="imageModel.busy" role="status">正在还原 {{ restoreModel.done }} / {{ restoreModel.total }} 项…</p>
      <div class="dialog-actions"><button class="secondary" :disabled="imageModel.busy" @click="restoreDialog?.close()">取消</button><button class="primary" :disabled="imageModel.busy" @click="restore">{{ imageModel.busy ? '正在还原…' : '确认还原' }}</button></div>
    </dialog>
    <dialog ref="namesDialog" class="task-dialog" aria-labelledby="local-recycle-names">
      <div class="section-heading"><h2 id="local-recycle-names">最近回收 · {{ lastLocalRecycle.length }} 张</h2><button class="icon-button" aria-label="关闭清单" @click="namesDialog?.close()"><Icon name="close" /></button></div>
      <textarea ref="namesField" class="my-4" readonly rows="6" aria-label="实际回收的文件名" :value="formatNames(lastLocalRecycle)" />
      <div class="dialog-actions"><button class="secondary" @click="copyRecycledNames">{{ canCopy ? '复制文件名' : '选中文件名' }}</button></div>
    </dialog>
    <dialog ref="confirmDialog" class="task-dialog recycle-dialog" @cancel="imageModel.busy && $event.preventDefault()">
      <div class="section-heading"><h2>移入回收站？</h2><button class="icon-button" :disabled="imageModel.busy" aria-label="取消回收" @click="confirmDialog?.close()"><Icon name="close" /></button></div>
      <p>将选中的 {{ imageModel.confirmation.length }} 张图片移入项目回收站，保留 15 天后自动永久删除。</p>
      <div class="recycle-confirm-list"><p v-for="item in imageModel.confirmation" :key="item.id">{{ item.name }}</p></div>
      <p v-if="imageModel.error" class="notice error" role="alert">{{ imageModel.error }}</p>
      <div class="dialog-actions"><button class="secondary" :disabled="imageModel.busy" @click="confirmDialog?.close()">取消</button><button class="danger" :disabled="toolbarBlocked" @click="recycle"><Icon :name="imageModel.busy ? 'loader' : 'trash'" :class="{ 'loading-icon': imageModel.busy }" :size="16" />{{ imageModel.busy ? '正在移入…' : '确认移入回收站' }}</button></div>
    </dialog>
  </section>
</template>

<style scoped>
@reference '../app/assets/main.css';
.image-library { overflow-anchor: none; }
.image-tabs { @apply max-w-full overflow-x-auto whitespace-nowrap; }
.image-tabs button { @apply shrink-0; }
.compressed-wall { @apply grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3; }
.compressed-pair { @apply pointer-events-none grid size-full grid-cols-2 gap-2 p-3; }
.compressed-pair > span { @apply flex min-h-0 min-w-0 flex-col gap-2; }
.compressed-pair strong { @apply text-sm font-medium; }
.compressed-pair img { @apply h-0 min-h-0 w-full flex-1 object-contain; }
.compressed-pair small { @apply truncate text-xs text-muted; }
.image-preview[aria-pressed=true] .compressed-pair { @apply ring-2 ring-blue ring-inset; }
.compressed-mark { @apply absolute right-0 bottom-0 grid size-5 place-items-center rounded-tl-md bg-blue text-white; }
.recycle-wall { @apply grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-8 xl:grid-cols-10; }
.recycle-toolbar { @apply my-3 flex flex-wrap items-end gap-3; }
.recycle-toolbar .search-box { @apply min-w-0; flex: 1 1 260px; max-width: 360px; }
.recycle-toolbar > span { @apply whitespace-nowrap text-sm text-muted; }
.recycle-actions { @apply my-3 flex items-center gap-3 overflow-x-auto whitespace-nowrap; }
.recycle-actions > button { @apply shrink-0; }
.recycle-check { @apply pointer-events-none absolute top-2 left-2 grid size-6 place-items-center rounded-full border-2 border-solid border-white bg-ink/30 text-white; }
.recycle-check.checked { @apply border-blue bg-blue; }
.recycle-one { @apply absolute top-1 right-1 grid size-11 min-h-11 place-items-center rounded-full bg-canvas p-0 text-blue; }
</style>
