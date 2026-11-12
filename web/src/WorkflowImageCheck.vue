<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, watch } from 'vue'
import { api } from './api'
import Icon from './Icon.vue'

type Source = { id: string; path: string; albums: { id: string; name: string }[]; available: boolean }
type Cache = { phase: string; running: boolean; baselines: number; cached: number; prepared: number; done: number; total: number; error: string }
type Settings = { enabled: boolean; roots: string[]; cache: Cache }
const props = defineProps<{ connection: string; sources: Source[] }>()
const emit = defineEmits<{ refresh: [] }>()
const model = reactive({ enabled: false, roots: new Set<string>(), saved: null as Settings | null,
  loading: true, busy: false, error: '', note: '' })
const dirty = computed(() => !!model.saved && (model.enabled !== model.saved.enabled
  || [...model.roots].sort().join(',') !== [...model.saved.roots].sort().join(',')))
const cacheLabel = computed(() => {
  const saved = model.saved
  if (dirty.value) return '设置更改尚未保存'
  if (!saved?.enabled) return '已关闭'
  const cache = saved.cache
  if (cache.phase === 'indexing') return `准备缓存 · 已读取 ${cache.baselines} 张 · 复用 ${cache.cached} 张 · 新计算 ${cache.prepared} 张`
  if (cache.phase === 'comparing') return `正在检查新图 · ${cache.done} / ${cache.total}`
  if (cache.phase === 'completed') return `缓存已就绪 · ${cache.baselines} 张参考图片`
  if (cache.phase === 'unbound') return '所选目录已解除绑定，请重新选择'
  if (cache.phase === 'failed') return '缓存准备失败'
  return '等待目录索引或当前文件操作完成'
})
let timer: ReturnType<typeof setTimeout>
let disposed = false
let revision = 0
const reads = new AbortController()

async function load(initial = false) {
  clearTimeout(timer)
  if (model.busy || disposed) return
  const generation = ++revision
  const fill = initial || model.saved === null
  try {
    const result = await api<Settings>(`/dedup/automatic?${new URLSearchParams({ connection: props.connection })}`, undefined, 'GET', reads.signal)
    if (disposed || generation !== revision) return
    model.saved = result
    if (fill) {
      model.error = ''
      model.enabled = result.enabled
      model.roots = new Set(result.roots.filter(id => props.sources.some(source => source.id === id)))
    }
  } catch (error) { if (!disposed && generation === revision && (error as Error).name !== 'AbortError') model.error = (error as Error).message }
  finally {
    model.loading = false
    if (!disposed && generation === revision) timer = setTimeout(() => void load(), model.saved?.cache.running ? 3000 : 10000)
  }
}
async function save() {
  ++revision; clearTimeout(timer)
  model.busy = true; model.error = ''; model.note = ''
  try {
    model.saved = await api<Settings>('/dedup/automatic', { connection: props.connection, enabled: model.enabled, roots: [...model.roots] })
    model.note = model.enabled ? `已保存，工作流只比对所选 ${model.roots.size} 个目录` : '已关闭工作流自动检查，图片缓存保留'
  } catch (error) { model.error = (error as Error).message }
  finally { model.busy = false; if (!disposed) timer = setTimeout(() => void load(), 1000) }
}
async function refreshCache() {
  ++revision; clearTimeout(timer)
  model.busy = true; model.error = ''; model.note = ''
  try {
    await api('/dedup/automatic/refresh', { connection: props.connection })
    model.note = '已请求更新所选目录缓存，未变化的图片继续复用特征'
  } catch (error) { model.error = (error as Error).message }
  finally { model.busy = false; if (!disposed) timer = setTimeout(() => void load(), 1000) }
}
onMounted(() => void load(true))
watch(() => props.sources, sources => {
  model.roots = new Set([...model.roots].filter(id => sources.some(source => source.id === id)))
})
onUnmounted(() => { disposed = true; revision++; clearTimeout(timer); reads.abort() })
</script>

<template>
  <section class="workflow-image-check" :aria-busy="model.loading">
    <div class="automatic-heading">
      <label class="automatic-toggle"><Icon name="workflow" :size="21" /><strong>工作流自动检查</strong><input v-model="model.enabled" type="checkbox" :disabled="model.loading || model.busy" /></label>
      <button class="primary" :disabled="model.loading || model.busy || !dirty || model.enabled && !model.roots.size" @click="save">{{ model.busy ? '请稍候…' : '保存设置' }}</button>
    </div>
    <template v-if="model.enabled">
      <div class="source-heading"><span class="muted">检查目录 · 已选 {{ model.roots.size }} 个</span><button class="text-button" :disabled="model.busy" @click="emit('refresh')">刷新列表</button></div>
      <div class="automatic-sources">
        <label v-for="source in sources" :key="source.id" class="automatic-source">
          <input v-model="model.roots" type="checkbox" :value="source.id" :disabled="model.loading || model.busy || !source.available && !model.roots.has(source.id)" />
          <span class="min-w-0"><strong class="block truncate" :title="source.albums.map(album => album.name).join('、')">{{ source.albums.map(album => album.name).join('、') }}</strong><span class="block truncate text-muted" :title="source.path">{{ source.path }}</span></span>
          <span v-if="!source.available" class="shrink-0 text-sm text-danger">不可访问</span>
        </label>
        <p v-if="!sources.length" class="muted py-4">还没有绑定目录，请先到小米云相册绑定本地文件夹。</p>
      </div>
    </template>
    <div class="cache-status"><span class="muted" role="status">{{ model.loading ? '正在读取设置…' : cacheLabel }}</span><button v-if="model.saved?.enabled" class="text-button" :disabled="model.busy || dirty || model.saved.cache.running" @click="refreshCache"><Icon name="refresh" :size="15" />更新缓存</button></div>
    <p v-if="model.note" class="muted mt-2" role="status">{{ model.note }}</p>
    <p v-if="model.error || model.saved?.cache.error" class="notice error mt-3 mb-0" role="alert">{{ model.error || model.saved?.cache.error }}</p>
  </section>
</template>

<style scoped>
@reference '../app/assets/main.css';
.workflow-image-check { @apply mb-5 rounded-panel border border-solid border-hairline bg-canvas p-5; }
.automatic-heading { @apply flex items-center justify-between gap-4; }
.automatic-toggle { @apply min-h-11 flex-row items-center gap-3 text-base; }
.automatic-toggle input { @apply ml-2; }
.source-heading { @apply mt-3 flex items-center justify-between gap-3 border-t border-solid border-hairline pt-2; border-width: 1px 0 0; }
.automatic-sources { @apply max-h-80 overflow-y-auto; }
.automatic-source { @apply min-h-16 flex-row items-center gap-3 border-b border-solid border-soft py-3; border-width: 0 0 1px; }
.automatic-source input[type=checkbox] { @apply size-5 appearance-auto rounded-sm accent-primary; }
.automatic-source input::after { display: none; }
.cache-status { @apply mt-3 flex items-center justify-between gap-3; }
@media (max-width: 600px) {
  .workflow-image-check { @apply p-3; }
  .automatic-toggle { @apply gap-2 text-sm; }
  .automatic-toggle input { @apply ml-0; }
  .automatic-heading .primary { @apply px-3 text-sm; }
}
</style>
