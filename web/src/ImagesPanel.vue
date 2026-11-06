<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch, watchEffect } from 'vue'
import { useRoute, useRouter } from '#imports'
import { queryText, queryPage } from './routeState'
import { api, bytes, imageThumbnail as thumbnail, type LibraryPicture as Picture } from './api'
import ImageReviewDialog from './ImageReviewDialog.vue'
import Icon from './Icon.vue'
import { formatNames, photoDay, takenAt } from './xiaomiMedia'

interface Recycled { id: string; original: string; size: number; created: number; reason: string; state: string }
type View = 'all' | 'candidates' | 'recycle'
const route = useRoute()
const router = useRouter()
const timeSources = { taken: '拍摄时间', digitized: '数字化时间', image: '图片日期', created: '文件创建时间', modified: '修改时间' }
const imageModel = reactive({ view: 'all' as View, organizing: false, items: [] as Picture[], trash: [] as Recycled[], page: 1,
  total: 0, pageSize: 50, nextCursor: null as number | null, recycleRoot: 'downloads', roots: [] as { id: string; path: string }[],
  cleanup: { running: false, checked: 0, removed: 0, failed: 0 },
  counts: { total: 0, candidates: 0, errors: 0 }, scan: { running: false, done: 0, total: 0, error: '' },
  search: '', appliedSearch: '', loading: false, loadingMore: false, busy: false, error: '', selected: new Map<number, Picture>(),
  confirmation: [] as Picture[], picture: null as Picture | null, broken: {} as Record<number, boolean> })
const props = defineProps<{ lastLocalRecycle: string[] }>()
const emit = defineEmits<{ message: [value: string]; recycled: [names: string[]] }>()
const confirmDialog = ref<HTMLDialogElement>()
const namesDialog = ref<HTMLDialogElement>()
const namesField = ref<HTMLTextAreaElement>()
const canCopy = typeof navigator !== 'undefined' && !!navigator.clipboard
const pictureDialog = ref<HTMLDialogElement>()
const reviewDialog = ref<InstanceType<typeof ImageReviewDialog>>()
const moreButton = ref<HTMLButtonElement>()
const selectedCount = computed(() => imageModel.selected.size)
const blocked = computed(() => imageModel.loading || imageModel.busy)
const toolbarBlocked = computed(() => blocked.value || imageModel.loadingMore)
const canLoadMore = computed(() => imageModel.view !== 'recycle' && !imageModel.scan.running && imageModel.nextCursor !== null)
const allSelected = computed(() => imageModel.items.length > 0 && imageModel.items.every(isSelected))
let timer: ReturnType<typeof setInterval>
let observer: IntersectionObserver | undefined
let loadRevision = 0
let polling = false
let press: { pointerId: number; x: number; y: number; timer: ReturnType<typeof setTimeout> } | undefined
let held = false
let loadedScope = ''
let activeReview: number | null = null

function imageRoute(value = imageModel.view, page = 1, search = imageModel.appliedSearch, root = imageModel.recycleRoot) {
  return router.push({ path: value === 'all' ? '/images' : `/images/${value}`, query: value === 'recycle'
    ? { root: root !== 'downloads' ? root : undefined, page: page > 1 ? String(page) : undefined }
    : { search: search || undefined } })
}
async function readRoute() {
  if (!route.path.startsWith('/images')) return
  const value = route.path.split('/')[2]
  const view: View = value === 'candidates' || value === 'recycle' ? value : 'all'
  const search = queryText(route.query.search)
  const root = queryText(route.query.root) || 'downloads'
  const page = queryPage(route.query.page)
  const scope = JSON.stringify([view, search, root, page])
  if (scope !== loadedScope) {
    loadedScope = scope; ++loadRevision
    imageModel.loading = imageModel.loadingMore = false
    Object.assign(imageModel, { view, page, search, appliedSearch: search, recycleRoot: root, items: [], trash: [], total: 0, nextCursor: null })
    clearSelection(); pictureDialog.value?.close(); reviewDialog.value?.close(); activeReview = null
    if (view === 'recycle') imageModel.organizing = false
    await load()
  }
  const photo = Number(queryText(route.query.photo))
  if (view === 'recycle' || !Number.isSafeInteger(photo) || photo < 1) { reviewDialog.value?.close(); return }
  if (photo === activeReview) return
  try {
    const item = imageModel.items.find(item => item.id === photo) || await api<Picture>(`/images/${photo}`)
    if (queryText(route.query.photo) !== String(photo)) return
    const listed = imageModel.items.includes(item)
    activeReview = photo
    reviewDialog.value?.open(listed ? imageModel.items : [item], item, listed ? imageModel.nextCursor : item.id, imageModel.total)
  } catch (error) { imageModel.error = (error as Error).message }
}
watch(() => route.fullPath, () => void readRoute())
function reviewChanged(id: number) {
  activeReview = id
  void router.replace({ query: { ...route.query, photo: String(id) } })
}

