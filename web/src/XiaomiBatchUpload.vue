<script setup lang="ts">
import { computed, onUnmounted, reactive, ref } from 'vue'
import { api, bytes } from './api'
import Icon from './Icon.vue'

type LocalFile = { name: string; kind: 'image' | 'video'; size: number; version: string }
type ItemState = 'waiting' | 'uploading' | 'uploaded' | 'verified' | 'failed' | 'recycled' | 'kept'
type Verification = { active: boolean; phase: 'receipt' | 'date' | 'album' | 'local'; done: number; total: number; pages: number; page: number; start: string | null; end: string | null }
type Job = { id: string; album: string; state: 'uploading' | 'pausing' | 'paused' | 'verifying' | 'stopping' | 'stopped' | 'complete'; current: string; error: string;
  total: number; done: number; eligible: number; revision: number; page_size: number; counts: Partial<Record<ItemState, number>>;
  verification: Verification | null;
  items: { name: string; status: ItemState; error: string }[] }

const props = defineProps<{ connection: string; album: string; albums: { id: string; name: string }[]; disabled: boolean }>()
const emit = defineEmits<{ message: [text: string]; finished: [album: string] }>()
const dialog = ref<HTMLDialogElement>()
const model = reactive({ files: [] as LocalFile[], selected: new Set<string>(), job: null as Job | null,
  selecting: false, confirming: false, page: 1, busy: false, error: '', note: '' })
const running = computed(() => !!model.job && !['complete', 'stopped'].includes(model.job.state))
const checking = computed(() => model.job?.verification?.active ? model.job.verification : null)
const working = computed(() => running.value || !!checking.value)
function dateLabel(day: string) { return `${day.slice(0, 4)}-${day.slice(4, 6)}-${day.slice(6, 8)}` }
const progressText = computed(() => {
  const job = model.job
  if (!job) return ''
  const check = checking.value
  if (check) {
    if (check.phase === 'receipt') return `正在核对小米上传回执 · 已确认 ${check.done} / ${check.total} 个文件`
    if (check.phase === 'local') return `正在回收本地图片 · 已处理 ${check.done} / ${check.total} 张`
    const scope = check.phase === 'date' ? `${dateLabel(check.start!)} 至 ${dateLabel(check.end!)}` : '缺少云端日期，正在扫描目标相册'
    return `已确认 ${check.done} / ${check.total} 个文件 · ${scope} · 第 ${check.page} 页（累计读取 ${check.pages} 页）`
  }
  if (job.state === 'paused') return `已暂停 · 已处理 ${job.done} / ${job.total}`
  if (job.state === 'pausing') return `正在暂停，等待在途文件完成 · ${job.current || '正在准备'}`
  if (job.state === 'stopping') return job.current ? `正在停止，等待在途文件完成 · ${job.current}` : '正在停止，核对已上传的文件…'
  if (job.state === 'verifying') return '正在核对目标相册中的文件…'
  return `已处理 ${job.done} / ${job.total} · 正在上传 ${job.counts.uploading || 0} / 3 个文件 · ${job.current || '正在准备'}`
})
const albumName = computed(() => {
  const id = model.selecting ? props.album : model.job?.album
  return props.albums.find(album => album.id === id)?.name || id || ''
})
const pageSize = computed(() => model.selecting ? 60 : model.job?.page_size || 60)
const pages = computed(() => Math.max(1, Math.ceil((model.selecting ? model.files.length : model.job?.total || 0) / pageSize.value)))
const filesOnPage = computed(() => model.files.slice((model.page - 1) * pageSize.value, model.page * pageSize.value))
const allSelected = computed(() => model.files.length > 0 && model.selected.size === model.files.length)
const labels: Record<ItemState, string> = { waiting: '未上传', uploading: '正在上传', uploaded: '尚未确认', verified: '云端已确认', failed: '上传未完成', recycled: '已回收本地图片', kept: '本地未回收' }
let timer: ReturnType<typeof setTimeout>
let disposed = false
let promptedJob = ''
let finishedJob = ''
let jobRead = 0

