<script setup lang="ts">
// 右上角音量面板：对齐参考站的四条滑杆（视频音量 / 节拍声 / 指令文字不透明度 / 指令文字大小）。
import { computed } from 'vue'

const props = defineProps<{
  mediaVolume: number
  beatVolume: number
  beatVolumeMax: number
  textOpacity: number
  textScale: number
  textOpacityMin: number
  textScaleMin: number
}>()

type VolumeKey = 'mediaVolume' | 'beatVolume' | 'textOpacity' | 'textScale'

const emit = defineEmits<{ 'update': [payload: { key: VolumeKey; value: number }] }>()

const beatPercent = computed(() => Math.round((props.beatVolume / props.beatVolumeMax) * 100))

function onInput(key: VolumeKey, event: Event) {
  emit('update', { key, value: Number((event.target as HTMLInputElement).value) })
}
</script>

<template>
  <div class="sd-panel" data-sundome-volume-panel>
    <label class="sd-row">
      <span>视频音量</span>
      <input type="range" min="0" max="100" :value="mediaVolume" @input="onInput('mediaVolume', $event)">
      <b>{{ mediaVolume }}%</b>
    </label>
    <p class="sd-note">iPhone、iPad 无法在页面上调整视频音量（机身音量键会同时调整所有声音）。请把节拍声调到 100% 以上来平衡。</p>
    <label class="sd-row">
      <span>节拍声</span>
      <input type="range" min="0" :max="beatVolumeMax" :value="beatVolume" @input="onInput('beatVolume', $event)">
      <b>{{ beatPercent }}%</b>
    </label>
    <p class="sd-note">100% = 和以前一样。被视频声音盖过就调高（最高 300%）。</p>
    <label class="sd-row">
      <span>文字浓度</span>
      <input type="range" :min="textOpacityMin" max="100" :value="textOpacity" @input="onInput('textOpacity', $event)">
      <b>{{ textOpacity }}%</b>
    </label>
    <p class="sd-note">视频上方的文字和周围暗色光晕的浓度。调低后能透过文字看到视频（{{ textOpacityMin }}～100%）。</p>
    <label class="sd-row">
      <span>文字大小</span>
      <input type="range" :min="textScaleMin" max="140" :value="textScale" @input="onInput('textScale', $event)">
      <b>{{ textScale }}%</b>
    </label>
    <p class="sd-note">把视频上方的指令、口白和补充一起缩小。调低后能看到更多视频画面（{{ textScaleMin }}～140%）。</p>
  </div>
</template>

<style scoped>
.sd-panel {
  position: absolute;
  top: 52px; right: 12px;
  z-index: 90;
  width: min(288px, calc(100vw - 24px));
  padding: 4px 16px 10px;
  border: 1px solid rgba(255, 255, 255, .15);
  border-radius: 12px;
  background: rgba(0, 0, 0, .95);
  color: #fff;
  text-align: left;
  box-shadow: 0 18px 42px rgba(0, 0, 0, .5);
}
.sd-row {
  display: grid;
  grid-template-columns: 72px 1fr 44px;
  align-items: center;
  gap: 10px;
  padding: 8px 0 0;
  font-size: 12px;
}
.sd-row span { color: rgba(255, 255, 255, .78); }
.sd-row b { font-weight: 700; font-variant-numeric: tabular-nums; text-align: right; }
.sd-row input[type='range'] { width: 100%; accent-color: #5ee3a1; }
.sd-note { margin: 2px 0 6px; font-size: 10.5px; line-height: 1.45; color: rgba(255, 255, 255, .45); }
@media (min-width: 640px) { .sd-panel { right: 16px; } }
</style>
