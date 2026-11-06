<script setup lang="ts">
import { computed } from 'vue'
import type { Task, TaskAction } from './api'
import Icon from './Icon.vue'
const props = defineProps<{ task: Task; busy?: boolean; archiveControls?: boolean }>()
defineEmits<{ action: [action: TaskAction] }>()
const downloadable = computed(() => (!props.task.stage || props.task.stage === 'download') && ['queued', 'interrupted', 'downloading', 'waiting', 'retrying'].includes(props.task.status))
const retryable = computed(() => ['failed', 'extraction_failed', 'processing_failed', 'waiting_volumes'].includes(props.task.status) || props.task.manual_extract_only && props.task.status === 'interrupted')
const archiveIdle = computed(() => props.archiveControls && props.task.kind === 'archive' &&
  !(props.task.group_members || [props.task]).some(part => ['downloading', 'waiting', 'retrying', 'extracting', 'organizing', 'manual_extracted', 'extracted', 'organized'].includes(part.status)))
</script>
<template>
  <div class="task-actions">
    <button v-if="downloadable" class="secondary" :disabled="busy" @click.stop="$emit('action', 'pause')"><Icon name="pause" :size="16" />暂停</button>
    <button v-if="task.status === 'paused'" class="secondary" :disabled="busy" @click.stop="$emit('action', 'resume')"><Icon name="play" :size="16" />继续</button>
    <button v-if="retryable && !(archiveIdle && task.manual_extract_only)" class="secondary" :disabled="busy" @click.stop="$emit('action', task.manual_extract_only ? 'extract_only' : 'retry')"><Icon name="refresh" :size="16" />重试{{ task.status === 'waiting_volumes' || task.manual_extract_only ? '解压' : '' }}</button>
    <template v-if="archiveIdle">
      <button class="secondary" :disabled="busy" @click.stop="$emit('action', 'extract_only')"><Icon name="folder" :size="16" />仅解压到文件夹</button>
      <button class="secondary" :disabled="busy" @click.stop="$emit('action', 'mark_manual_extracted')"><Icon name="check" :size="16" />标记为手动解压</button>
    </template>
  </div>
</template>
