<script setup lang="ts">
import { onMounted, onUnmounted, reactive, watch } from 'vue'
import { useRoute, useRouter } from '#imports'
import { queryText } from './routeState'
import { api } from './api'
import Icon from './Icon.vue'
const logsModel = reactive({ name: 'collector.log', files: [] as string[], content: '', live: true, busy: false, error: '' })
const route = useRoute()
const router = useRouter()
let timer: ReturnType<typeof setInterval>
let loadRevision = 0
async function load() {
  const revision = ++loadRevision
  logsModel.busy = true
  try {
    const result = await api(`/logs?name=${encodeURIComponent(logsModel.name)}`)
    if (revision === loadRevision) { Object.assign(logsModel, result); logsModel.error = '' }
  }
  catch (error) { if (revision === loadRevision) logsModel.error = (error as Error).message }
  finally { if (revision === loadRevision) logsModel.busy = false }
}
function selectFile() { void router.push({ path: '/logs', query: { file: logsModel.name } }) }
async function readRoute() { logsModel.name = queryText(route.query.file) || 'collector.log'; await load() }
watch(() => route.fullPath, () => { if (route.path === '/logs') void readRoute() })
onMounted(() => { void readRoute(); timer = setInterval(() => { if (logsModel.live && !logsModel.busy && !document.hidden) void load() }, 5000) })
onUnmounted(() => clearInterval(timer))
</script>
<template>
  <section class="logs-panel"><p v-if="logsModel.error" class="notice error" role="alert">{{ logsModel.error }}</p><div class="logs-toolbar"><select v-model="logsModel.name" :disabled="logsModel.busy" aria-label="选择日志文件" @change="selectFile"><option v-for="name in logsModel.files" :key="name">{{ name }}</option></select><label class="live-logs"><input v-model="logsModel.live" type="checkbox" />自动更新</label><button class="secondary" :disabled="logsModel.busy" @click="load"><Icon name="refresh" :size="16" />刷新</button><a class="secondary" :href="`/api/logs/download?name=${encodeURIComponent(logsModel.name)}`" download><Icon name="down" :size="16" />下载日志</a></div><span class="muted">最近 500 行</span><pre class="log-output" tabindex="0" aria-label="运行日志">{{ logsModel.content || '暂无运行日志' }}</pre></section>
</template>