async function run(action: () => Promise<void>) {
  if (model.busy) return
  model.busy = true; model.error = ''; model.note = ''
  try { await action() }
  catch (error) { model.error = (error as Error).message; model.note = '' }
  finally { model.busy = false; completedJob() }
}

async function loadFiles() {
  model.selecting = true; model.confirming = false; model.page = 1
  model.files = []; model.selected.clear()
  model.files = (await api<{ items: LocalFile[] }>(`/xiaomi/local-media?connection=${props.connection}`)).items
}

async function loadJob() {
  clearTimeout(timer)
  const revision = ++jobRead
  const result = await api<{ job: Job | null }>(`/xiaomi/batch?connection=${props.connection}&page=${model.page}`)
  if (disposed || revision !== jobRead) return
  model.job = result.job
  if (model.job && !working.value && !model.busy) {
    completedJob()
  }
  if (working.value) timer = setTimeout(() => void pollJob(), 1000)
}

function completedJob() {
  if (disposed) return
  if (model.job && !working.value && !model.selecting && !model.error) {
    if (finishedJob !== model.job.id) { finishedJob = model.job.id; emit('finished', model.job.album) }
    if (model.job.eligible && promptedJob !== model.job.id) {
      promptedJob = model.job.id
      model.confirming = true
      if (!dialog.value?.open) dialog.value?.showModal()
    }
  }
}

async function pollJob() {
  const revision = jobRead + 1
  try { await loadJob() }
  catch (error) { if (!disposed && revision === jobRead) model.error = `进度读取失败：${(error as Error).message}` }
}

async function checkRequest(path: string, body: unknown) {
  clearTimeout(timer)
  timer = setTimeout(() => void pollJob(), 500)
  let result: { moved: number } | undefined
  let failure: Error | undefined
  try { result = await api<{ moved: number }>(path, body) }
  catch (error) { failure = error as Error }
  finally { clearTimeout(timer) }
  try { await loadJob() }
  catch (error) {
    if (failure) throw new Error(`${failure.message}；批次状态读取失败：${(error as Error).message}`)
    throw error
  }
  if (failure) throw failure
  model.error = ''
  return result!
}

async function loadDialog() {
  model.selecting = false; model.confirming = false; model.page = 1
  await loadJob()
  if (!model.job) await loadFiles()
}

function open() {
  dialog.value?.showModal()
  void run(loadDialog)
}

function selectAll() {
  if (allSelected.value) model.selected.clear()
  else model.selected = new Set(model.files.map(file => file.name))
}

function select(name: string, event: Event) {
  if ((event.target as HTMLInputElement).checked) model.selected.add(name)
  else model.selected.delete(name)
}

function start() {
  return run(async () => {
    const items = model.files.filter(item => model.selected.has(item.name)).map(({ name, version }) => ({ name, version }))
    await api('/xiaomi/batch', { connection: props.connection, album: props.album, items })
    model.selecting = false; model.job = null; model.page = 1
    await loadJob()
  })
}

function page(delta: number) {
  if (model.selecting) { model.page += delta; return }
  return run(async () => {
    const previous = model.page
    model.page += delta
    try { await loadJob() } catch (error) { model.page = previous; throw error }
  })
}

function verify() {
  return run(async () => {
    await checkRequest('/xiaomi/batch/verify', { connection: props.connection, job: model.job!.id })
  })
}

function control(action: 'pause' | 'resume' | 'stop') {
  return run(async () => {
    await api('/xiaomi/batch/control', { connection: props.connection, job: model.job!.id, action })
    await loadJob()
  })
}

function recycle() {
  model.confirming = false
  return run(async () => {
    model.note = '正在重新核对云端并回收本地图片…'
    const { moved } = await checkRequest('/xiaomi/batch/recycle', {
      connection: props.connection, job: model.job!.id, revision: model.job!.revision,
    })
    if (moved) emit('message', `已将 ${moved} 张图片移入本地回收站`)
    model.note = moved ? `已回收 ${moved} 张本地图片。` : '本次没有移动图片，请查看下方逐项结果。'
  })
}

