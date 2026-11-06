<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { api } from './api'
import Icon from './Icon.vue'
import type { CloudMedia, LocalFileState } from './xiaomiMedia'

type Binding = { path: string; updated: number; count: number; state: 'queued' | 'waiting' | 'scanning' | 'ready'; done: number; error: string; available: boolean; ready: boolean }
type Status = { binding: Binding | null; states: Record<string, LocalFileState> }
const props = defineProps<{ connection: string; album: string; items: CloudMedia[] }>()
const emit = defineEmits<{ status: [states: Record<string, LocalFileState>, bound: boolean] }>()
const dialog = ref<HTMLDialogElement>()
const model = reactive({ binding: null as Binding | null, path: '', busy: false, loading: false, error: '' })
const indexing = computed(() => !!model.binding && ['queued', 'waiting', 'scanning'].includes(model.binding.state))
const statusText = computed(() => {
  const info = model.binding
  if (!info) return '绑定本地文件夹'
  if (!info.available) return '目录离线或不可访问'
  if (info.state === 'waiting' || info.state === 'queued') return '等待下载和整理空闲'
  if (info.state === 'scanning') return `正在缓存 · ${info.done} 个文件`
  if (info.error) return info.error
  return info.updated ? `缓存 ${info.count} 个文件 · ${new Date(info.updated * 1000).toLocaleString('zh-CN')}` : '索引尚未建立'
})
let timer: ReturnType<typeof setTimeout>
let revision = 0
let disposed = false

async function load() {
  clearTimeout(timer)
  const generation = ++revision
  model.loading = true
  const items = props.items.map(({ id, name, size }) => ({ id, name, size }))
  const states: Record<string, LocalFileState> = {}
  try {
    let status: Status | undefined
    for (let offset = 0; offset < Math.max(1, items.length); offset += 2000) {
      status = await api<Status>('/xiaomi/local/status', { connection: props.connection, album: props.album, items: items.slice(offset, offset + 2000) })
      if (disposed || generation !== revision) return
      Object.assign(states, status.states)
    }
    model.binding = status!.binding
    model.error = ''
    emit('status', states, !!model.binding)
    if (model.binding) timer = setTimeout(() => void load(), indexing.value ? 3000 : 60000)
  } catch (failure) {
    if (!disposed && generation === revision) {
      model.error = (failure as Error).message
      emit('status', {}, !!model.binding)
    }
  } finally { if (generation === revision) model.loading = false }
}
function open() {
  model.path = model.binding?.path ?? ''
  dialog.value?.showModal()
}
async function bind(path: string) {
  model.busy = true
  model.loading = false
  revision++
  clearTimeout(timer)
  try {
    await api('/xiaomi/local/bind', { connection: props.connection, album: props.album, path })
    dialog.value?.close()
    await load()
  } catch (failure) { model.error = (failure as Error).message }
  finally { model.busy = false }
}
async function refresh() {
  model.busy = true
  try {
    await api('/xiaomi/local/refresh', { connection: props.connection, album: props.album })
    await load()
  } catch (failure) { model.error = (failure as Error).message }
  finally { model.busy = false }
}
watch(() => props.items.map(item => item.id).join(','), () => { if (!model.busy) void load() })
onMounted(() => void load())
onUnmounted(() => { disposed = true; revision++; clearTimeout(timer) })
</script>

<template>
  <div class="local-binding">
    <div class="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
      <button class="text-button min-w-0" @click="open"><Icon name="folder" :size="16" /><span class="truncate" :title="model.binding?.path">{{ model.binding?.path || '绑定本地文件夹' }}</span></button>
      <span v-if="model.binding" class="muted" role="status">{{ statusText }}</span>
      <button v-if="model.binding" class="text-button ml-auto" :disabled="model.busy || indexing" @click="refresh"><Icon name="refresh" :size="15" />更新索引</button>
    </div>
    <div v-if="model.binding" class="local-legend">
      <span><i class="local-color same" />同名同大小</span><span><i class="local-color different" />同名大小不同</span><span><i class="local-color missing" />本地没有</span>
    </div>
    <p v-if="model.error" class="notice error" role="alert">{{ model.error }}<button class="text-button" :disabled="model.loading || model.busy" @click="load">刷新状态</button></p>
  </div>
  <dialog ref="dialog" class="task-dialog" aria-labelledby="local-folder-title" @cancel="model.busy && $event.preventDefault()">
    <div class="section-heading"><h2 id="local-folder-title">绑定本地文件夹</h2><button class="icon-button" aria-label="关闭" :disabled="model.busy" @click="dialog?.close()"><Icon name="close" /></button></div>
    <form class="mt-4 grid gap-4" @submit.prevent="bind(model.path)">
      <label>目录绝对路径<input v-model="model.path" required maxlength="4096" placeholder="例如 /backups/手机淘宝 或 D:\照片备份" aria-describedby="local-folder-help" :disabled="model.busy" /></label>
      <p id="local-folder-help" class="muted">读取程序所在机器的目录及子目录。Docker 中请先只读挂载，例如 /backups；不会修改文件或联动删除。</p>
      <p class="muted">只缓存文件名和大小，后台每六小时择空闲更新。目录改动后也可手动更新索引。</p>
      <p v-if="model.error" class="notice error" role="alert">{{ model.error }}</p>
      <div class="dialog-actions"><button v-if="model.binding" type="button" class="secondary" :disabled="model.busy" @click="bind('')">解除绑定</button><button class="primary" :disabled="model.busy">{{ model.busy ? '正在保存…' : '保存绑定' }}</button></div>
    </form>
  </dialog>
</template>

<style scoped>
@reference '../app/assets/main.css';
.local-binding { @apply mb-4 border-b border-solid border-hairline pb-3; border-width: 0 0 1px; }
.local-legend { @apply flex flex-wrap gap-3 text-xs text-muted; }
.local-legend span { @apply inline-flex items-center gap-1.5; }
.local-color { @apply inline-block h-1.5 w-5 rounded-sm; }
.same { background: #16a34a; }
.different { background: #eab308; }
.missing { background: #dc2626; }
</style>
