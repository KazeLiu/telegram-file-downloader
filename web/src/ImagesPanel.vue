<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api, bytes } from './api'
import Icon from './Icon.vue'

interface Picture { id: number; name: string; size: number; width: number | null; height: number | null; version: string; score: number | null; error: string; features: { color: number; light: number } | null }
interface Recycled { id: string; original: string; size: number; created: number; reason: string }
type View = 'all' | 'candidates' | 'recycle'
const imageModel = reactive({ view: 'all' as View, items: [] as Picture[], trash: [] as Recycled[], page: 1, total: 0, pageSize: 60,
  counts: { total: 0, candidates: 0, errors: 0 }, scan: { running: false, done: 0, total: 0, error: '' },
  threshold: 80, search: '', appliedSearch: '', loading: false, busy: false, error: '', selected: {} as Record<number, string>,
  confirmation: [] as Picture[], picture: null as Picture | null, broken: {} as Record<number, boolean> })
const emit = defineEmits<{ message: [value: string] }>()
const confirmDialog = ref<HTMLDialogElement>()
const pictureDialog = ref<HTMLDialogElement>()
const selectedCount = computed(() => Object.keys(imageModel.selected).length)
const blocked = computed(() => imageModel.loading || imageModel.busy)
const allSelected = computed(() => imageModel.items.length > 0 && imageModel.items.every(item => imageModel.selected[item.id] === item.version))
let timer: ReturnType<typeof setInterval>
let loadRevision = 0
let polling = false