onUnmounted(() => { disposed = true; jobRead++; clearTimeout(timer) })
</script>

<template>
  <button class="primary" :disabled="disabled || model.busy" @click="open">从本地目录上传</button>
  <dialog ref="dialog" class="task-dialog batch-dialog">
    <div class="section-heading"><h2>批量上传{{ albumName ? `到「${albumName}」` : '' }}</h2><button class="icon-button" aria-label="关闭批量上传" :disabled="model.busy" @click="dialog?.close()"><Icon name="close" /></button></div>
    <p v-if="model.error" class="notice error" role="alert">{{ model.error }}<button class="text-button" :disabled="model.busy" @click="run(loadDialog)">刷新</button></p>

    <template v-if="model.selecting">
      <div class="section-heading batch-tools"><button class="secondary" :disabled="model.busy || !model.files.length" @click="selectAll">{{ allSelected ? '取消全选' : '全选全部页面' }}</button><span class="muted">已选 {{ model.selected.size }} / {{ model.files.length }} 个文件</span></div>
      <ul v-if="filesOnPage.length" class="batch-list">
        <li v-for="item in filesOnPage" :key="item.name"><label><input type="checkbox" :checked="model.selected.has(item.name)" :disabled="model.busy" @change="select(item.name, $event)" /><Icon :name="item.kind === 'video' ? 'video' : 'photo'" :size="17" /><span>{{ item.name }}</span><small class="muted">{{ bytes(item.size) }}</small></label></li>
      </ul>
      <p v-else-if="!model.error" class="empty-list">{{ model.busy ? '正在读取下载目录…' : '下载根目录没有符合上传大小限制的图片或视频。' }}</p>
      <p v-if="album === '1000'" class="muted">隐私相册请在小米云网页版上传。</p>
      <p v-if="model.job?.eligible" class="muted">开始新批次会替换上批结果，未回收的图片会留在原处。</p>
    </template>

    <template v-else-if="model.job">
      <p v-if="model.job.error" class="notice" role="status">{{ model.job.error }}</p>
      <template v-if="working">
        <p class="batch-progress" role="status">{{ progressText }}</p>
        <progress :value="checking ? checking.done : model.job.done" :max="checking ? checking.total : model.job.total" :aria-label="checking ? '云端核对与本地回收进度' : '批量上传处理进度'" />
        <div v-if="running" class="batch-controls">
          <button v-if="model.job.state === 'uploading'" class="secondary" :disabled="model.busy" @click="control('pause')"><Icon name="pause" :size="17" />暂停</button>
          <button v-if="model.job.state === 'pausing' || model.job.state === 'paused'" class="primary" :disabled="model.busy" @click="control('resume')"><Icon name="play" :size="17" />继续上传</button>
          <button v-if="model.job.state !== 'stopping'" class="secondary danger-text" :disabled="model.busy" @click="control('stop')"><Icon name="close" :size="17" />停止</button>
        </div>
        <p v-if="running" class="muted batch-tools">最多同时上传 3 个文件。暂停、停止会等待在途文件完成，不再开始新文件。关闭窗口不等于停止；批次结束后，有可回收图片时会再次询问。</p>
        <p v-if="model.job.state === 'paused'" class="muted">暂停保留本批次的云端写操作，继续或停止后才能进行其他上传或云端回收。</p>
      </template>
      <template v-else>
        <p class="batch-progress" role="status">{{ model.job.state === 'stopped' ? '批次已停止。' : '批次已结束。' }}云端已确认 {{ (model.job.counts.verified || 0) + (model.job.counts.recycled || 0) + (model.job.counts.kept || 0) }} / {{ model.job.total }} 个文件。{{ model.job.eligible }} 张图片可回收，视频保留在本地。</p>
        <p v-if="model.note" class="notice" role="status">{{ model.note }}</p>
        <section v-if="model.confirming" class="batch-recycle-prompt" aria-labelledby="batch-recycle-question">
          <h3 id="batch-recycle-question">是否回收已上传的本地照片？</h3>
          <p>可回收 {{ model.job.eligible }} 张，移入项目回收站保留 15 天，之后自动永久清理。云端照片不删除；未上传、未确认和失败的本地文件保留。</p>
          <p class="muted">执行前会再次核对云端记录和本地文件，已变化的文件不移动。</p>
          <div class="dialog-actions"><button class="secondary" :disabled="model.busy" @click="model.confirming = false">暂时保留</button><button class="danger" :disabled="model.busy" @click="recycle">回收这 {{ model.job.eligible }} 张本地照片</button></div>
        </section>
        <ul class="batch-list">
          <li v-for="item in model.job.items" :key="item.name" class="batch-result"><span>{{ item.name }}</span><span class="badge" :class="{ completed: item.status === 'verified' || item.status === 'recycled', failed: item.status === 'failed' || item.error }">{{ labels[item.status] }}</span><small v-if="item.error" class="danger-text">{{ item.error }}</small></li>
        </ul>
      </template>
    </template>
    <p v-else-if="model.busy" class="empty-list" role="status">正在读取批次…</p>

    <div v-if="!working && pages > 1" class="pagination">
      <span>第 {{ model.page }} / {{ pages }} 页</span><button class="secondary" :disabled="model.busy || model.page === 1" @click="page(-1)">上一页</button><button class="secondary" :disabled="model.busy || model.page >= pages" @click="page(1)">下一页</button>
    </div>
    <div v-if="model.selecting" class="dialog-actions">
      <button v-if="model.job" class="secondary" :disabled="model.busy" @click="run(async () => { model.selecting = false; model.page = 1; await loadJob() })">返回上批结果</button>
      <button class="primary" :disabled="model.busy || !model.selected.size || !album || album === '1000'" @click="start">上传所选 {{ model.selected.size }} 个文件</button>
    </div>
    <template v-else-if="model.job && !working">
      <div v-if="!model.confirming" class="dialog-actions">
        <button class="secondary" :disabled="model.busy" @click="run(loadFiles)">选择下一批</button>
        <button v-if="model.job.counts.uploaded" class="secondary" :disabled="model.busy" @click="verify">重新核对云端</button>
        <button v-if="model.job.eligible" class="primary" :disabled="model.busy" @click="model.confirming = true">回收已确认的 {{ model.job.eligible }} 张图片</button>
      </div>
    </template>
  </dialog>
