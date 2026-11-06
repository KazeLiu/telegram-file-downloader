<script setup lang="ts">
import { computed } from 'vue'
import type { Task } from './api'
import Icon from './Icon.vue'
const props = defineProps<{ task: Task; busy?: boolean }>()
defineEmits<{ action: [action: 'pause' | 'resume' | 'retry'] }>()
const downloadable = computed(() => (!props.task.stage || props.task.stage === 'download') && ['queued', 'interrupted', 'downloading', 'waiting', 'retrying'].includes(props.task.status))
const retryable = computed(() => ['failed', 'extraction_failed', 'processing_failed', 'waiting_volumes'].includes(props.task.status))
</script>
<template>
  <div class="task-actions">
    <button v-if="downloadable" class="secondary" :disabled="busy" @click.stop="$emit('action', 'pause')"><Icon name="pause" :size="16" />暂停</button>
    <button v-if="task.status === 'paused'" class="secondary" :disabled="busy" @click.stop="$emit('action', 'resume')"><Icon name="play" :size="16" />继续</button>
    <button v-if="retryable" class="secondary" :disabled="busy" @click.stop="$emit('action', 'retry')"><Icon name="refresh" :size="16" />重试{{ task.status === 'waiting_volumes' ? '解压' : '' }}</button>
  </div>
</template>
