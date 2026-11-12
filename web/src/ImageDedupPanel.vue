<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from '#imports'
import { api, bytes } from './api'
import { queryPage, queryText } from './routeState'
import { useBeforeUnload } from './useBeforeUnload'
import Icon from './Icon.vue'

type Source = { id: string; path: string; albums: { id: string; name: string }[]; available: boolean }
type Job = { id: string; roots: Source[]; distance: number; running: boolean; phase: string; done: number; total: number; errors: number; groups: number; matched: number; error: string; current: string }
type Group = { id: number; count: number; exact: boolean; covers: number[] }
type Picture = { id: number; root_id: string; path: string; size: number; width: number; height: number; group_id: number; removed: boolean; error: string }
type Score = { ssim?: number; distance?: number; exact?: boolean; error: string }
type Plan = { token: string; file_id: number; name: string; path: string; size: number; root: Source; local_done: boolean; attempted: boolean; done: boolean; error: string;
  cloud: { id: string; album: string; album_name: string; done: boolean; error: string }[] }
type Preview = { state: string; items: Plan[]; pages: number; album: string; error: string }
const emit = defineEmits<{ message: [text: string] }>()
const route = useRoute()
const router = useRouter()
const model = reactive({ initialized: false, account: null as { connection: string; label: string } | null,
  sources: [] as Source[], roots: new Set<string>(), distance: 10, foldersOpen: true, job: null as Job | null,
  groups: [] as Group[], groupsPage: 1, groupTotal: 0, group: 0, items: [] as Picture[], page: 1, total: 0,
  reference: null as Picture | null, scores: {} as Record<number, Score>, scoring: false,
  selected: new Map<number, Picture>(), loading: false, busy: false, error: '', note: '',
  preview: null as Preview | null, pending: [] as Plan[], completed: 0, executing: false,
  review: null as Picture | null, broken: new Set<number>(), failures: [] as { path: string; error: string }[], errorPage: 1 })
const confirmDialog = ref<HTMLDialogElement>()
const reviewDialog = ref<HTMLDialogElement>()
const selectedSize = computed(() => [...model.selected.values()].reduce((sum, item) => sum + item.size, 0))
const previewCloudCount = computed(() => new Set(model.preview?.items.flatMap(plan => plan.cloud.map(item => item.id)) ?? []).size)
const blocked = computed(() => model.busy || model.loading || !!model.job?.running || model.preview?.state === 'matching')
const phaseLabels: Record<string, string> = { scanning: '读取图片', grouping: '正在分组', completed: '扫描完成', cancelled: '已停止', interrupted: '扫描中断', failed: '扫描失败' }
const rootNames = computed(() => new Map([...(model.job?.roots ?? []), ...model.sources].map(root => [root.id, root])))
useBeforeUnload(() => model.executing || model.selected.size > 0)
let timer: ReturnType<typeof setTimeout>
let disposed = false
let listedRun = ''
let revision = 0
let scoreRevision = 0
let reads = new AbortController()
let scoreReads = new AbortController()

function params(values: Record<string, string | number> = {}) {
  return new URLSearchParams({ connection: model.account!.connection, ...Object.fromEntries(Object.entries(values).map(([key, value]) => [key, String(value)])) })
}
function body(values = {}) { return { connection: model.account!.connection, ...values } }
function imageUrl(id: number, original = false) {
  return `/api/dedup/files/${id}/${original ? 'original' : 'thumbnail'}?${params({ run: model.job!.id })}`
}
function name(item: Picture) { return item.path.split('/').pop() || item.path }
function sourceName(item: Picture) { return rootNames.value.get(item.root_id)?.albums.map(album => album.name).join('、') || '' }
function fullPath(item: Picture) { return `${rootNames.value.get(item.root_id)?.path ?? ''}/${item.path}` }
function toggle(item: Picture) {
  if (model.busy || item.removed) return
  if (model.selected.has(item.id)) model.selected.delete(item.id)
  else if (model.selected.size >= 200) model.error = '每次最多选择 200 张，请先处理当前选择'
  else model.selected.set(item.id, item)
}

