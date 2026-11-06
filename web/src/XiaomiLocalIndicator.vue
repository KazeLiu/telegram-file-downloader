<script setup lang="ts">
import { localStateLabels, type LocalFileState } from './xiaomiMedia'
defineProps<{ state: LocalFileState; dot?: boolean }>()
</script>

<template>
  <span class="local-indicator" :class="[state, dot ? 'dot' : 'bar']" role="img" :aria-label="localStateLabels[state]" :title="localStateLabels[state]" />
</template>

<style scoped>
@reference '../app/assets/main.css';
.local-indicator { @apply inline-block shrink-0; }
.dot { @apply absolute right-1 bottom-1 size-2.5 rounded-full ring-2 ring-white; }
.bar { @apply h-1.5 w-7 rounded-sm; }
.same { background: #16a34a; }
.different { background: #eab308; }
.missing { background: #dc2626; }
.unknown { background: #94a3b8; }
</style>