function thumbnail(item: Picture) { return `/api/images/${item.id}/thumbnail?version=${encodeURIComponent(item.version)}` }
function clearSelection() { imageModel.selected = {} }
async function load(poll = false) {
  if (imageModel.loading || (poll && polling)) return
  const revision = ++loadRevision
  if (poll) polling = true
  else imageModel.loading = true
  if (!poll) imageModel.error = ''
  try {
    if (imageModel.view === 'recycle') {
      const result = await api(`/recycle?page=${imageModel.page}`)
      if (revision !== loadRevision) return
      imageModel.trash = result.items; imageModel.total = result.total; imageModel.pageSize = result.page_size
    } else {
      const result = await api(`/images?page=${imageModel.page}&candidate=${imageModel.view === 'candidates'}&threshold=${imageModel.threshold}&search=${encodeURIComponent(imageModel.appliedSearch)}`)
      if (revision !== loadRevision) return
      imageModel.scan = result.scan; imageModel.counts = result.counts
      if (!poll || (!selectedCount.value && !pictureDialog.value?.open && !confirmDialog.value?.open)) {
        imageModel.items = result.items; imageModel.total = result.total; imageModel.pageSize = result.page_size; imageModel.broken = {}
      }
    }
  } catch (error) { if (revision === loadRevision) imageModel.error = (error as Error).message }
  finally { if (poll) polling = false; else imageModel.loading = false }
}
async function scan() {
  if (blocked.value) return
  clearSelection(); imageModel.error = ''
  imageModel.scan.running = true
  try { imageModel.scan = await api('/images/scan', {}); await load() }
  catch (error) { imageModel.error = (error as Error).message; imageModel.scan.running = false }
}
async function view(value: View) { if (blocked.value) return; imageModel.view = value; imageModel.page = 1; clearSelection(); await load() }
async function filter() { if (blocked.value) return; imageModel.page = 1; imageModel.appliedSearch = imageModel.search; clearSelection(); await load() }
async function page(delta: number) { imageModel.page += delta; clearSelection(); await load() }
function selectPage() {
  if (allSelected.value) clearSelection()
  else imageModel.selected = Object.fromEntries(imageModel.items.map(item => [item.id, item.version]))
}
function select(item: Picture, checked: boolean) {
  if (checked) imageModel.selected[item.id] = item.version
  else delete imageModel.selected[item.id]
}
async function preview(item: Picture) { imageModel.picture = item; await nextTick(); pictureDialog.value?.showModal() }
async function confirm(items?: Picture[]) {
  imageModel.confirmation = items || imageModel.items.filter(item => imageModel.selected[item.id] === item.version)
  if (!imageModel.confirmation.length) return
  await nextTick(); confirmDialog.value?.showModal()
}
async function recycle() {
  imageModel.busy = true; imageModel.error = ''
  try {
    const result = await api('/images/recycle', { items: imageModel.confirmation.map(item => ({ id: item.id, version: item.version })) })
    confirmDialog.value?.close(); pictureDialog.value?.close(); clearSelection()
    if (result.moved.length) emit('message', `已将 ${result.moved.length} 张图片移入回收站`)
    const errors = result.failures.map((failure: { id: number; error: string }) => `${imageModel.confirmation.find(item => item.id === failure.id)?.name || failure.id}：${failure.error}`)
    await load()
    if (errors.length) imageModel.error = errors.join('；')
  } catch (error) { imageModel.error = (error as Error).message }
  finally { imageModel.busy = false }
}
async function restore(item: Recycled) {
  imageModel.busy = true; imageModel.error = ''
  try { await api(`/recycle/${item.id}/restore`, {}); emit('message', `已还原 ${item.original}`); await load() }
  catch (error) { imageModel.error = (error as Error).message }
  finally { imageModel.busy = false }
}
onMounted(() => { timer = setInterval(() => { if (!document.hidden && imageModel.scan.running && imageModel.view !== 'recycle' && !imageModel.busy) void load(true) }, 2000); void scan() })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <section class="image-library">
    <div class="image-library-toolbar"><div class="image-tabs" role="tablist" aria-label="图片视图"><button role="tab" :aria-selected="imageModel.view === 'all'" :disabled="blocked" @click="view('all')">全部图片 <span>{{ imageModel.counts.total || 0 }}</span></button><button role="tab" :aria-selected="imageModel.view === 'candidates'" :disabled="blocked" @click="view('candidates')"><Icon name="sketch" :size="16" />疑似线稿 <span>{{ imageModel.counts.candidates || 0 }}</span></button><button role="tab" :aria-selected="imageModel.view === 'recycle'" :disabled="blocked" @click="view('recycle')">回收站</button></div><button v-if="imageModel.view !== 'recycle'" class="secondary" :disabled="blocked || imageModel.scan.running" @click="scan"><Icon :name="imageModel.scan.running ? 'loader' : 'refresh'" :class="{ 'loading-icon': imageModel.scan.running }" :size="16" />{{ imageModel.scan.running ? '正在扫描' : '刷新图片' }}</button><button v-else class="secondary" :disabled="blocked" @click="load()"><Icon name="refresh" :size="16" />刷新</button></div>
    <p v-if="imageModel.error" class="notice error" role="alert">{{ imageModel.error }}</p>
    <p v-if="imageModel.scan.error && imageModel.view !== 'recycle'" class="notice error" role="alert">扫描失败：{{ imageModel.scan.error }}</p>
    <p v-if="imageModel.counts.errors && imageModel.view !== 'recycle'" class="notice">{{ imageModel.counts.errors }} 张图片读取失败，可在“全部图片”中查看；原文件保留。</p>
    <div v-if="imageModel.view === 'candidates'" class="candidate-guide"><div><h2>把未上色的那一份，先挑出来。</h2><p>按低彩度、浅底与线条特征筛选，黑白成稿也可能入选。先看图，再决定是否移入回收站。</p></div><label>筛选范围<select v-model="imageModel.threshold" :disabled="blocked" @change="filter"><option :value="80">保守 · 更少候选</option><option :value="65">宽松 · 更多候选</option></select></label></div>
    <div v-if="imageModel.scan.running && imageModel.view !== 'recycle'" class="image-scan" role="status"><span><Icon name="loader" class="loading-icon" :size="16" />{{ imageModel.scan.total ? `已检查 ${imageModel.scan.done} / ${imageModel.scan.total} 张，图片会陆续出现` : '正在读取根目录图片…' }}</span><progress v-if="imageModel.scan.total" :value="imageModel.scan.done" :max="imageModel.scan.total" aria-label="图片分析进度" /></div>
    <template v-if="imageModel.view !== 'recycle'">
      <div class="image-actions"><form class="search-box" @submit.prevent="filter"><Icon name="search" :size="17" /><input v-model="imageModel.search" :disabled="blocked" placeholder="搜索根目录图片" aria-label="搜索根目录图片" /><button class="text-button" :disabled="blocked">搜索</button></form><span class="muted">仅根目录 · {{ imageModel.total }} 张</span><button class="text-button" :disabled="blocked || !imageModel.items.length" @click="selectPage">{{ allSelected ? '取消本页选择' : '选择本页' }}</button><button class="secondary recycle-selection" :disabled="blocked || !selectedCount" @click="confirm()"><Icon name="trash" :size="16" />移入回收站<span v-if="selectedCount">({{ selectedCount }})</span></button></div>
      <div class="image-grid" :aria-busy="imageModel.loading"><article v-for="item in imageModel.items" :key="item.id + ':' + item.version" class="image-card" :class="{ selected: imageModel.selected[item.id] === item.version }"><div class="image-frame"><button class="image-preview" :aria-label="'查看 ' + item.name" @click="preview(item)"><img v-if="item.width && !item.error && !imageModel.broken[item.id]" :src="thumbnail(item)" :alt="item.name" loading="lazy" decoding="async" @error="imageModel.broken[item.id] = true" /><span v-else class="image-placeholder"><Icon name="photo" :size="32" />{{ item.error ? '图片读取失败' : '等待缩略图' }}</span></button><label class="image-select"><input type="checkbox" :checked="imageModel.selected[item.id] === item.version" :disabled="blocked" :aria-label="'选择 ' + item.name" @change="select(item, ($event.target as HTMLInputElement).checked)" /></label><span v-if="item.score !== null && item.score >= imageModel.threshold" class="sketch-badge"><Icon name="sketch" :size="13" />疑似线稿</span></div><div class="image-caption"><p :title="item.name">{{ item.name }}</p><div><span>{{ item.width ? `${item.width} × ${item.height}` : item.error ? '详情见预览' : '分析中' }} · {{ bytes(item.size) }}</span><button class="icon-button" :aria-label="'移入回收站 ' + item.name" :disabled="blocked" @click="confirm([item])"><Icon name="trash" :size="16" /></button></div></div></article></div>
      <div v-if="!imageModel.items.length" class="empty-list tall"><Icon :name="imageModel.view === 'candidates' ? 'sketch' : 'photo'" :size="38" /><h2>{{ imageModel.scan.running ? '正在整理图片索引' : imageModel.view === 'candidates' ? '暂时没有符合条件的图片' : '根目录还没有图片' }}</h2><p>{{ imageModel.view === 'candidates' ? '可以切换宽松范围；候选只供复核，不会自动删除。' : '这里只展示直接放在下载根目录的图片，不进入子文件夹。' }}</p></div>
    </template>
    <template v-else>
      <p class="muted recycle-help">PSD、TXT 和手动删除的图片都保存在下载目录内的持久回收站，不会自动清空。还原到原路径，同名文件不会被覆盖。</p>
      <div class="recycle-list"><article v-for="item in imageModel.trash" :key="item.id"><span class="file-icon"><Icon :name="['image', 'xiaomi_upload'].includes(item.reason) ? 'photo' : 'file'" /></span><div><strong>{{ item.original }}</strong><p>{{ bytes(item.size) }} · {{ new Date(item.created * 1000).toLocaleString('zh-CN') }} · {{ item.reason === 'xiaomi_upload' ? '小米云上传后回收' : item.reason === 'image' ? '图片管理' : '整理清理' }}</p></div><button class="secondary" :disabled="blocked" @click="restore(item)"><Icon name="restore" :size="16" />还原</button></article></div><div v-if="!imageModel.trash.length" class="empty-list tall"><Icon name="trash" :size="38" /><h2>回收站是空的</h2><p>移入回收站的文件会出现在这里。</p></div>
    </template>
    <div class="pagination"><span>第 {{ imageModel.page }} / {{ Math.max(1, Math.ceil(imageModel.total / imageModel.pageSize)) }} 页</span><button class="secondary" :disabled="blocked || imageModel.page === 1" @click="page(-1)">上一页</button><button class="secondary" :disabled="blocked || imageModel.page * imageModel.pageSize >= imageModel.total" @click="page(1)">下一页</button></div>
    <dialog ref="pictureDialog" class="task-dialog image-dialog"><template v-if="imageModel.picture"><div class="section-heading"><h2>查看图片</h2><button class="icon-button" aria-label="关闭图片预览" @click="pictureDialog?.close()"><Icon name="close" /></button></div><img v-if="imageModel.picture.width && !imageModel.picture.error" :src="thumbnail(imageModel.picture)" :alt="imageModel.picture.name" /><div v-else class="empty-list"><Icon name="photo" :size="38" /><p>{{ imageModel.picture.error || '缩略图尚未生成，请稍后刷新' }}</p></div><p class="image-dialog-name">{{ imageModel.picture.name }}</p><p class="muted">{{ imageModel.picture.width }} × {{ imageModel.picture.height }} · {{ bytes(imageModel.picture.size) }}<span v-if="imageModel.picture.score !== null && imageModel.picture.score >= imageModel.threshold"> · 疑似线稿，请人工复核</span></p><div class="dialog-actions"><button class="secondary" @click="pictureDialog?.close()">保留</button><button class="danger" :disabled="blocked" @click="confirm([imageModel.picture!])"><Icon name="trash" :size="16" />移入回收站</button></div></template></dialog>
    <dialog ref="confirmDialog" class="task-dialog recycle-dialog"><div class="section-heading"><h2>移入回收站？</h2><button class="icon-button" :disabled="imageModel.busy" aria-label="取消回收" @click="confirmDialog?.close()"><Icon name="close" /></button></div><p>将选中的 {{ imageModel.confirmation.length }} 张图片移出根目录，可在回收站中还原。</p><div class="recycle-confirm-list"><p v-for="item in imageModel.confirmation" :key="item.id">{{ item.name }}</p></div><p v-if="imageModel.error" class="notice error" role="alert">{{ imageModel.error }}</p><div class="dialog-actions"><button class="secondary" :disabled="imageModel.busy" @click="confirmDialog?.close()">取消</button><button class="danger" :disabled="imageModel.busy" @click="recycle"><Icon :name="imageModel.busy ? 'loader' : 'trash'" :class="{ 'loading-icon': imageModel.busy }" :size="16" />{{ imageModel.busy ? '正在移入…' : '确认移入回收站' }}</button></div></dialog>
  </section>
</template>
