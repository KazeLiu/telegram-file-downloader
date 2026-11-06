<script setup lang="ts">
import { onMounted, onUnmounted, reactive } from 'vue'
import { api } from './api'
import Icon from './Icon.vue'
const logsModel = reactive({ name: 'collector.log', files: [] as string[], content: '', live: true, busy: false, error: '' })
let timer: ReturnType<typeof setInterval>
async function load() {
  if (logsModel.busy) return
  logsModel.busy = true
  try { Object.assign(logsModel, await api(`/logs?name=${encodeURIComponent(logsModel.name)}`)); logsModel.error = '' }
  catch (error) { logsModel.error = (error as Error).message }
  finally { logsModel.busy = false }
}
onMounted(() => { void load(); timer = setInterval(() => { if (logsModel.live && !document.hidden) void load() }, 5000) })
onUnmounted(() => clearInterval(timer))
</script>
<template>
  <section class="logs-panel"><p v-if="logsModel.error" class="notice error">{{ logsModel.error }}</p><div class="logs-toolbar"><select v-model="logsModel.name" aria-label="选择日志文件" @change="load"><option v-for="name in logsModel.files" :key="name">{{ name }}</option></select><label class="live-logs"><input v-model="logsModel.live" type="checkbox" />自动更新</label><button class="secondary" :disabled="logsModel.busy" @click="load"><Icon name="refresh" :size="16" />刷新</button><a class="secondary" :href="`/api/logs/download?name=${encodeURIComponent(logsModel.name)}`" download><Icon name="down" :size="16" />下载日志</a></div><p class="muted">最近 500 行。日志保存在持久化数据目录的 logs 中，每份最多 5 MB，保留 5 份轮转备份。</p><pre class="log-output" tabindex="0" aria-label="运行日志">{{ logsModel.content || '暂无运行日志。接收任务、下载进度和错误会记录在这里。' }}</pre></section>
</template>
