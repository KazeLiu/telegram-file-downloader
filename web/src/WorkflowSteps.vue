<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { bytes, percent, taskLabels, type Settings, type Task } from './api'
import Icon from './Icon.vue'
const props = defineProps<{ task?: Task | null; settings?: Settings }>()
const workflowModel = reactive({ selected: 'download' })
const legacyPdf = computed(() => !!props.task?.steps?.pdf && !props.task?.steps?.cleanup && !props.task?.steps?.psd && ['organized', 'extracted', 'completed'].includes(props.task?.status || ''))
const legacyPsd = computed(() => !!props.task?.steps?.psd && !props.task?.steps?.cleanup && ['organized', 'extracted', 'completed'].includes(props.task?.status || ''))
const cleanupDetail = computed(() => {
  const task = props.task
  if (legacyPdf.value) return `旧版记录：删除 ${task?.deleted_pdfs || 0} 个 PDF。当前保留 PDF。`
  if (legacyPsd.value) return `旧版记录：直接删除 ${task?.deleted_psds || 0} 个 PSD。`
  if (task?.recycled_psds || task?.recycled_txts) return `已将 ${task.recycled_psds || 0} 个 PSD、${task.recycled_txts || 0} 个 TXT 移入回收站，可在本地图片快筛中还原。`
  if (task?.deleted_psds || task?.deleted_txts) return `旧版记录：直接删除 ${task.deleted_psds || 0} 个 PSD、${task.deleted_txts || 0} 个 TXT。`
  return '将本次资源的 PSD、TXT 移入持久回收站，可还原；PDF 保留。'
})
watch(() => props.task?.id, () => { workflowModel.selected = props.task?.manual_extract_only ? 'extract' : props.task?.stage === 'complete' ? 'organize' : props.task?.stage || 'download' }, { immediate: true })
const nodes = computed(() => [
  { id: 'receive', title: '接收转发', icon: 'telegram', detail: props.task ? `任务 #${props.task.id} 已记录` : '群里的新附件会记录到下载队列。' },
  { id: 'download', title: '下载文件', icon: 'down', detail: props.task ? `${bytes(props.task.downloaded)} / ${bytes(props.task.size)} · ${percent(props.task).toFixed(1)}%` : `最多 ${props.settings?.parallel_files || 5} 个文件，每个文件最多 ${props.settings?.download_parallelism || 4} 路；实际文件数遵守 Telegram 队列上限。` },
  { id: 'volumes', title: '分卷收齐', icon: 'archive', detail: '同组分卷下载齐全并通过完整性检查后，才会继续。' },
  { id: 'extract', title: props.task?.manual_extract_only ? '手动解压' : '完整解压', icon: 'folder', detail: props.task?.manual_source === 'external' ? '由你确认已在外部解压，只更新记录，不检查原包。' : props.task?.manual_extract_only ? '整组仅解压到资源文件夹，保留原包；后续由你手动整理和处理图片。' : props.settings?.extract === false ? '自动解压已关闭。' : '先无密码，再尝试保存的密码；失败保留原包。' },
  { id: 'organize', title: '平铺到根目录', icon: 'workflow', detail: props.task?.result_files ? `已整理 ${props.task.result_files} 个文件到下载根目录。` : '资源A/第一套/001.jpg → 资源A-第一套-001.jpg' },
  { id: legacyPdf.value ? 'pdf' : legacyPsd.value ? 'psd' : 'cleanup', title: legacyPdf.value ? '旧版 PDF 清理' : legacyPsd.value ? '旧版 PSD 清理' : '回收 PSD / TXT', icon: 'trash', detail: cleanupDetail.value },
  { id: 'cloud', title: '小米云相册', icon: 'cloud', detail: '在侧栏打开「小米云相册」手动上传；此工作流不自动上传。' },
])
function state(id: string) {
  if (props.task?.manual_extract_only && ['organize', 'cleanup', 'cloud'].includes(id)) return 'skipped'
  if (id === 'cloud') return 'pending'
  if (props.task?.stage === id && ['paused', 'waiting', 'waiting_volumes', 'interrupted'].includes(props.task.status)) return 'waiting'
  const saved = props.task?.steps?.[id]
  if (saved) return saved
  if (props.task && id === 'receive') return 'done'
  if (props.task?.stage === id) return ['failed', 'extraction_failed', 'processing_failed'].includes(props.task.status) ? 'failed' : ['paused', 'waiting', 'waiting_volumes'].includes(props.task.status) ? 'waiting' : 'active'
  return 'idle'
}
const labels: Record<string, string> = { done: '完成', manual: '用户确认', active: '进行中', failed: '需处理', waiting: '等待', skipped: '已跳过', idle: '待执行', pending: '手动上传' }
</script>
<template>
  <section class="workflow-panel" aria-label="资源处理工作流">
    <div class="section-heading"><h2>处理步骤</h2><span v-if="task" class="badge" :class="task.status">{{ taskLabels[task.status] || task.status }}</span></div>
    <div class="workflow-track"><button v-for="node in nodes" :key="node.id" class="workflow-node" :class="[state(node.id), { selected: workflowModel.selected === node.id }]" :aria-current="workflowModel.selected === node.id ? 'step' : undefined" @click="workflowModel.selected = node.id"><span class="node-icon"><Icon :name="state(node.id) === 'done' ? 'check' : node.icon" :size="23" /></span><strong>{{ node.title }}</strong><small>{{ labels[state(node.id)] }}</small></button></div>
    <div class="workflow-caption"><Icon :name="nodes.find(n => n.id === workflowModel.selected)?.icon || 'workflow'" :size="17" /><p>{{ nodes.find(n => n.id === workflowModel.selected)?.detail }}</p></div>
  </section>
</template>