function isSelected(item: Picture) { return imageModel.selected.get(item.id)?.version === item.version }
function clearSelection() { imageModel.selected.clear() }
function listImages(after?: number | null) {
  const query = new URLSearchParams({ candidate: String(imageModel.view === 'candidates'), search: imageModel.appliedSearch })
  if (after != null) query.set('after', String(after))
  return api<{ items: Picture[]; total: number; next_cursor: number | null;
    scan: typeof imageModel.scan; counts: typeof imageModel.counts }>(`/images?${query}`)
}
async function load({ poll = false, append = false } = {}) {
  if (imageModel.loading || imageModel.loadingMore || (poll && polling) || (append && (!canLoadMore.value || blocked.value))) return
  const revision = ++loadRevision
  if (poll) polling = true
  else if (append) imageModel.loadingMore = true
  else imageModel.loading = true
  if (!poll) imageModel.error = ''
  try {
    if (imageModel.view === 'recycle') {
      imageModel.roots = (await api<{ items: typeof imageModel.roots }>('/recycle/roots')).items
      const query = new URLSearchParams({ page: String(imageModel.page), root: imageModel.recycleRoot })
      const result = await api(`/recycle?${query}`)
      if (revision !== loadRevision) return
      imageModel.trash = result.items; imageModel.total = result.total; imageModel.pageSize = result.page_size
      imageModel.cleanup = result.cleanup
    } else {
      const result = await listImages(append ? imageModel.nextCursor : null)
      if (revision !== loadRevision) return
      imageModel.scan = result.scan; imageModel.counts = result.counts
      if (append) {
        const loaded = new Set(imageModel.items.map(item => item.id))
        imageModel.items.push(...result.items.filter(item => !loaded.has(item.id)))
        imageModel.total = result.total; imageModel.nextCursor = result.next_cursor
      } else if (!poll || (!imageModel.organizing && activeReview === null && !pictureDialog.value?.open && !confirmDialog.value?.open)) {
        imageModel.items = result.items; imageModel.total = result.total; imageModel.nextCursor = result.next_cursor; imageModel.broken = {}
      }
    }
  } catch (error) { if (revision === loadRevision) imageModel.error = (error as Error).message }
  finally {
    if (poll) polling = false
    else if (revision === loadRevision && append) imageModel.loadingMore = false
    else if (revision === loadRevision) imageModel.loading = false
  }
}
async function scan() {
  if (toolbarBlocked.value) return
  clearSelection(); imageModel.error = ''
  imageModel.scan.running = true
  try { imageModel.scan = await api('/images/scan', {}); await load() }
  catch (error) { imageModel.error = (error as Error).message; imageModel.scan.running = false }
}
async function view(value: View) {
  if (toolbarBlocked.value || imageModel.view === value) return
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
  const selecting = !allSelected.value
  for (const item of imageModel.items) {
    if (selecting) imageModel.selected.set(item.id, item)
    else imageModel.selected.delete(item.id)
  }
}
function select(item: Picture, checked: boolean) {
  if (checked) imageModel.selected.set(item.id, item)
  else imageModel.selected.delete(item.id)
}
async function preview(item: Picture) { imageModel.picture = item; await nextTick(); pictureDialog.value?.showModal() }
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
    void preview(item)
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
function finishReview(items: Picture[], submit: boolean) {
  activeReview = null
  if (route.path.startsWith('/images') && route.query.photo) void router.replace({ query: { ...route.query, photo: undefined } })
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
      confirmDialog.value?.close(); pictureDialog.value?.close()
      const removed = targets.filter(item => moved.has(item.id))
      emit('recycled', removed.map(item => item.name))
      moved.forEach(id => imageModel.selected.delete(id))
      imageModel.items = imageModel.items.filter(item => !moved.has(item.id))
      imageModel.total = Math.max(0, imageModel.total - moved.size)
      imageModel.counts.total = Math.max(0, imageModel.counts.total - moved.size)
      imageModel.counts.candidates = Math.max(0, imageModel.counts.candidates - removed.filter(item => item.monochrome).length)
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
async function restore(item: Recycled) {
  imageModel.busy = true; imageModel.error = ''
  try { await api(`/recycle/${item.id}/restore?root=${encodeURIComponent(imageModel.recycleRoot)}`, {}); emit('message', `已还原 ${item.original}`); await load() }
  catch (error) { imageModel.error = (error as Error).message }
  finally { imageModel.busy = false }
}
function loadMore() { void load({ append: true }) }
watchEffect(() => {
  const button = moreButton.value
  const ready = canLoadMore.value && !toolbarBlocked.value && !imageModel.error
  observer?.disconnect()
  if (button && ready) observer?.observe(button)
}, { flush: 'post' })
onMounted(() => {
  if ('IntersectionObserver' in window) {
    observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) loadMore() }, { rootMargin: '0px 0px 240px' })
  }
  timer = setInterval(() => {
    if (!document.hidden && imageModel.scan.running && imageModel.view !== 'recycle' && !imageModel.busy) void load({ poll: true })
  }, 2000)
  void readRoute().then(() => { if (imageModel.view !== 'recycle') void scan() })
})
onUnmounted(() => { clearInterval(timer); observer?.disconnect(); stopPress() })
</script>

