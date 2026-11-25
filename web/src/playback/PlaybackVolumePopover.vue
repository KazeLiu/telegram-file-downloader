<script setup lang="ts">
// 右上角音量面板：对齐参考站 `lE` 的五条滑杆（视频音量 / 节拍声 / 指令文字不透明度 / 指令文字大小 / 视频变暗程度）。
// 每行结构同参考站 `ah`：标题 + 右侧百分比，下面一条 step=5 的 range，再一行灰色说明。
import { computed } from 'vue'

const props = defineProps<{
  mediaVolume: number
  beatVolume: number
  beatVolumeMax: number
  textOpacity: number
  textScale: number
  textOpacityMin: number
  textScaleMin: number
  textScaleMax: number
  dim: number
}>()

type VolumeKey = 'mediaVolume' | 'beatVolume' | 'textOpacity' | 'textScale' | 'dim'

const emit = defineEmits<{ 'update': [payload: { key: VolumeKey; value: number }] }>()

const beatPercent = computed(() => Math.round((props.beatVolume / props.beatVolumeMax) * 100))

function onInput(key: VolumeKey, event: Event) {
  emit('update', { key, value: Number((event.target as HTMLInputElement).value) })
}
</script>

<template>
  <div class="sd-panel" data-sundome-volume-panel aria-label="音量">
    <label class="sd-row" data-sundome-volume-row="video">
      <span class="sd-head"><span class="sd-label">视频音量</span><b data-sundome-volume-value="video">{{ mediaVolume }}%</b></span>
      <input type="range" min="0" max="100" step="5" :value="mediaVolume" aria-label="视频音量" :aria-valuetext="`${mediaVolume}%`" data-sundome-volume="video" @input="onInput('mediaVolume', $event)">
      <span class="sd-note" data-sundome-volume-locked="play">iPhone、iPad 无法在页面上调整视频音量（机身音量键会同时调整所有声音）。请把节拍声调到100%以上来平衡</span>
    </label>
    <label class="sd-row" data-sundome-volume-row="beat">
      <span class="sd-head"><span class="sd-label">节拍声（节拍器）</span><b data-sundome-volume-value="beat">{{ beatPercent }}%</b></span>
      <input type="range" min="0" :max="beatVolumeMax" step="5" :value="beatVolume" aria-label="节拍声（节拍器）" :aria-valuetext="`${beatPercent}%`" data-sundome-volume="beat" @input="onInput('beatVolume', $event)">
      <span class="sd-note">100%=和以前一样。被视频声音盖过就调高（最高{{ beatVolumeMax }}%）</span>
    </label>
    <label class="sd-row" data-sundome-volume-row="text">
      <span class="sd-head"><span class="sd-label">指令文字不透明度</span><b data-sundome-volume-value="text">{{ textOpacity }}%</b></span>
      <input type="range" :min="textOpacityMin" max="100" step="5" :value="textOpacity" aria-label="指令文字不透明度" :aria-valuetext="`${textOpacity}%`" data-sundome-volume="text" @input="onInput('textOpacity', $event)">
      <span class="sd-note">视频上方的文字和周围暗色光晕的浓度。调低后能透过文字看到视频（{{ textOpacityMin }}～100%）</span>
    </label>
    <label class="sd-row" data-sundome-volume-row="size">
      <span class="sd-head"><span class="sd-label">指令文字大小</span><b data-sundome-volume-value="size">{{ textScale }}%</b></span>
      <input type="range" :min="textScaleMin" :max="textScaleMax" step="5" :value="textScale" aria-label="指令文字大小" :aria-valuetext="`${textScale}%`" data-sundome-volume="size" @input="onInput('textScale', $event)">
      <span class="sd-note">把视频上方的指令、口白和补充一起缩小。调低后能看到更多视频画面（{{ textScaleMin }}～{{ textScaleMax }}%）</span>
    </label>
    <label class="sd-row" data-sundome-volume-row="dim">
      <span class="sd-head"><span class="sd-label">视频变暗程度</span><b data-sundome-volume-value="dim">{{ dim }}%</b></span>
      <input type="range" min="0" max="100" step="5" :value="dim" aria-label="视频变暗程度" :aria-valuetext="`${dim}%`" data-sundome-volume="dim" @input="onInput('dim', $event)">
      <span class="sd-note">0%＝完全透明，不加暗色遮罩（视频原本的亮度）。100%＝和以前一样</span>
    </label>
  </div>
</template>

<style scoped>
.sd-panel {
  position: absolute;
  top: 52px; right: 12px;
  z-index: 90;
  width: min(288px, calc(100vw - 24px));
  padding: 4px 16px;
  border: 1px solid rgba(255, 255, 255, .15);
  border-radius: 12px;
  background: rgba(0, 0, 0, .95);
  color: #fff;
  text-align: left;
  box-shadow: 0 18px 42px rgba(0, 0, 0, .5);
}
.sd-row { display: block; padding: 12px 0; cursor: pointer; }
.sd-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.sd-label { min-width: 0; font-size: 14px; font-weight: 500; line-height: 20px; }
.sd-head b { flex: 0 0 auto; font-size: 12px; font-weight: 400; font-variant-numeric: tabular-nums; color: rgba(255, 255, 255, .7); }
/* 全局 input 的 46px 高度与描边都不适用于滑杆（参考站是 h-6 的无框 range）。 */
.sd-row input[type='range'] {
  display: block;
  width: 100%; min-width: 0;
  height: 24px; min-height: 0;
  margin-top: 8px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  cursor: pointer;
  accent-color: #5ee3a1;
}
.sd-note { display: block; margin-top: 2px; font-size: 12px; line-height: 1rem; color: rgba(255, 255, 255, .6); }
@media (min-width: 640px) { .sd-panel { right: 16px; } }
</style>
