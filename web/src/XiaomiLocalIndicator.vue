<script setup lang="ts">
import { localStateLabels, type LocalFileState } from './xiaomiMedia'
import Icon from './Icon.vue'
defineProps<{ state: LocalFileState; dot?: boolean }>()
const symbols: Record<LocalFileState, string> = { same: 'check', different: 'compare', missing: 'close', unknown: 'search' }
const labels: Record<LocalFileState, string> = { same: '同名同大小', different: '大小不同', missing: '本地没有', unknown: '尚未核对' }
</script>

<template>
  <span class="local-indicator" :class="[state, dot ? 'dot' : 'bar']" role="img" :aria-label="localStateLabels[state]" :title="localStateLabels[state]"><Icon :name="symbols[state]" :size="12" /><span v-if="!dot" aria-hidden="true">{{ labels[state] }}</span></span>
</template>

<style scoped>
@reference '../app/assets/main.css';
.local-indicator { @apply inline-flex shrink-0 items-center justify-center gap-1; }
.dot { @apply absolute right-1 bottom-1 size-5 rounded-full border border-solid border-hairline bg-pearl; }
.bar { @apply text-xs; }
.same { @apply text-success; }
.different { @apply text-warning; }
.missing { @apply text-danger; }
.unknown { @apply text-muted; }
</style>