<template>
  <section class="image-library" :class="{ 'has-floating-actions': imageModel.view !== 'recycle' }">
    <div class="image-library-toolbar">
      <div class="image-tabs" role="tablist" aria-label="图片视图">
        <button role="tab" :aria-selected="imageModel.view === 'all'" :disabled="toolbarBlocked" @click="view('all')">全部图片 <span>{{ imageModel.counts.total || 0 }}</span></button>
        <button role="tab" :aria-selected="imageModel.view === 'candidates'" :disabled="toolbarBlocked" @click="view('candidates')">黑白候选 <span>{{ imageModel.counts.candidates || 0 }}</span></button>
        <button role="tab" :aria-selected="imageModel.view === 'recycle'" :disabled="toolbarBlocked" @click="view('recycle')">回收站</button>
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
    <p v-if="imageModel.counts.errors && imageModel.view !== 'recycle'" class="notice">{{ imageModel.counts.errors }} 张图片读取失败，可在“全部图片”中查看；原文件保留。</p>
    <div v-if="imageModel.scan.running && imageModel.view !== 'recycle'" class="image-scan" role="status"><span><Icon name="loader" class="loading-icon" :size="16" />{{ imageModel.scan.total ? `已检查 ${imageModel.scan.done} / ${imageModel.scan.total} 张，图片会陆续出现` : '正在读取根目录图片…' }}</span><progress v-if="imageModel.scan.total" :value="imageModel.scan.done" :max="imageModel.scan.total" aria-label="图片分析进度" /></div>
    <template v-if="imageModel.view !== 'recycle'">
      <div class="image-actions">
        <form class="search-box" @submit.prevent="filter"><Icon name="search" :size="17" /><input v-model="imageModel.search" :disabled="toolbarBlocked" maxlength="255" placeholder="搜索根目录图片" aria-label="搜索根目录图片" /><button class="text-button" :disabled="toolbarBlocked">搜索</button></form>
        <span class="muted" title="拍摄时间优先，其次图片日期、文件创建时间、修改时间">{{ imageModel.total }} 张 · 按照片时间从新到旧</span>
        <button v-if="imageModel.organizing" class="text-button" :disabled="blocked || !imageModel.items.length" @click="selectLoaded">{{ allSelected ? '取消已加载选择' : '全选已加载' }}</button>
      </div>
      <div class="image-grid" :aria-busy="imageModel.loading || imageModel.loadingMore">
        <template v-for="(item, index) in imageModel.items" :key="item.id + ':' + item.version">
        <h3 v-if="index === 0 || photoDay(item.sort_time) !== photoDay(imageModel.items[index - 1]!.sort_time)" class="col-span-full pt-3 pb-1 text-sm font-medium">{{ photoDay(item.sort_time) }}</h3>
        <article class="image-card">
          <button type="button" class="image-preview" :title="item.name" :disabled="blocked"
            :aria-label="(imageModel.organizing ? '选择 ' : '快速审阅 ') + item.name" :aria-pressed="imageModel.organizing ? isSelected(item) : undefined"
            aria-keyshortcuts="Shift+Enter" @click="activateImage($event, item)" @keydown.shift.enter.prevent="!$event.repeat && preview(item)"
            @pointerdown="startPress($event, item)" @pointermove="movePress" @pointerup="stopPress" @pointerleave="stopPress" @pointercancel="stopPress" @contextmenu.prevent>
            <span class="image-thumb">
              <img v-if="item.width && !item.error && !imageModel.broken[item.id]" :src="thumbnail(item)" alt="" draggable="false" loading="lazy" decoding="async" @error="imageModel.broken[item.id] = true" />
              <Icon v-else name="photo" class="text-muted" :size="16" />
            </span>
          </button>
        </article>
        </template>
      </div>
      <div v-if="canLoadMore" class="image-more"><button ref="moreButton" class="text-button" :disabled="toolbarBlocked" @click="loadMore">{{ imageModel.loadingMore ? '正在加载…' : '加载更多' }}</button></div>
      <div v-if="!imageModel.items.length && !canLoadMore && !imageModel.loading && !imageModel.error" class="empty-list tall">
        <Icon name="photo" :size="38" />
        <h2>{{ imageModel.scan.running ? '正在整理图片索引' : imageModel.appliedSearch ? '没有匹配的图片' : imageModel.view === 'candidates' ? '暂无黑白候选' : '根目录还没有图片' }}</h2>
        <p v-if="!imageModel.scan.running && !imageModel.appliedSearch && imageModel.view === 'all'">这里只展示直接放在下载根目录的图片，不进入子文件夹。</p>
      </div>
      <button v-if="imageModel.organizing && selectedCount" class="danger recycle-selection" :disabled="blocked" @click="confirm()"><Icon name="trash" :size="16" />移入回收站 · {{ selectedCount }} 张</button>
    </template>
    <template v-else>
      <p class="muted recycle-help">文件在项目回收站保留 15 天，期间可还原到原路径且不覆盖同名文件。到期后由容器自动永久删除，不进入 Windows 回收站，也无法再从这里恢复。</p>
      <p v-if="imageModel.cleanup.running" class="muted mt-2" role="status">正在检查到期文件…</p>
      <p v-else-if="imageModel.cleanup.checked" class="muted mt-2">最近检查：{{ new Date(imageModel.cleanup.checked * 1000).toLocaleString('zh-CN') }} · 本轮已永久清理 {{ imageModel.cleanup.removed }} 项</p>
      <p v-if="imageModel.cleanup.failed" class="notice error" role="alert">自动清理有 {{ imageModel.cleanup.failed }} 项异常，请查看运行日志。</p>
      <div class="my-3 flex flex-wrap items-end gap-4">
        <label v-if="imageModel.roots.length > 1">回收目录<select v-model="imageModel.recycleRoot" :disabled="blocked" @change="imageRoute('recycle')"><option v-for="root in imageModel.roots" :key="root.id" :value="root.id">{{ root.path }}</option></select></label>
      </div>
      <div class="recycle-list"><article v-for="item in imageModel.trash" :key="item.id"><span class="file-icon"><Icon :name="['image', 'xiaomi_upload', 'xiaomi_cloud'].includes(item.reason) ? 'photo' : 'file'" /></span><div><strong>{{ item.original }}</strong><p>{{ bytes(item.size) }} · {{ new Date(item.created * 1000).toLocaleString('zh-CN') }} · {{ item.reason === 'xiaomi_cloud' ? '云端联动回收' : item.reason === 'xiaomi_upload' ? '小米云上传后回收' : item.reason === 'image' ? '本地图片快筛' : '整理清理' }}</p><p v-if="item.state === 'exporting'" class="break-all">文件已移出项目回收站，需手动核对。记录：{{ item.id }}</p></div><button v-if="item.state !== 'exporting'" class="secondary" :disabled="blocked" @click="restore(item)"><Icon name="restore" :size="16" />还原</button></article></div><div v-if="!imageModel.trash.length" class="empty-list tall"><Icon name="trash" :size="38" /><h2>回收站是空的</h2><p>移入回收站的文件会出现在这里。</p></div>
    </template>
    <div v-if="imageModel.view === 'recycle'" class="pagination"><span>第 {{ imageModel.page }} / {{ Math.max(1, Math.ceil(imageModel.total / imageModel.pageSize)) }} 页</span><button class="secondary" :disabled="blocked || imageModel.page === 1" @click="page(-1)">上一页</button><button class="secondary" :disabled="blocked || imageModel.page * imageModel.pageSize >= imageModel.total" @click="page(1)">下一页</button></div>
    <ImageReviewDialog ref="reviewDialog" :load-page="listImages" @change="reviewChanged" @finish="finishReview" />
    <dialog ref="namesDialog" class="task-dialog" aria-labelledby="local-recycle-names">
      <div class="section-heading"><h2 id="local-recycle-names">最近回收 · {{ lastLocalRecycle.length }} 张</h2><button class="icon-button" aria-label="关闭清单" @click="namesDialog?.close()"><Icon name="close" /></button></div>
      <textarea ref="namesField" class="my-4" readonly rows="6" aria-label="实际回收的文件名" :value="formatNames(lastLocalRecycle)" />
      <div class="dialog-actions"><button class="secondary" @click="copyRecycledNames">{{ canCopy ? '复制文件名' : '选中文件名' }}</button></div>
    </dialog>
    <dialog ref="pictureDialog" class="task-dialog image-dialog">
      <template v-if="imageModel.picture">
        <div class="section-heading"><h2>图片详情</h2><button class="icon-button" aria-label="关闭图片详情" @click="pictureDialog?.close()"><Icon name="close" /></button></div>
        <img v-if="imageModel.picture.width && !imageModel.picture.error && !imageModel.broken[imageModel.picture.id]" :src="thumbnail(imageModel.picture)" :alt="imageModel.picture.name" />
        <div v-else class="empty-list"><Icon name="photo" :size="38" /><p>{{ imageModel.picture.error || (imageModel.broken[imageModel.picture.id] ? '缩略图加载失败，请刷新图片' : '缩略图尚未生成，请稍后刷新') }}</p></div>
        <p class="image-dialog-name">{{ imageModel.picture.name }}</p>
        <p class="muted"><template v-if="imageModel.picture.width">{{ imageModel.picture.width }} × {{ imageModel.picture.height }} · </template>{{ bytes(imageModel.picture.size) }}<span v-if="imageModel.picture.monochrome"> · 黑白候选</span></p>
        <p class="muted mt-2">{{ imageModel.picture.time_source ? timeSources[imageModel.picture.time_source] : '索引时间' }} · {{ takenAt(imageModel.picture.sort_time) }}</p>
        <div v-if="imageModel.organizing" class="dialog-actions"><button class="secondary" @click="pictureDialog?.close()">关闭</button><button class="danger" :disabled="blocked" @click="confirm([imageModel.picture!])"><Icon name="trash" :size="16" />移入回收站</button></div>
      </template>
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
