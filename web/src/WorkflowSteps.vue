<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { bytes, percent, taskLabels, type Settings, type Task } from './api'
import Icon from './Icon.vue'
const props = defineProps<{ task?: Task | null; settings?: Settings }>()
const workflowModel = reactive({ selected: 'download' })
const legacyPdf = computed(() => !!props.task?.steps?.pdf && !props.task?.steps?.cleanup && !props.task?.steps?.psd && ['organized', 'extracted', 'completed'].includes(props.task?.status || ''))
const legacyPsd = computed(() => !!props.task?.steps?.psd && !props.task?.steps?.cleanup && ['organized', 'extracted', 'completed'].includes(props.task?.status || ''))
watch(() => props.task?.id, () => { workflowModel.selected = props.task?.stage === 'complete' ? 'organize' : props.task?.stage || 'download' }, { immediate: true })
const nodes = computed(() => [
  { id: 'receive', title: '接收转发', icon: 'telegram', detail: props.task ? `任务 #${props.task.id} 已记录` : '群里的新附件会记录到下载队列。' },
  { id: 'download', title: '下载文件', icon: 'down', detail: props.task ? `${bytes(props.task.downloaded)} / ${bytes(props.task.size)} · ${percent(props.task).toFixed(1)}%` : `最多 ${props.settings?.parallel_files || 5} 个文件，每个文件最多 ${props.settings?.download_parallelism || 4} 路；实际文件数遵守 Telegram 队列上限。` },
  { id: 'volumes', title: '分卷收齐', icon: 'archive', detail: '同组分卷下载齐全并通过完整性检查后，才会继续。' },
  { id: 'extract', title: '完整解压', icon: 'folder', detail: props.settings?.extract === false ? '自动解压已关闭。' : '先无密码，再尝试保存的密码；失败保留原包。' },
  { id: 'organize', title: '平铺到根目录', icon: 'workflow', detail: props.task?.result_files ? `已整理 ${props.task.result_files} 个文件到下载根目录。` : '资源A/第一套/001.jpg → 资源A-第一套-001.jpg' },
  { id: legacyPdf.value ? 'pdf' : legacyPsd.value ? 'psd' : 'cleanup', title: legacyPdf.value ? '旧版 PDF 清理' : legacyPsd.value ? '旧版 PSD 清理' : '清理 PSD / TXT', icon: 'trash', detail: legacyPdf.value ? `旧版记录：删除 ${props.task?.deleted_pdfs || 0} 个 PDF。本版本仅清理 PSD、TXT，保留 PDF。` : legacyPsd.value ? `旧版记录：删除 ${props.task?.deleted_psds || 0} 个 PSD。` : props.task?.deleted_psds || props.task?.deleted_txts ? `已删除本次资源的 ${props.task?.deleted_psds || 0} 个 PSD、${props.task?.deleted_txts || 0} 个 TXT。` : '同一规则清理本次资源的 .psd、.txt 文件，PDF 保留。' },
  { id: 'cloud', title: '小米云相册', icon: 'cloud', detail: '待接入' },
])
function state(id: string) {
  if (id === 'cloud') return 'pending'
  if (props.task?.stage === id && ['paused', 'waiting', 'waiting_volumes', 'interrupted'].includes(props.task.status)) return 'waiting'
  const saved = props.task?.steps?.[id]
  if (saved) return saved
  if (props.task && id === 'receive') return 'done'
  if (props.task?.stage === id) return ['failed', 'extraction_failed', 'processing_failed'].includes(props.task.status) ? 'failed' : ['paused', 'waiting', 'waiting_volumes'].includes(props.task.status) ? 'waiting' : 'active'
  return 'idle'
}
const labels: Record<string, string> = { done: '完成', active: '进行中', failed: '需处理', waiting: '等待', skipped: '已跳过', idle: '待执行', pending: '待接入' }
</script>
<template>
  <section class="workflow-panel" aria-label="资源处理工作流">
    <div class="section-heading"><h2>从转发，到资源库。</h2><span class="muted">{{ task ? `任务 #${task.id} · ${taskLabels[task.status] || task.status}` : '自动工作流' }}</span></div>
    <div class="workflow-track"><button v-for="node in nodes" :key="node.id" class="workflow-node" :class="[state(node.id), { selected: workflowModel.selected === node.id }]" :aria-current="workflowModel.selected === node.id ? 'step' : undefined" @click="workflowModel.selected = node.id"><span class="node-icon"><Icon :name="state(node.id) === 'done' ? 'check' : node.icon" :size="23" /></span><strong>{{ node.title }}</strong><small>{{ labels[state(node.id)] }}</small></button></div>
    <div class="workflow-caption"><Icon :name="nodes.find(n => n.id === workflowModel.selected)?.icon || 'workflow'" :size="17" /><p>{{ nodes.find(n => n.id === workflowModel.selected)?.detail }}</p></div>
  </section>
</template>
