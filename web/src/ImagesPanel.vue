<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watchEffect } from 'vue'
import { api, bytes, imageThumbnail as thumbnail, type LibraryPicture as Picture } from './api'
import ImageReviewDialog from './ImageReviewDialog.vue'
import Icon from './Icon.vue'

interface Recycled { id: string; original: string; size: number; created: number; reason: string }
type View = 'all' | 'candidates' | 'recycle'
const imageModel = reactive({ view: 'all' as View, organizing: false, items: [] as Picture[], trash: [] as Recycled[], page: 1,
  total: 0, pageSize: 50, nextCursor: null as number | null,
  counts: { total: 0, candidates: 0, errors: 0 }, scan: { running: false, done: 0, total: 0, error: '' },
  search: '', appliedSearch: '', loading: false, loadingMore: false, busy: false, error: '', selected: new Map<number, Picture>(),
  confirmation: [] as Picture[], picture: null as Picture | null, broken: {} as Record<number, boolean> })
const emit = defineEmits<{ message: [value: string] }>()
const confirmDialog = ref<HTMLDialogElement>()
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
      const result = await api(`/recycle?page=${imageModel.page}`)
      if (revision !== loadRevision) return
      imageModel.trash = result.items; imageModel.total = result.total; imageModel.pageSize = result.page_size
    } else {
      const result = await listImages(append ? imageModel.nextCursor : null)
      if (revision !== loadRevision) return
      imageModel.scan = result.scan; imageModel.counts = result.counts
      if (append) {
        const loaded = new Set(imageModel.items.map(item => item.id))
        imageModel.items.push(...result.items.filter(item => !loaded.has(item.id)))
        imageModel.total = result.total; imageModel.nextCursor = result.next_cursor
      } else if (!poll || !result.scan.running || (!selectedCount.value && !pictureDialog.value?.open && !confirmDialog.value?.open)) {
        imageModel.items = result.items; imageModel.total = result.total; imageModel.nextCursor = result.next_cursor; imageModel.broken = {}
      }
    }
  } catch (error) { if (revision === loadRevision) imageModel.error = (error as Error).message }
  finally {
    if (poll) polling = false
    else if (append) imageModel.loadingMore = false
    else imageModel.loading = false
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
  imageModel.view = value; imageModel.page = 1; imageModel.total = 0
  imageModel.items = []; imageModel.trash = []; imageModel.nextCursor = null; clearSelection()
  if (value === 'recycle') imageModel.organizing = false
  await load()
}
async function filter() {
  if (toolbarBlocked.value) return
  imageModel.appliedSearch = imageModel.search; imageModel.total = 0
  imageModel.items = []; imageModel.nextCursor = null; clearSelection()
  await load()
}
async function page(delta: number) { imageModel.page += delta; clearSelection(); await load() }
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
function review(item: Picture) {
  reviewDialog.value?.open(imageModel.items, item, imageModel.nextCursor, imageModel.total)
}
function finishReview(items: Picture[], submit: boolean) {
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
async function restore(item: Recycled) {
  imageModel.busy = true; imageModel.error = ''
  try { await api(`/recycle/${item.id}/restore`, {}); emit('message', `已还原 ${item.original}`); await load() }
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
  void scan()
})
onUnmounted(() => { clearInterval(timer); observer?.disconnect() })
</script>

