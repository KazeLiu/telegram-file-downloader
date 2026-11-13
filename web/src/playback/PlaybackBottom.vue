<script setup lang="ts">
import { computed } from 'vue'
import type { LegendItem } from './types'

const props = defineProps<{
  title: string
  elapsed: string
  total: string
  progress: number
  hideTime: boolean
  legend: LegendItem[]
  nextLabel: string
  canNext: boolean
}>()

defineEmits<{
  next: []
}>()

/** 图例圆点颜色：与中央阶段药丸保持同一套色。 */
const legendTones: Record<LegendItem['tone'], string> = { slow: '#e6b34a', fast: '#35d6a4', rest: '#f2637c' }

/** 不限时（total 为空）或隐藏时间时，整条进度行都不渲染。 */
const showProgressRow = computed(() => !props.hideTime && props.total !== '')
const progressValue = computed(() => (Number.isFinite(props.progress) ? Math.min(100, Math.max(0, props.progress)) : 0))
</script>

<template>
  <footer class="playback-bottom">
    <p class="bottom-title" :title="title">{{ title }}</p>

    <div v-if="showProgressRow" class="bottom-progress">
      <div
        class="progress-track"
        role="progressbar"
        aria-label="本次播放进度"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-valuenow="Math.round(progressValue)"
      >
        <span class="progress-fill" :style="{ width: `${progressValue}%` }"></span>
      </div>
      <span class="progress-time">{{ elapsed }} / {{ total }}</span>
    </div>

    <div class="bottom-row">
      <ul class="legend" aria-label="阶段颜色说明">
        <li v-for="item in legend" :key="`${item.tone}-${item.label}`">
          <span class="dot" :style="{ background: legendTones[item.tone] }" aria-hidden="true"></span>{{ item.label }}
        </li>
      </ul>
      <div class="row-end">
        <button class="next-button" type="button" :disabled="!canNext" @click="$emit('next')">{{ nextLabel }}</button>
        <div class="controls">
          <slot name="controls" />
        </div>
      </div>
    </div>
  </footer>
</template>

<style scoped>
.playback-bottom {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 10px max(14px, env(safe-area-inset-right)) max(10px, env(safe-area-inset-bottom)) max(14px, env(safe-area-inset-left));
  color: #fff;
  pointer-events: auto;
  background: linear-gradient(180deg, rgba(0, 0, 0, 0), rgba(0, 0, 0, .55));
  -webkit-tap-highlight-color: transparent;
}
.bottom-title {
  margin: 0;
  overflow: hidden;
  color: rgba(255, 255, 255, .7);
  font-size: 13px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bottom-progress {
  display: flex;
  align-items: center;
  gap: 10px;
}
.progress-track {
  position: relative;
  flex: 1;
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, .22);
}
.progress-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: rgba(255, 255, 255, .82);
  transition: width .25s linear;
}
.progress-time {
  flex-shrink: 0;
  color: rgba(255, 255, 255, .7);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
/* 第三行：左图例、右药丸按钮与控件槽，窄屏自动换行 */
.bottom-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  font-size: 12px;
}
.legend {
  display: flex;
  flex: 1 1 auto;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 14px;
  min-width: 0;
  margin: 0;
  padding: 0;
  color: rgba(255, 255, 255, .62);
  font-size: 11px;
  line-height: 1.5;
  list-style: none;
}
.legend li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.row-end {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 6px 10px;
  min-width: 0;
  margin-left: auto;
}
.next-button {
  position: relative;
  padding: 4px 12px;
  border: 1px solid rgba(255, 255, 255, .3);
  border-radius: 999px;
  color: rgba(255, 255, 255, .8);
  font-family: inherit;
  font-size: 11px;
  line-height: 1.4;
  white-space: nowrap;
  background: rgba(255, 255, 255, .06);
  cursor: pointer;
  transition: background-color .15s ease, opacity .15s ease;
}
/* 药丸视觉偏小，命中区补到 44px 高 */
.next-button::after {
  content: '';
  position: absolute;
  inset: -10px -4px;
  border-radius: 999px;
}
.next-button:hover:not(:disabled) {
  background: rgba(255, 255, 255, .16);
}
.next-button:disabled {
  opacity: .45;
  cursor: default;
}
.next-button:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}
.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 12px;
}
.controls :deep(*) {
  font-size: 12px;
}
@media (max-width: 400px) {
  .playback-bottom {
    padding-inline: max(10px, env(safe-area-inset-left)) max(10px, env(safe-area-inset-right));
  }
  .legend {
    gap: 2px 10px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .progress-fill,
  .next-button {
    transition: none;
  }
}
</style>