async function refreshStatus() {
  if (!model.account || disposed || model.executing) return
  const status = await api<{ job: Job | null; preview: Preview | null; pending: Plan[] }>(`/dedup/status?${params()}`, undefined, 'GET', reads.signal)
  if (disposed) return
  if (model.job && status.job?.id !== model.job.id) {
    model.selected.clear(); model.reference = null; model.items = []; model.groups = []; listedRun = ''
  }
  model.job = status.job; model.preview = status.preview; model.pending = status.pending
  if (status.job?.phase === 'completed' && listedRun !== status.job.id) await loadRoute()
}
async function poll() {
  clearTimeout(timer)
  try { await refreshStatus() }
  catch (error) { if (!disposed && (error as Error).name !== 'AbortError') model.error = (error as Error).message }
  finally { if (!disposed) timer = setTimeout(() => void poll(), model.job?.running || model.preview?.state === 'matching' ? 1500 : 10000) }
}
async function refreshSources() {
  const result = await api<{ items: Source[] }>(`/dedup/sources?${params()}`, undefined, 'GET', reads.signal)
  model.sources = result.items
  model.roots = new Set([...model.roots].filter(id => model.sources.some(root => root.id === id && root.available)))
}
async function start() {
  model.busy = true; model.error = ''; model.note = ''
  try {
    const job = await api<Job>('/dedup/scan', body({ roots: [...model.roots], distance: model.distance }))
    model.job = job; model.foldersOpen = false; model.selected.clear(); model.groups = []; model.items = []
    model.reference = null; model.group = 0; listedRun = ''; model.failures = []; model.broken.clear()
    await router.replace({ path: '/dedup' })
  } catch (error) { model.error = (error as Error).message }
  finally { model.busy = false; clearTimeout(timer); timer = setTimeout(() => void poll(), 1000) }
}
async function cancelScan() {
  try { await api('/dedup/cancel', body()); model.note = '正在停止，当前图片处理结束后退出' }
  catch (error) { model.error = (error as Error).message }
}
function navigate(group: number, page = 1, groupsPage = model.groupsPage) {
  return router.push({ path: '/dedup', query: { group: group || undefined, page: page > 1 ? String(page) : undefined, groupsPage: groupsPage > 1 ? String(groupsPage) : undefined } })
}
async function loadRoute() {
  if (!model.account || model.job?.phase !== 'completed' || disposed || !route.path.startsWith('/dedup')) return
  reads.abort(); reads = new AbortController()
  scoreReads.abort(); ++scoreRevision
  const generation = ++revision
  const signal = reads.signal
  const run = model.job.id
  model.loading = true
  try {
    const groupsPage = queryPage(route.query.groupsPage)
    const groups = await api<{ items: Group[]; total: number }>(`/dedup/groups?${params({ run, page: groupsPage })}`, undefined, 'GET', signal)
    if (generation !== revision || disposed) return
    const lastGroupsPage = Math.max(1, Math.ceil(groups.total / 20))
    if (groupsPage > lastGroupsPage) {
      await router.replace({ path: '/dedup', query: { groupsPage: lastGroupsPage > 1 ? String(lastGroupsPage) : undefined } })
      return
    }
    model.groups = groups.items; model.groupTotal = groups.total; model.groupsPage = groupsPage; listedRun = run
    const requested = Number(queryText(route.query.group))
    const group = groups.items.some(item => item.id === requested) ? requested : groups.items[0]?.id ?? 0
    const page = group === requested ? queryPage(route.query.page) : 1
    if (!group) { model.items = []; model.group = 0; model.reference = null; return }
    const result = await api<{ items: Picture[]; total: number }>(`/dedup/groups/${group}?${params({ run, page })}`, undefined, 'GET', signal)
    if (generation !== revision || disposed) return
    const lastPage = Math.max(1, Math.ceil(result.total / 40))
    if (page > lastPage) {
      await router.replace({ path: '/dedup', query: { ...route.query, group: String(group), page: lastPage > 1 ? String(lastPage) : undefined } })
      return
    }
    if (model.group !== group || model.reference?.removed) model.reference = null
    model.items = result.items; model.total = result.total; model.group = group; model.page = page; model.scores = {}
    model.reference ??= result.items[0] ?? null
    void score()
  } catch (error) { if (!disposed && (error as Error).name !== 'AbortError') model.error = (error as Error).message }
  finally { if (generation === revision) model.loading = false }
}
async function score(reference = model.reference) {
  scoreReads.abort(); scoreReads = new AbortController()
  const generation = ++scoreRevision
  model.reference = reference; model.scores = {}
  if (!reference || !model.items.length) { model.scoring = false; return }
  model.scoring = true
  try {
    const ids = model.items.map(item => item.id)
    for (let offset = 0; offset < ids.length; offset += 4) {
      const result = await api<Record<number, Score>>('/dedup/scores', body({ run: model.job!.id, reference: reference.id, ids: ids.slice(offset, offset + 4) }), 'POST', scoreReads.signal)
      if (generation !== scoreRevision || disposed) return
      Object.assign(model.scores, result)
    }
  } catch (error) { if (generation === scoreRevision && !disposed && (error as Error).name !== 'AbortError') model.error = (error as Error).message }
  finally { if (generation === scoreRevision) model.scoring = false }
}
async function showFailures(page = 1) {
  try {
    const result = await api<{ items: typeof model.failures }>(`/dedup/errors?${params({ run: model.job!.id, page })}`, undefined, 'GET', reads.signal)
    model.failures = result.items; model.errorPage = page
  } catch (error) { if (!disposed && (error as Error).name !== 'AbortError') model.error = (error as Error).message }
}
async function openReview(item: Picture) {
  model.review = item
  await nextTick()
  if (!reviewDialog.value?.open) reviewDialog.value?.showModal()
}
function nextReview(delta: number) {
  const index = model.items.findIndex(item => item.id === model.review?.id)
  const item = model.items[index + delta]
  if (item) model.review = item
}