<template>
  <section class="image-library" :class="{ 'has-selection': imageModel.organizing && selectedCount }">
    <div class="image-library-toolbar">
      <div class="image-tabs" role="tablist" aria-label="图片视图">
        <button role="tab" :aria-selected="imageModel.view === 'all'" :disabled="toolbarBlocked" @click="view('all')">全部图片 <span>{{ imageModel.counts.total || 0 }}</span></button>
        <button role="tab" :aria-selected="imageModel.view === 'candidates'" :disabled="toolbarBlocked" @click="view('candidates')">黑白候选 <span>{{ imageModel.counts.candidates || 0 }}</span></button>
        <button role="tab" :aria-selected="imageModel.view === 'recycle'" :disabled="toolbarBlocked" @click="view('recycle')">回收站</button>
      </div>
      <div class="image-toolbar-actions">
        <template v-if="imageModel.view !== 'recycle'">
          <button class="secondary" :disabled="toolbarBlocked || imageModel.scan.running" @click="scan"><Icon :name="imageModel.scan.running ? 'loader' : 'refresh'" :class="{ 'loading-icon': imageModel.scan.running }" :size="16" />{{ imageModel.scan.running ? '正在扫描' : '刷新图片' }}</button>
          <button :class="imageModel.organizing ? 'primary' : 'secondary'" :disabled="blocked" @click="toggleOrganizing">{{ imageModel.organizing ? '完成' : '整理' }}</button>
        </template>
        <button v-else class="secondary" :disabled="blocked" @click="load()"><Icon name="refresh" :size="16" />刷新</button>
      </div>
    </div>
    <p v-if="imageModel.error" class="notice error" role="alert">{{ imageModel.error }}</p>
    <p v-if="imageModel.scan.error && imageModel.view !== 'recycle'" class="notice error" role="alert">扫描失败：{{ imageModel.scan.error }}</p>
    <p v-if="imageModel.counts.errors && imageModel.view !== 'recycle'" class="notice">{{ imageModel.counts.errors }} 张图片读取失败，可在“全部图片”中查看；原文件保留。</p>
    <div v-if="imageModel.scan.running && imageModel.view !== 'recycle'" class="image-scan" role="status"><span><Icon name="loader" class="loading-icon" :size="16" />{{ imageModel.scan.total ? `已检查 ${imageModel.scan.done} / ${imageModel.scan.total} 张，图片会陆续出现` : '正在读取根目录图片…' }}</span><progress v-if="imageModel.scan.total" :value="imageModel.scan.done" :max="imageModel.scan.total" aria-label="图片分析进度" /></div>
    <template v-if="imageModel.view !== 'recycle'">
      <div class="image-actions">
        <form class="search-box" @submit.prevent="filter"><Icon name="search" :size="17" /><input v-model="imageModel.search" :disabled="toolbarBlocked" maxlength="255" placeholder="搜索根目录图片" aria-label="搜索根目录图片" /><button class="text-button" :disabled="toolbarBlocked">搜索</button></form>
        <span class="muted">{{ imageModel.total }} 张</span>
        <button v-if="imageModel.organizing" class="text-button" :disabled="blocked || !imageModel.items.length" @click="selectLoaded">{{ allSelected ? '取消已加载选择' : '全选已加载' }}</button>
      </div>
      <div class="image-grid" :aria-busy="imageModel.loading || imageModel.loadingMore">
        <article v-for="item in imageModel.items" :key="item.id + ':' + item.version" class="image-card">
          <div class="image-preview" :class="{ selected: imageModel.organizing && isSelected(item) }" :title="item.name">
            <img v-if="item.width && !item.error && !imageModel.broken[item.id]" :src="thumbnail(item)" alt="" loading="lazy" decoding="async" @error="imageModel.broken[item.id] = true" />
            <Icon v-else name="photo" class="image-placeholder" :size="16" />
            <template v-if="imageModel.organizing">
              <input type="checkbox" :checked="isSelected(item)" :aria-label="'选择 ' + item.name" :disabled="blocked" @change="select(item, ($event.target as HTMLInputElement).checked)" />
              <span class="image-check" aria-hidden="true"><Icon v-if="isSelected(item)" name="check" :size="12" /></span>
            </template>
            <button v-else :aria-label="'快速审阅 ' + item.name" :disabled="blocked" @click="review(item)"></button>
          </div>
          <button v-if="imageModel.organizing" class="image-details" :aria-label="'查看 ' + item.name + ' 的详情'" :disabled="blocked" @click="preview(item)">详情</button>
        </article>
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
      <p class="muted recycle-help">PSD、TXT 和手动删除的图片都保存在下载目录内的持久回收站，不会自动清空。还原到原路径，同名文件不会被覆盖。</p>
      <div class="recycle-list"><article v-for="item in imageModel.trash" :key="item.id"><span class="file-icon"><Icon :name="['image', 'xiaomi_upload'].includes(item.reason) ? 'photo' : 'file'" /></span><div><strong>{{ item.original }}</strong><p>{{ bytes(item.size) }} · {{ new Date(item.created * 1000).toLocaleString('zh-CN') }} · {{ item.reason === 'xiaomi_upload' ? '小米云上传后回收' : item.reason === 'image' ? '图片管理' : '整理清理' }}</p></div><button class="secondary" :disabled="blocked" @click="restore(item)"><Icon name="restore" :size="16" />还原</button></article></div><div v-if="!imageModel.trash.length" class="empty-list tall"><Icon name="trash" :size="38" /><h2>回收站是空的</h2><p>移入回收站的文件会出现在这里。</p></div>
    </template>
    <div v-if="imageModel.view === 'recycle'" class="pagination"><span>第 {{ imageModel.page }} / {{ Math.max(1, Math.ceil(imageModel.total / imageModel.pageSize)) }} 页</span><button class="secondary" :disabled="blocked || imageModel.page === 1" @click="page(-1)">上一页</button><button class="secondary" :disabled="blocked || imageModel.page * imageModel.pageSize >= imageModel.total" @click="page(1)">下一页</button></div>
    <ImageReviewDialog ref="reviewDialog" :load-page="listImages" @finish="finishReview" />
    <dialog ref="pictureDialog" class="task-dialog image-dialog">
      <template v-if="imageModel.picture">
        <div class="section-heading"><h2>图片详情</h2><button class="icon-button" aria-label="关闭图片详情" @click="pictureDialog?.close()"><Icon name="close" /></button></div>
        <img v-if="imageModel.picture.width && !imageModel.picture.error && !imageModel.broken[imageModel.picture.id]" :src="thumbnail(imageModel.picture)" :alt="imageModel.picture.name" />
        <div v-else class="empty-list"><Icon name="photo" :size="38" /><p>{{ imageModel.picture.error || (imageModel.broken[imageModel.picture.id] ? '缩略图加载失败，请刷新图片' : '缩略图尚未生成，请稍后刷新') }}</p></div>
        <p class="image-dialog-name">{{ imageModel.picture.name }}</p>
        <p class="muted"><template v-if="imageModel.picture.width">{{ imageModel.picture.width }} × {{ imageModel.picture.height }} · </template>{{ bytes(imageModel.picture.size) }}<span v-if="imageModel.picture.monochrome"> · 黑白候选</span></p>
        <div v-if="imageModel.organizing" class="dialog-actions"><button class="secondary" @click="pictureDialog?.close()">关闭</button><button class="danger" :disabled="blocked" @click="confirm([imageModel.picture!])"><Icon name="trash" :size="16" />移入回收站</button></div>
      </template>
    </dialog>
    <dialog ref="confirmDialog" class="task-dialog recycle-dialog" @cancel="imageModel.busy && $event.preventDefault()">
      <div class="section-heading"><h2>移入回收站？</h2><button class="icon-button" :disabled="imageModel.busy" aria-label="取消回收" @click="confirmDialog?.close()"><Icon name="close" /></button></div>
      <p>将选中的 {{ imageModel.confirmation.length }} 张图片移出根目录，可在回收站中还原。</p>
      <div class="recycle-confirm-list"><p v-for="item in imageModel.confirmation" :key="item.id">{{ item.name }}</p></div>
      <p v-if="imageModel.error" class="notice error" role="alert">{{ imageModel.error }}</p>
      <div class="dialog-actions"><button class="secondary" :disabled="imageModel.busy" @click="confirmDialog?.close()">取消</button><button class="danger" :disabled="toolbarBlocked" @click="recycle"><Icon :name="imageModel.busy ? 'loader' : 'trash'" :class="{ 'loading-icon': imageModel.busy }" :size="16" />{{ imageModel.busy ? '正在移入…' : '确认移入回收站' }}</button></div>
    </dialog>
  </section>
</template>
