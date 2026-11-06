<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api } from './api'
import Icon from './Icon.vue'
import type { CloudMedia } from './xiaomiMedia'

type LocalPreview = { id: string; name: string; root: string; path: string; status: string; detail: string }
type Preview = LocalPreview & { token: string }
type Result = { id: string; name: string; token: string; cloud_done: boolean; local_done: boolean; local: LocalPreview; error: string }
const props = defineProps<{ connection: string; album: string }>()
const emit = defineEmits<{ recycled: [ids: string[]]; message: [text: string] }>()
const dialog = ref<HTMLDialogElement>()
const model = reactive({ items: [] as Preview[], pending: [] as Result[], loading: false, running: false, stopping: false,
  done: 0, localDone: 0, error: '', result: '', retrying: '', pendingError: '' })
let disposed = false

async function loadPending() {
  model.pendingError = ''
  try { model.pending = (await api<{ items: Result[] }>(`/xiaomi/recycle/pending?connection=${props.connection}`)).items }
  catch (failure) { model.pendingError = (failure as Error).message }
}

async function open(items: CloudMedia[]) {
  if (model.running || model.retrying) return
  Object.assign(model, { items: [], loading: true, done: 0, localDone: 0, error: '', result: '', stopping: false })
  await nextTick(); dialog.value?.showModal()
  try {
    for (let offset = 0; offset < items.length; offset += 2000) {
      const result = await api<{ items: Preview[] }>('/xiaomi/recycle/preview', {
        connection: props.connection, album: props.album, ids: items.slice(offset, offset + 2000).map(item => item.id),
      })
      if (disposed) return
      model.items.push(...result.items)
    }
  } catch (failure) { model.error = (failure as Error).message; model.items = [] }
  finally { model.loading = false }
}

async function recycle() {
  if (model.loading || model.running || !model.items.length || model.result) return
  model.running = true; model.error = ''; model.stopping = false
  const moved: string[] = []
  try {
    for (const item of model.items) {
      const result = await api<Result>('/xiaomi/recycle', { connection: props.connection, id: item.id, token: item.token })
      if (result.cloud_done) { moved.push(item.id); model.done++ }
      if (result.local_done) model.localDone++
      if (result.error) { model.error = result.error; break }
      if (disposed || model.stopping) break
    }
  } catch (failure) { model.error = `${(failure as Error).message}。已停止后续操作；云端未确认的项目不会回收本地。` }
  finally {
    model.running = false
    model.result = `云端已确认回收 ${model.done} / ${model.items.length} 项，本地已回收 ${model.localDone} 项。`
    if (moved.length) { emit('recycled', moved); emit('message', model.result) }
    if (!disposed) await loadPending()
  }
}

async function retry(item: Result) {
  if (model.retrying || model.running) return
  model.retrying = item.token; model.pendingError = ''
  try {
    const result = await api<Result>('/xiaomi/recycle', { connection: props.connection, id: item.id, token: item.token })
    await loadPending()
    if (result.error) model.pendingError = result.error
    else emit('message', `本地已回收：${item.name}`)
  } catch (failure) { model.pendingError = (failure as Error).message }
  finally { model.retrying = '' }
}

defineExpose({ open })
onMounted(() => void loadPending())
onUnmounted(() => { disposed = true })
</script>

<template>
  <section v-if="model.pending.length || model.pendingError" class="notice" aria-label="待完成的本地回收">
    <h3 v-if="model.pending.length">云端已回收，本地待处理 · {{ model.pending.length }} 项</h3>
    <p v-if="model.pendingError" class="form-error" role="alert">{{ model.pendingError }}</p>
    <button class="text-button" :disabled="!!model.retrying || model.running" @click="loadPending">刷新待处理清单</button>
    <ul class="my-2 max-h-48 space-y-2 overflow-auto">
      <li v-for="item in model.pending" :key="item.token" class="flex flex-wrap items-center justify-between gap-2">
        <span class="min-w-0 break-all">{{ item.name }}<small class="block text-muted">{{ item.local.root }}/{{ item.local.path }}</small></span>
        <button class="secondary" :disabled="!!model.retrying || model.running" @click="retry(item)">{{ model.retrying === item.token ? '正在重试…' : '仅重试本地回收' }}</button>
      </li>
    </ul>
  </section>
  <dialog ref="dialog" class="task-dialog linked-recycle" aria-labelledby="linked-recycle-title" @cancel="(model.loading || model.running) && $event.preventDefault()">
    <div class="section-heading"><h2 id="linked-recycle-title">回收云端及对应本地文件</h2><button class="icon-button" aria-label="关闭回收确认" :disabled="model.loading || model.running" @click="dialog?.close()"><Icon name="close" /></button></div>
    <p class="mt-3">云端成功后，唯一的同名同大小本地文件才会移入项目回收站。重名或不匹配的本地文件保留。</p>
    <p class="muted mt-2">云端删除会同步到开启相册同步的设备。本地文件静置满 15 天后，由 Windows 宿主机任务转入系统回收站。</p>
    <p v-if="model.loading" class="mt-4" role="status">正在核对本地文件…</p>
    <ul v-else class="my-4 max-h-72 list-none space-y-3 overflow-auto p-0">
      <li v-for="item in model.items" :key="item.token" class="break-all">
        <strong>{{ item.name }}</strong>
        <p v-if="item.path" class="text-sm text-muted">{{ item.root }}/{{ item.path }}</p>
        <p class="text-sm" :class="item.status === 'ready' ? 'text-muted' : 'text-danger'">{{ item.detail }}</p>
      </li>
    </ul>
    <p v-if="model.error" class="notice error" role="alert">{{ model.error }}</p>
    <p v-if="model.result" class="notice" role="status">{{ model.result }}<span v-if="model.pending.length">关闭后可单独重试未完成的本地回收。</span></p>
    <p v-else-if="model.running" role="status">云端已确认 {{ model.done }} / {{ model.items.length }} 项，本地已回收 {{ model.localDone }} 项</p>
    <div class="dialog-actions">
      <button v-if="model.running" class="secondary" :disabled="model.stopping" @click="model.stopping = true">{{ model.stopping ? '等待当前项目结束…' : '停止后续回收' }}</button>
      <template v-else><button class="secondary" :disabled="model.loading" @click="dialog?.close()">{{ model.result ? '关闭' : '保留' }}</button><button v-if="!model.result" class="danger" :disabled="model.loading || !model.items.length" @click="recycle">确认回收 · {{ model.items.length }} 项</button></template>
    </div>
  </dialog>
</template>

<style scoped>
.linked-recycle { width: min(680px, calc(100% - 24px)); }
</style>