async function prepare() {
  model.busy = true; model.error = ''; model.note = ''
  try {
    model.preview = await api<Preview>('/dedup/preview', body({ run: model.job!.id, ids: [...model.selected.keys()] }))
    await nextTick(); confirmDialog.value?.showModal()
  } catch (error) { model.error = (error as Error).message }
  finally { model.busy = false }
}
async function closePreview() {
  if (model.executing) return
  if (model.preview?.state === 'matching') {
    try { await api('/dedup/preview/cancel', body()) }
    catch (error) { model.error = (error as Error).message; return }
  }
  confirmDialog.value?.close()
}
async function execute(plans: Plan[]) {
  if (model.busy || !plans.length) return
  model.busy = model.executing = true; model.error = ''; model.completed = 0
  let moved = 0
  try {
    for (const plan of plans) {
      try {
        const wasLocalDone = plan.local_done
        const result = await api<Plan>('/dedup/recycle', body({ token: plan.token }))
        Object.assign(plan, result)
        if (result.local_done) {
          if (!wasLocalDone) moved++
          model.selected.delete(result.file_id)
          for (const item of model.items) if (item.id === result.file_id) item.removed = true
          if (model.reference?.id === result.file_id) model.reference = null
        }
      } catch (error) { plan.error = (error as Error).message }
      model.completed++
    }
    const remaining = plans.filter(plan => !plan.done).length
    model.note = `已处理 ${plans.length} 项，本次本地回收 ${moved} 张${remaining ? `；${remaining} 项未完成，可继续处理` : '，云端联动已完成'}`
    emit('message', remaining ? `${remaining} 项回收未完成，请查看结果` : '所选图片回收已完成')
  } finally {
    model.busy = model.executing = false
    if (!disposed) {
      try { await refreshStatus(); await loadRoute() }
      catch (error) { if (!disposed && (error as Error).name !== 'AbortError') model.error = (error as Error).message }
    }
  }
}
async function dismiss(plan: Plan) {
  model.busy = true
  try { await api('/dedup/recycle/dismiss', body({ token: plan.token })); await refreshStatus() }
  catch (error) { model.error = (error as Error).message }
  finally { model.busy = false }
}

watch(() => route.fullPath, () => { if (model.initialized) void loadRoute() })
onMounted(async () => {
  model.loading = true
  try {
    const result = await api<{ account: typeof model.account }>('/xiaomi/account', undefined, 'GET', reads.signal)
    model.account = result.account
    if (model.account) {
      await refreshStatus()
      await refreshSources()
      model.roots = new Set(model.job?.roots.map(root => root.id).filter(id => model.sources.some(root => root.id === id && root.available)) ?? [])
      model.distance = model.job?.distance ?? 10
      model.foldersOpen = !model.job
    }
  } catch (error) { if (!disposed && (error as Error).name !== 'AbortError') model.error = (error as Error).message }
  finally { model.initialized = true; model.loading = false; if (model.account && !disposed) void poll() }
})
onUnmounted(() => { disposed = true; clearTimeout(timer); reads.abort(); scoreReads.abort(); revision++; scoreRevision++ })
</script>