</template>

<style scoped>
@reference '../app/assets/main.css';

.batch-dialog { width: min(740px, calc(100% - 32px)); }
.batch-dialog > .section-heading { @apply mb-3.5; }
.batch-dialog h2, .batch-progress { overflow-wrap: anywhere; }
.batch-tools, .batch-progress { @apply my-3.5; }
.batch-controls { @apply my-3 flex flex-wrap gap-2; }
.batch-recycle-prompt { @apply my-4 rounded-xl bg-soft p-4; }
.batch-recycle-prompt h3 { @apply mb-2 text-base; }
.batch-recycle-prompt p { @apply mt-2 text-sm; }
.batch-list { @apply m-0 max-h-[min(42vh,460px)] list-none overflow-auto p-0; }
.batch-list li { @apply px-1 py-2.5; border-top: 1px solid var(--color-soft); }
.batch-list label, .batch-result { @apply grid min-h-[30px] items-center gap-2.5; }
.batch-list label { @apply grid-cols-[auto_auto_minmax(0,1fr)_auto]; }
.batch-result { @apply grid-cols-[minmax(0,1fr)_auto]; }
.batch-result small { @apply col-span-full; }
.batch-list span, .batch-result small { overflow-wrap: anywhere; }
.batch-dialog .notice { @apply my-3; }
</style>
