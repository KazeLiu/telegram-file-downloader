<script setup lang="ts">
import { computed, onUnmounted, reactive, ref } from 'vue'
import { api, bytes } from './api'
import Icon from './Icon.vue'
import XiaomiThumbnail from './XiaomiThumbnail.vue'
import { formatNames, parseNames, takenAt, type CloudMedia } from './xiaomiMedia'

const props = defineProps<{ connection: string; album: string; albumName: string; lastLocalRecycle: string[]; disabled: boolean }>()
const emit = defineEmits<{ recycled: [ids: string[]]; message: [text: string] }>()
const dialog = ref<HTMLDialogElement>()
const model = reactive({ input: '', items: [] as CloudMedia[], unmatched: [] as string[], duplicates: new Set<string>(),
  selected: new Set<string>(), page: 0, searching: false, running: false, ready: false, searchedPages: 0,
  stopping: false, progress: 0, targetCount: 0, result: '', error: '' })
const pages = computed(() => Math.max(1, Math.ceil(model.items.length / 20)))
const visible = computed(() => model.items.slice(model.page * 20, (model.page + 1) * 20))
let revision = 0

function resetPreview() {
  model.ready = false; model.items = []; model.unmatched = []; model.duplicates.clear(); model.selected.clear()
  model.page = 0; model.searchedPages = 0; model.error = ''; model.result = ''
}
function useLocalNames() {
  model.input = formatNames(props.lastLocalRecycle)
  resetPreview()
}
async function search() {
  if (model.searching || model.running) return
  resetPreview()
  const generation = ++revision
  try {
    const names = parseNames(model.input)
    model.searching = true
    const matches = new Map<string, CloudMedia>()
    const markers = new Set<string>()
    for (let page = 0; ; page++) {
      const result = await api<{ items: CloudMedia[]; last: boolean; marker: string }>('/xiaomi/media/match', {
        connection: props.connection, album: props.album, names, page,
      })
      if (generation !== revision || !dialog.value?.open) return
      if (result.marker && markers.has(result.marker)) throw new Error('小米云返回了重复的相册页，请重新匹配。')
      if (result.marker) markers.add(result.marker)
      for (const item of result.items) matches.set(item.id, item)
      model.searchedPages = page + 1
      if (result.last) break
    }
    const counts = new Map<string, number>()
    for (const item of matches.values()) counts.set(item.name, (counts.get(item.name) ?? 0) + 1)
    model.items = [...matches.values()]
    model.unmatched = names.filter(name => !counts.has(name))
    model.duplicates = new Set(names.filter(name => (counts.get(name) ?? 0) > 1))
    model.selected = new Set(model.items.filter(item => !model.duplicates.has(item.name)).map(item => item.id))
    model.ready = true
  } catch (failure) {
    if (generation === revision) model.error = (failure as Error).message
  } finally {
    if (generation === revision) model.searching = false
  }
}
function close() {
  revision++
  model.searching = false
  resetPreview()
}
onUnmounted(() => { revision++ })

async function recycle() {
  if (!model.ready || model.running || !model.selected.size) return
  const targets = model.items.filter(item => model.selected.has(item.id))
  const moved: string[] = []
  const generation = revision
  model.running = true; model.stopping = false; model.error = ''; model.targetCount = targets.length; model.progress = 0
  try {
    for (const item of targets) {
      try { await api('/xiaomi/recycle', { connection: props.connection, id: item.id }) }
      catch (failure) {
        model.error = `未确认「${item.name}」的结果：${(failure as Error).message}。已停止后续回收，请重新匹配后再操作。`
        break
      }
      if (revision !== generation) return
      moved.push(item.id)
      model.progress = moved.length
      if (model.stopping) break
    }
    if (moved.length) {
      emit('recycled', moved)
      emit('message', `已将 ${moved.length} 张图片移入小米云回收站`)
    }
    model.result = `已确认回收 ${moved.length} / ${targets.length} 张。${model.stopping && moved.length < targets.length ? '后续项目已停止。' : ''}`
    model.ready = false; model.items = []; model.selected.clear()
  } finally { model.running = false }
}
</script>