<template>
  <div class="dedup-page">
    <p v-if="model.error" class="notice error" role="alert">{{ model.error }}<button class="text-button" @click="model.error = ''">关闭</button></p>
    <div v-if="!model.initialized" class="empty-list" role="status">正在读取绑定目录…</div>
    <div v-else-if="!model.account" class="empty-list tall"><Icon name="cloud" :size="36" /><h2>先连接小米云相册</h2><button class="primary mt-4" @click="router.push('/xiaomi')">连接小米云</button></div>
    <template v-else>
      <section class="dedup-setup">
        <div class="setup-toolbar">
          <button class="text-button min-w-0" :aria-expanded="model.foldersOpen" @click="model.foldersOpen = !model.foldersOpen"><Icon name="folder" />选择目录 · {{ model.roots.size }}<Icon name="down" :size="15" /></button>
          <label class="distance-control">分组范围<input v-model.number="model.distance" type="number" min="0" max="24" step="1" :disabled="blocked" /></label>
          <button v-if="model.job?.running" class="secondary" @click="cancelScan"><Icon name="close" :size="16" />停止扫描</button>
          <button v-else class="primary" :disabled="blocked || !model.roots.size || !Number.isInteger(model.distance) || model.distance < 0 || model.distance > 24" @click="start"><Icon name="search" :size="17" />{{ model.job ? '重新扫描' : '开始比对' }}</button>
        </div>
        <div v-if="model.foldersOpen" class="source-list">
          <div class="flex items-center justify-between gap-3"><span class="muted">{{ model.account.label }} · 已绑定目录</span><button class="text-button" :disabled="blocked" @click="refreshSources().catch(error => model.error = error.message)">刷新目录</button></div>
          <label v-for="source in model.sources" :key="source.id" class="source-row">
            <input v-model="model.roots" type="checkbox" :value="source.id" :disabled="blocked || !source.available" />
            <span class="min-w-0"><strong class="block truncate" :title="source.albums.map(album => album.name).join('、')">{{ source.albums.map(album => album.name).join('、') }}</strong><span class="block truncate text-muted" :title="source.path">{{ source.path }}</span></span>
            <span v-if="!source.available" class="text-danger whitespace-nowrap">目录不可访问</span>
          </label>
          <div v-if="!model.sources.length" class="empty-list"><p>还没有绑定目录</p><button class="text-button" @click="router.push('/xiaomi')">去相册绑定本地文件夹</button></div>
          <p class="muted mt-3">同时查找所选目录及子目录内、不同目录间的重复与相似图片。范围越大，分组越宽松。</p>
        </div>
      </section>

      <div v-if="model.job" class="scan-strip" role="status">
        <span class="inline-flex items-center gap-2"><Icon :name="model.job.running ? 'loader' : 'check'" :size="17" />{{ phaseLabels[model.job.phase] }}</span>
        <span>{{ model.job.done }} 张图片</span><span v-if="!model.job.running">{{ model.job.groups }} 组 · {{ model.job.matched }} 张命中</span>
        <button v-if="model.job.errors" class="text-button danger-text" @click="showFailures()">{{ model.job.errors }} 张读取失败</button>
        <span v-if="model.job.current" class="min-w-0 truncate text-muted">{{ model.job.current }}</span>
        <progress v-if="model.job.running" aria-label="图片扫描进行中" />
      </div>
      <p v-if="model.job?.error" class="notice error" role="alert">{{ model.job.error }}</p>
      <section v-if="model.failures.length" class="failures-panel">
        <div class="section-heading"><h2>读取失败</h2><button class="text-button" @click="model.failures = []">收起</button></div>
        <p v-for="(failure, index) in model.failures" :key="index" class="mt-2 text-sm break-all"><strong>{{ failure.path }}</strong> · {{ failure.error }}</p>
        <div class="pagination"><span>第 {{ model.errorPage }} 页</span><button class="secondary" :disabled="model.errorPage === 1" @click="showFailures(model.errorPage - 1)">上一页</button><button class="secondary" :disabled="model.errorPage * 40 >= (model.job?.errors ?? 0)" @click="showFailures(model.errorPage + 1)">下一页</button></div>
      </section>
      <p v-if="model.note" class="notice" role="status">{{ model.note }}</p>
      <button v-if="model.preview?.state === 'ready' && model.preview.items.some(item => !item.done)" class="secondary mb-4" :disabled="model.busy" @click="confirmDialog?.showModal()">继续核对待回收清单</button>

      <div v-if="model.job?.phase === 'completed'" class="comparison-layout" :aria-busy="model.loading">
        <aside class="group-list" aria-label="相似图片分组">
          <div class="group-heading"><strong>{{ model.groupTotal }} 个分组</strong><span v-if="model.loading" class="muted" role="status">读取中…</span></div>
          <select class="mobile-group-picker" aria-label="选择图片分组" :value="model.group" :disabled="model.busy" @change="navigate(Number(($event.target as HTMLSelectElement).value))"><option v-if="!model.groups.length" value="0">没有分组</option><option v-for="group in model.groups" :key="group.id" :value="group.id">组 {{ group.id }} · {{ group.count }} 张 · {{ group.exact ? '完全重复' : '视觉相似' }}</option></select>
          <button v-for="group in model.groups" :key="group.id" class="group-button" :class="{ active: model.group === group.id }" :disabled="model.busy" :aria-current="model.group === group.id ? 'true' : undefined" @click="navigate(group.id)">
            <span class="group-covers"><img v-for="id in group.covers" :key="id" :src="imageUrl(id)" alt="" loading="lazy" /></span>
            <span class="flex items-center justify-between gap-2"><strong>组 {{ group.id }} · {{ group.count }} 张</strong><span class="badge">{{ group.exact ? '完全重复' : '视觉相似' }}</span></span>
          </button>
          <div v-if="!model.groups.length" class="empty-list"><p>{{ model.groupTotal ? '此页没有分组' : '没有找到重复或相似图片' }}</p></div>
          <div v-if="model.groupTotal > 20" class="group-pages"><button class="icon-button" aria-label="上一页分组" :disabled="model.groupsPage === 1 || blocked" @click="navigate(0, 1, model.groupsPage - 1)"><Icon name="chevron" class="rotate-180" /></button><span>{{ model.groupsPage }} / {{ Math.ceil(model.groupTotal / 20) }}</span><button class="icon-button" aria-label="下一页分组" :disabled="model.groupsPage * 20 >= model.groupTotal || blocked" @click="navigate(0, 1, model.groupsPage + 1)"><Icon name="chevron" /></button></div>
        </aside>
        <section class="group-detail">
          <div v-if="model.group" class="detail-heading"><h2>组 {{ model.group }}<span class="muted ml-3">{{ model.total }} 张</span></h2><span class="muted">{{ model.scoring ? '正在计算相似度…' : '手动勾选要回收的图片' }}</span></div>
          <p v-if="model.reference" class="reference-line"><span class="truncate" :title="name(model.reference)">参考图：{{ name(model.reference) }}</span><span class="shrink-0">SSIM 为与参考图的直接比较</span></p>
          <div class="picture-grid">
            <article v-for="item in model.items" :key="item.id" class="picture-card" :class="{ selected: model.selected.has(item.id), removed: item.removed }">
              <button class="picture-preview" :disabled="item.removed" :aria-label="`查看原图：${name(item)}`" @click="openReview(item)"><img v-if="!model.broken.has(item.id)" :src="imageUrl(item.id)" :alt="name(item)" loading="lazy" @error="model.broken.add(item.id)" /><span v-else class="text-muted">预览不可用，请重新扫描</span></button>
              <div class="picture-info">
                <label class="picture-select"><input type="checkbox" :checked="model.selected.has(item.id)" :disabled="model.busy || item.removed" @change="toggle(item)" /><strong class="truncate" :title="name(item)">{{ name(item) }}</strong></label>
                <span class="block truncate text-sm text-muted" :title="fullPath(item)">{{ sourceName(item) }} · {{ item.path }}</span>
                <div class="picture-metrics"><span>{{ item.width }} × {{ item.height }}</span><span>{{ bytes(item.size) }}</span><span v-if="/\.(gif|webp|avif)$/i.test(item.path)" title="多帧图片仅分析首帧">首帧</span></div>
                <div class="score-line"><span v-if="item.removed" class="text-success">本地已回收</span><span v-else-if="model.scores[item.id]?.error" class="text-danger truncate" :title="model.scores[item.id]?.error">{{ model.scores[item.id]?.error }}</span><span v-else-if="model.reference?.id === item.id">参考图</span><span v-else-if="model.scores[item.id]?.ssim !== undefined">{{ model.scores[item.id]?.exact ? '完全重复' : `SSIM ${model.scores[item.id]?.ssim?.toFixed(5)}` }} · 距离 {{ model.scores[item.id]?.distance }}</span><span v-else class="text-muted">{{ model.scoring ? '计算中…' : '尚未计算' }}</span><button class="text-button" :disabled="model.busy || item.removed || model.reference?.id === item.id" @click="score(item)">设为参考</button></div>
              </div>
            </article>
          </div>
          <div v-if="model.group && !model.items.length" class="empty-list"><p>此分组的图片已移走或当前页为空</p></div>
          <div v-if="model.total > 40" class="pagination"><span>第 {{ model.page }} / {{ Math.ceil(model.total / 40) }} 页</span><button class="secondary" :disabled="model.page === 1 || blocked" @click="navigate(model.group, model.page - 1)">上一页</button><button class="secondary" :disabled="model.page * 40 >= model.total || blocked" @click="navigate(model.group, model.page + 1)">下一页</button></div>
        </section>
      </div>

      <section v-if="model.pending.length" class="pending-panel">
        <div class="section-heading"><h2>未完成回收 · {{ model.pending.length }} 项</h2><button class="secondary" :disabled="model.busy" @click="execute(model.pending)">继续处理</button></div>
        <div v-for="plan in model.pending" :key="plan.token" class="pending-row"><div class="min-w-0"><strong class="block truncate" :title="plan.path">{{ plan.name }}</strong><p class="text-sm text-muted">{{ plan.local_done ? '本地已回收' : '本地未回收' }} · 云端 {{ plan.cloud.filter(item => item.done).length }} / {{ plan.cloud.length }}</p><p v-if="plan.error" class="text-sm text-danger">{{ plan.error }}</p><p v-for="item in plan.cloud.filter(item => item.error)" :key="item.id" class="text-sm text-danger">{{ item.album_name }} · {{ item.id }}：{{ item.error }}</p></div><div class="flex shrink-0 gap-3"><button class="text-button" :disabled="model.busy" @click="execute([plan])">重试</button><button class="text-button" :disabled="model.busy" @click="dismiss(plan)">放弃后续操作</button></div></div>
      </section>
      <div v-if="model.selected.size" class="selection-bar"><span class="whitespace-nowrap">已选 {{ model.selected.size }} 张 · {{ bytes(selectedSize) }}</span><div class="flex gap-3"><button class="text-button" :disabled="model.busy" @click="model.selected.clear()">清空</button><button class="danger" :disabled="blocked" @click="prepare"><Icon name="trash" :size="17" />核对回收清单</button></div></div>
    </template>

    <dialog ref="confirmDialog" class="task-dialog dedup-confirm" aria-labelledby="dedup-confirm-title" @cancel="(event: Event) => { event.preventDefault(); if (!model.executing) void closePreview() }">
      <div class="section-heading"><h2 id="dedup-confirm-title">回收清单</h2><button class="icon-button" aria-label="关闭回收清单" :disabled="model.executing" @click="closePreview"><Icon name="close" /></button></div>
      <template v-if="model.preview">
        <p v-if="model.preview.state === 'matching'" class="muted my-4" role="status">正在匹配 {{ model.preview.album }} · 已读取 {{ model.preview.pages }} 页</p>
        <p v-if="model.preview.error" class="notice error mt-4" role="alert">{{ model.preview.error }}</p>
        <template v-if="model.preview.state === 'ready' || model.preview.state === 'completed'">
          <p class="muted my-4">先将本地文件移入回收站，再回收绑定相册中所有同名同大小的云端图片。本地保留 15 天，云端可在小米回收站恢复。</p>
          <div v-for="plan in model.preview.items" :key="plan.token" class="confirmation-row"><div class="min-w-0"><strong class="block truncate" :title="plan.path">{{ plan.name }}</strong><span class="block truncate text-sm text-muted" :title="`${plan.root.path}/${plan.path}`">{{ plan.root.path }}/{{ plan.path }}</span><span class="text-sm">{{ bytes(plan.size) }} · {{ plan.local_done ? '本地已回收' : '本地待回收' }}</span><p v-if="!plan.cloud.length" class="text-sm text-muted">云端未找到同名同大小图片，仅回收本地</p><p v-for="item in plan.cloud" :key="item.id" class="text-sm text-muted">{{ item.album_name }} · 编号 {{ item.id }} · {{ item.done ? '已回收' : '待回收' }}<span v-if="item.error" class="text-danger"> · {{ item.error }}</span></p><p v-if="plan.error" class="text-sm text-danger">{{ plan.error }}</p></div><Icon v-if="plan.done" name="check" class="text-success" /></div>
          <div class="confirmation-actions"><span class="muted" role="status">{{ model.executing ? `正在处理 ${model.completed} / ${model.preview.items.length}` : `${model.preview.items.length} 张本地 · ${previewCloudCount} 张云端` }}</span><button class="danger" :disabled="model.busy || model.preview.items.every(plan => plan.done)" @click="execute(model.preview!.items.filter(plan => !plan.done))">{{ model.executing ? '正在回收…' : '确认回收所选图片' }}</button></div>
        </template>
        <div v-else class="dialog-actions mt-4"><button class="secondary" @click="closePreview">{{ model.preview.state === 'matching' ? '取消匹配' : '关闭' }}</button></div>
      </template>
    </dialog>

    <dialog ref="reviewDialog" class="task-dialog dedup-review" aria-labelledby="dedup-review-title" @keydown.left.prevent="nextReview(-1)" @keydown.right.prevent="nextReview(1)">
      <div class="section-heading"><h2 id="dedup-review-title">原图对照</h2><div class="flex shrink-0 gap-2"><button class="icon-button" aria-label="上一张" :disabled="model.items.findIndex(item => item.id === model.review?.id) <= 0" @click="nextReview(-1)"><Icon name="chevron" class="rotate-180" /></button><button class="icon-button" aria-label="下一张" :disabled="model.items.findIndex(item => item.id === model.review?.id) >= model.items.length - 1" @click="nextReview(1)"><Icon name="chevron" /></button><button class="icon-button" aria-label="关闭原图对照" @click="reviewDialog?.close()"><Icon name="close" /></button></div></div>
      <div v-if="model.review" class="review-pair"><figure v-if="model.reference && model.reference.id !== model.review.id"><figcaption>参考图 · {{ name(model.reference) }}</figcaption><img :src="imageUrl(model.reference.id, true)" :alt="name(model.reference)" /><span class="muted">{{ model.reference.width }} × {{ model.reference.height }} · {{ bytes(model.reference.size) }}</span></figure><figure><figcaption>{{ name(model.review) }}</figcaption><img :src="imageUrl(model.review.id, true)" :alt="name(model.review)" /><div class="flex items-center justify-between gap-3"><span class="muted">{{ model.review.width }} × {{ model.review.height }} · {{ bytes(model.review.size) }}</span><button :class="model.selected.has(model.review.id) ? 'danger' : 'secondary'" :disabled="model.busy || model.review.removed" @click="toggle(model.review)">{{ model.selected.has(model.review.id) ? '已选回收' : '选择回收' }}</button></div></figure></div>
    </dialog>
  </div>
