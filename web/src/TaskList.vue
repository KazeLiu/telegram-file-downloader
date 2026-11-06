<script setup lang="ts">
import { bytes, date, groupPercent, taskLabels, type Task } from './api'
import Icon from './Icon.vue'
defineProps<{ tasks: Task[]; compact?: boolean }>()
defineEmits<{ select: [task: Task] }>()
</script>
<template>
  <div class="task-list" :class="{ compact }">
    <div class="list-head"><span>文件</span><span>收集时间</span><span>平均速度</span><span>状态</span><span></span></div>
    <button v-for="task in tasks" :key="task.id" class="task-row" @click="$emit('select', task)">
      <span class="file-cell"><span class="file-icon" :class="task.kind"><Icon :name="task.kind === 'archive' ? 'archive' : task.kind === 'video' ? 'video' : task.kind === 'photo' ? 'photo' : 'file'" :size="22" /></span><span class="file-text"><strong>{{ task.archive_name || task.filename }}</strong><small><template v-if="(task.group_count || 0) > 1">{{ task.group_count }} 个分卷 · </template>{{ bytes(task.group_size ?? task.size) }}<template v-if="task.quality"> · {{ task.quality }}</template></small></span></span>
      <span class="date-cell">{{ date(task.created_at) }}</span><span class="speed-cell">{{ (task.group_count || 0) > 1 ? '按分卷查看' : task.average_speed ? bytes(task.average_speed) + '/s' : '—' }}</span>
      <span class="status-cell"><span class="badge" :class="task.display_status || task.status">{{ taskLabels[task.display_status || task.status] || task.status }}</span><progress v-if="['downloading', 'waiting'].includes(task.display_status || task.status)" :value="groupPercent(task)" max="100" :aria-label="task.filename + ' 下载进度'" /></span><Icon name="chevron" :size="16" />
    </button>
  </div>
</template>
