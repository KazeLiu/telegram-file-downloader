<script setup lang="ts">
import type { PlaybackPosition } from './types'

defineProps<{
  reason: string
  elapsed: string
  position: PlaybackPosition
}>()

defineEmits<{ restart: []; close: [] }>()
</script>

<template>
  <div class="playback-finished">
    <section class="finished-card" role="status" aria-live="polite" tabindex="-1" aria-label="本次播放结束">
      <h2>本次播放结束</h2>
      <p class="reason">{{ reason }}</p>
      <p class="fact">本次播放 {{ elapsed }}</p>
      <p class="fact">完成第 {{ position.cycle }} 轮 · {{ position.index + 1 }} / {{ position.total }} 项</p>
      <div class="finished-actions">
        <button type="button" class="primary" @click="$emit('restart')">再来一次</button>
        <button type="button" class="secondary" @click="$emit('close')">返回播放列表</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.playback-finished {
  position: fixed;
  inset: 0;
  z-index: 62;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(0, 0, 0, .68);
}
.finished-card {
  width: min(460px, 100%);
  padding: 28px;
  border-radius: var(--radius-panel);
  background: var(--color-canvas);
  color: var(--color-ink);
  box-shadow: 0 18px 48px rgba(0, 0, 0, .32);
}
.finished-card:focus-visible {
  outline: 2px solid var(--color-primary-focus);
  outline-offset: 3px;
}
.finished-card h2 {
  margin: 0 0 12px;
  font-size: 21px;
  font-weight: 600;
}
.reason {
  color: var(--color-ink);
  font-size: 15px;
}
.fact {
  margin-top: 6px;
  color: var(--color-muted);
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}
.finished-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 24px;
}
.finished-actions button {
  min-height: 44px;
}
@media (max-width: 480px) {
  .finished-card { padding: 22px; }
  .finished-actions { flex-direction: column; }
  .finished-actions button { width: 100%; }
}
</style>