<template>
  <button class="secondary" :disabled="disabled" @click="dialog?.showModal()">按文件名回收</button>
  <dialog ref="dialog" class="task-dialog name-recycle" aria-labelledby="name-recycle-title" @close="close" @cancel="model.running && $event.preventDefault()">
    <div class="section-heading"><h2 id="name-recycle-title" class="min-w-0 break-all">按文件名回收：{{ albumName }}</h2><button class="icon-button shrink-0" aria-label="关闭" :disabled="model.running" @click="dialog?.close()"><Icon name="close" /></button></div>
    <form class="mt-4 grid gap-3" @submit.prevent="search">
      <label>图片文件名<textarea v-model="model.input" rows="3" placeholder="例如 IMG_001.jpg, IMG_002.png" :disabled="model.searching || model.running" @input="resetPreview" /></label>
      <div class="dialog-actions">
        <button v-if="lastLocalRecycle.length" type="button" class="text-button" :disabled="model.searching || model.running" @click="useLocalNames">带入最近本地回收清单</button>
        <button type="submit" class="secondary" :disabled="model.searching || model.running || !model.input.trim()">{{ model.result ? '重新匹配' : '匹配图片' }}</button>
      </div>
    </form>
    <p v-if="model.searching" class="muted mt-3" role="status">正在查找 · 已检查 {{ model.searchedPages }} 页</p>
    <p v-if="model.error" class="notice error" role="alert">{{ model.error }}</p>
    <p v-if="model.result" class="notice" role="status">{{ model.result }}</p>
    <template v-if="model.ready">
      <p class="mt-4" role="status">匹配 {{ model.items.length }} 张，选中 {{ model.selected.size }} 张<span v-if="model.duplicates.size">。同名多张未自动选中</span>。</p>
      <details v-if="model.unmatched.length" class="my-2 text-sm text-muted">
        <summary>未找到 {{ model.unmatched.length }} 个文件名</summary>
        <p class="max-h-28 overflow-auto break-all">{{ formatNames(model.unmatched) }}</p>
      </details>
      <div v-if="visible.length" class="name-preview my-3">
        <label v-for="item in visible" :key="item.id" class="name-preview-card">
          <XiaomiThumbnail :item="item" />
          <span class="flex items-start gap-2"><input v-model="model.selected" type="checkbox" :value="item.id" :disabled="model.running" /><strong class="min-w-0 break-all">{{ item.name }}</strong></span>
          <small class="text-muted">{{ takenAt(item.taken_at) }}<template v-if="item.size"> · {{ bytes(item.size) }}</template></small>
          <small v-if="model.duplicates.has(item.name)" class="text-muted">同名 · 编号 {{ item.id }}</small>
        </label>
      </div>
      <div v-if="pages > 1" class="pagination">
        <span>第 {{ model.page + 1 }} / {{ pages }} 页</span>
        <button class="secondary" :disabled="model.page === 0 || model.running" @click="model.page--">上一页</button>
        <button class="secondary" :disabled="model.page + 1 >= pages || model.running" @click="model.page++">下一页</button>
      </div>
      <div v-if="model.items.length" class="name-confirm mt-4">
        <p class="muted">仅回收已选的云端图片。删除会同步到开启相册同步的设备。</p>
        <p v-if="model.running" role="status">已确认 {{ model.progress }} / {{ model.targetCount }} 张</p>
        <button v-if="model.running" class="secondary" :disabled="model.stopping" @click="model.stopping = true">{{ model.stopping ? '等待当前请求结束…' : '停止后续回收' }}</button>
        <button v-else class="danger" :disabled="!model.selected.size" @click="recycle">确认移入云端回收站 · {{ model.selected.size }} 张</button>
      </div>
    </template>
  </dialog>
</template>

<style scoped>
@reference '../app/assets/main.css';
.name-recycle { width: min(880px, calc(100% - 24px)); }
.name-preview { @apply grid grid-cols-2 gap-3 sm:grid-cols-4; }
.name-preview-card { @apply min-w-0 gap-1.5 rounded-lg border border-solid border-hairline p-2; }
.name-preview-card input[type=checkbox] { @apply size-4 appearance-auto accent-blue; }
.name-preview-card input::after { display: none; }
.name-confirm { @apply sticky bottom-0 flex flex-wrap items-center justify-between gap-2 border-t border-solid border-hairline bg-canvas py-2; border-width: 1px 0 0; }
</style>
