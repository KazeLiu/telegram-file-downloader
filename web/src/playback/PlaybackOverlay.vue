<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'
import type { PhaseKind } from './types'

const props = defineProps<{
  phase: PhaseKind
  paused: boolean
  beatIntervalMs: number
  dim: number
}>()

const root = ref<HTMLElement>()

/** 节拍速率：由间隔毫秒换算成 BPM，0 表示当前阶段没有节拍。 */
const bpm = computed(() => (props.beatIntervalMs > 0 ? Math.round((60000 / props.beatIntervalMs) * 100) / 100 : 0))
const beatVisible = computed(() => bpm.value > 0)
/** dim 是画面亮度（20–100），转成遮罩不透明度，数值越小遮罩越重。 */
const dimOpacity = computed(() => Math.max(0, Math.min(0.8, (100 - props.dim) / 100)))

// 节拍间隔只能按运行时算出的值下发，故走自定义属性；样式里只做 opacity / transform 过渡。
watchEffect(() => {
  const element = root.value
  if (!element) return
  element.style.setProperty('--bpm', String(bpm.value || 1))
  element.style.setProperty('--beat-interval', bpm.value ? 'calc(60s / var(--bpm))' : '0s')
  element.style.setProperty('--dim-opacity', String(dimOpacity.value))
})
</script>

<template>
  <div ref="root" class="playback-overlay" :data-phase="phase" :data-paused="paused ? 'true' : 'false'">
    <div class="tone tone-slow" :class="{ active: phase === 'slow' }" aria-hidden="true"></div>
    <div class="tone tone-fast" :class="{ active: phase === 'fast' }" aria-hidden="true"></div>
    <div class="tone tone-rest" :class="{ active: phase === 'rest' }" aria-hidden="true"></div>
    <div class="dim" aria-hidden="true"></div>
    <div class="region region-stage">
      <slot name="stage" />
    </div>
    <div v-if="beatVisible" class="beat" aria-hidden="true"></div>
    <div class="region region-top">
      <slot name="top" />
    </div>
    <div class="region region-bottom">
      <slot name="bottom" />
    </div>
  </div>
</template>

<style scoped>
.playback-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  overflow: hidden;
  background: #000;
  color: #fff;
  -webkit-tap-highlight-color: transparent;
}
.tone {
  position: absolute;
  inset: 0;
  z-index: 0;
  opacity: 0;
  pointer-events: none;
  transition: opacity 1.2s ease;
}
.tone.active { opacity: 1; }
.tone-slow {
  background:
    radial-gradient(120% 90% at 50% 0%, rgba(242, 175, 201, .18), transparent 60%),
    radial-gradient(90% 70% at 50% 100%, rgba(92, 70, 82, .55), transparent 72%);
}
.tone-fast {
  background:
    radial-gradient(100% 80% at 50% 0%, rgba(168, 61, 104, .34), transparent 62%),
    radial-gradient(80% 60% at 50% 100%, rgba(242, 175, 201, .16), transparent 70%);
}
.tone-rest {
  background: radial-gradient(110% 90% at 50% 40%, rgba(39, 39, 41, .92), transparent 75%);
}
.dim {
  position: absolute;
  inset: 0;
  z-index: 1;
  background: #000;
  opacity: var(--dim-opacity, 0);
  pointer-events: none;
}
.region {
  position: absolute;
  z-index: 4;
  pointer-events: none;
}
.region-top {
  inset: 0 0 auto;
  padding-top: env(safe-area-inset-top);
}
.region-bottom {
  inset: auto 0 0;
  padding-bottom: env(safe-area-inset-bottom);
}
.region-stage {
  inset: 0;
  z-index: 2;
}
.beat {
  position: absolute;
  inset: 0;
  z-index: 3;
  display: grid;
  place-items: center;
  pointer-events: none;
}
.beat::after {
  content: '';
  width: min(58vmin, 460px);
  aspect-ratio: 1;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(242, 175, 201, .22) 0%, rgba(242, 175, 201, 0) 70%);
  animation: beat-halo var(--beat-interval, 0s) ease-out infinite;
}
.playback-overlay[data-paused='true'] .beat::after { animation-play-state: paused; }
@keyframes beat-halo {
  0% { opacity: .12; transform: scale(.86); }
  40% { opacity: .5; transform: scale(1); }
  100% { opacity: 0; transform: scale(1.06); }
}
@media (prefers-reduced-motion: reduce) {
  .tone { transition: none; }
  .beat::after {
    animation: none;
    opacity: .28;
    transform: none;
  }
}
</style>