</template>

<style scoped>
@reference '../app/assets/main.css';
.dedup-setup, .failures-panel, .pending-panel { @apply mb-4 rounded-panel bg-canvas p-5; }
.setup-toolbar { @apply flex items-center justify-between gap-4; }
.distance-control { @apply ml-auto flex-row items-center gap-2 whitespace-nowrap; }
.distance-control input { @apply w-18 py-2; }
.source-list { @apply mt-3 border-t border-solid border-hairline pt-2; border-width: 1px 0 0; }
.source-row { @apply flex-row items-center gap-3 border-b border-solid border-soft py-3; border-width: 0 0 1px; }
.source-row input[type=checkbox], .picture-select input[type=checkbox] { @apply size-5 appearance-auto rounded-sm accent-blue; }
.source-row input::after, .picture-select input::after { display: none; }
.scan-strip { @apply mb-5 flex min-w-0 flex-wrap items-center gap-x-5 gap-y-2 text-sm; }
.scan-strip progress { @apply w-full; }
.comparison-layout { @apply grid items-start gap-5; grid-template-columns: 260px minmax(0, 1fr); }
.group-list { @apply sticky top-5 min-w-0 overflow-y-auto rounded-panel bg-canvas p-3; max-height: calc(100dvh - 40px); }
.mobile-group-picker { display: none; }
.group-heading { @apply flex items-center justify-between gap-2 px-2 pb-3 text-sm; }
.group-button { @apply mb-2 block w-full rounded-lg border border-solid border-transparent p-2 text-left; }
.group-button.active { @apply border-blue bg-blue/5; }
.group-covers { @apply mb-2 flex h-16 gap-1 overflow-hidden rounded-md; }
.group-covers img { @apply min-w-0 flex-1 bg-parchment object-contain; }
.group-button strong { @apply text-sm; }
.group-pages { @apply mt-2 flex items-center justify-between gap-2 text-sm text-muted; }
.group-detail { @apply min-w-0; }
.detail-heading { @apply mb-2 flex items-center justify-between gap-3; }
.reference-line { @apply mb-4 flex min-w-0 items-center justify-between gap-3 text-sm text-muted; }
.picture-grid { @apply grid gap-4; grid-template-columns: repeat(auto-fill, minmax(min(100%, 270px), 1fr)); }
.picture-card { @apply min-w-0 overflow-hidden rounded-xl border-2 border-solid border-transparent bg-canvas; }
.picture-card.selected { @apply border-danger; }
.picture-card.removed { @apply opacity-50; }
.picture-preview { @apply grid w-full place-items-center bg-soft p-0; aspect-ratio: 4 / 3; }
.picture-preview img { @apply h-full max-h-80 w-full object-contain; }
.picture-info { @apply p-3; }
.picture-select { @apply mb-2 min-h-7 flex-row items-center gap-2.5; }
.picture-metrics { @apply mt-2 flex items-center gap-3 text-sm text-muted; }
.score-line { @apply mt-2 flex min-h-11 items-center justify-between gap-2 border-t border-solid border-soft pt-1 text-sm; border-width: 1px 0 0; }
.score-line .text-button { @apply shrink-0 text-sm; }
.selection-bar { @apply sticky bottom-0 z-10 mt-5 flex items-center justify-between gap-3 rounded-xl border border-solid border-hairline bg-canvas p-4 shadow-lg; }
.pending-panel { @apply mt-5; }
.pending-row, .confirmation-row { @apply flex items-start justify-between gap-4 border-b border-solid border-soft py-3; border-width: 0 0 1px; }
.dedup-confirm { width: min(800px, calc(100% - 24px)); }
.confirmation-actions { @apply sticky bottom-0 mt-4 flex items-center justify-between gap-3 bg-canvas pt-3; }
.dedup-review { width: min(1500px, calc(100% - 24px)); }
.review-pair { @apply mt-4 grid gap-5; grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr)); }
.review-pair figure { @apply m-0 flex min-w-0 flex-col gap-3; }
.review-pair figcaption { @apply truncate text-sm; }
.review-pair img { @apply h-[60vh] w-full bg-parchment object-contain; }
@media (max-width: 1200px) { .comparison-layout { grid-template-columns: 210px minmax(0, 1fr); } .reference-line { @apply flex-col items-start gap-1; } }
@media (max-width: 800px) {
  .comparison-layout { grid-template-columns: minmax(0, 1fr); }
  .group-list { @apply static block overflow-visible; max-height: none; }
  .mobile-group-picker { display: block; }
  .group-button { display: none; }
  .setup-toolbar { @apply gap-2; }
  .dedup-setup { @apply p-3; }
  .setup-toolbar > .text-button { @apply text-sm; }
  .distance-control { @apply gap-1 text-xs; }
  .distance-control input { @apply w-13 px-1.5; }
  .setup-toolbar > .primary, .setup-toolbar > .secondary { @apply gap-1 px-2.5 text-sm; }
  .detail-heading { @apply items-start; }
  .detail-heading > .muted { @apply text-right; }
  .selection-bar { @apply gap-2 p-3 text-sm; }
  .selection-bar .danger { @apply gap-1 px-2.5 text-sm; }
  .pending-row { @apply flex-col gap-1; }
  .confirmation-actions { @apply flex-col items-stretch; }
  .review-pair img { @apply h-[45vh]; }
}
</style>
