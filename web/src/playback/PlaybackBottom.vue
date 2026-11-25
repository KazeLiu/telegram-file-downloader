<script setup lang="ts">
// 底栏：整局进度条 + 计时 + 三色图例 + 「换个视频」。
import { computed } from 'vue'
import Icon from '../Icon.vue'
import { modeColors, modeLabels, modeOrder } from './engine.ts'

const props = defineProps<{
  elapsed: string
  total: string
  progress: number
  allowed: boolean
  windowLeft: number
  hideTime: boolean
}>()

const emit = defineEmits<{ skip: [] }>()

const percent = computed(() => Math.min(1, Math.max(0, props.progress)))
const legend = computed(() => modeOrder.map(mode => ({ mode, label: modeLabels[mode], color: modeColors[mode] })))
</script>

<template>
  <div class="sd-bottombar">
    <div class="sd-progress-row">
      <div class="sd-track">
        <div class="sd-fill" :class="{ window: allowed }" data-sundome-session-bar :style="{ transform: `scaleX(${allowed ? Math.min(1, Math.max(0, percent)) : percent})`, background: allowed ? '#fff' : undefined }" />
      </div>
      <span class="sd-time" data-sundome-elapsed>{{ allowed ? `许可 ${windowLeft} 秒` : `${elapsed} / ${total}` }}</span>
    </div>
    <div class="sd-legend-row">
      <ul class="sd-legend">
        <li v-for="item in legend" :key="item.mode">
          <span class="sd-dot" :style="{ background: item.color }" />{{ item.label }}
        </li>
        <li v-if="!hideTime" class="sd-keys">Space 暂停 · E 忍住 · Esc 退出</li>
      </ul>
      <button class="sd-skip" type="button" data-sundome-video-skip @click="emit('skip')">
        <Icon name="refresh" :size="12" />换个视频
      </button>
    </div>
  </div>
</template>

<style scoped>
.sd-bottombar { padding: 0 16px 16px; padding-bottom: max(16px, env(safe-area-inset-bottom)); }
.sd-progress-row { display: flex; align-items: center; gap: 12px; }
.sd-track { flex: 1 1 auto; height: 8px; overflow: hidden; border-radius: 999px; background: rgba(255, 255, 255, .15); }
.sd-fill { width: 100%; height: 100%; border-radius: 999px; transform-origin: left center; background: #5ee3a1; transition: transform .25s linear, background .3s ease; }
.sd-fill.window { box-shadow: 0 0 12px rgba(255, 255, 255, .8); }
.sd-time { flex: none; font-size: 11px; color: rgba(255, 255, 255, .6); font-variant-numeric: tabular-nums; }
.sd-legend-row { margin-top: 12px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.sd-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; margin: 0; padding: 0; list-style: none; font-size: 11px; color: rgba(255, 255, 255, .6); }
.sd-legend li { display: inline-flex; align-items: center; gap: 4px; }
.sd-dot { display: inline-block; width: 10px; height: 10px; flex: none; border-radius: 999px; }
.sd-keys { display: none; }
.sd-skip {
  display: inline-flex; flex: none; align-items: center; gap: 6px;
  min-height: 0; padding: 4px 10px;
  border: 1px solid rgba(255, 255, 255, .3); border-radius: 999px;
  background: rgba(255, 255, 255, .1); color: rgba(255, 255, 255, .85);
  font-size: 11px; font-weight: 500; cursor: pointer;
}
.sd-skip:hover { background: rgba(255, 255, 255, .2); }
@media (min-width: 640px) { .sd-keys { display: inline-flex; } .sd-legend { gap: 4px 16px; } }
</style>
