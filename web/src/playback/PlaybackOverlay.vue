<script setup lang="ts">
// 播放层骨架：底色 → 模式光晕 → 媒体 → 顶栏 / 中央 / 底栏。
// 视觉对齐参考实现：整层固定满屏、四层背景、中央文字自带 radial 底衬与黑色投影。
import { computed } from 'vue'
import { modeColors, type EdgeMode } from './engine.ts'

const props = defineProps<{
  mode: EdgeMode
  dim: number
  opacity: number
  scale: number
}>()

/** 把十六进制色转成 rgba 字符串，供四层 radial-gradient 复用。 */
function rgba(hex: string, alpha: number) {
  const value = hex.replace('#', '')
  const full = value.length === 3 ? value.split('').map(char => char + char).join('') : value
  const r = parseInt(full.slice(0, 2), 16)
  const g = parseInt(full.slice(2, 4), 16)
  const b = parseInt(full.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

const color = computed(() => modeColors[props.mode])
const glow = computed(() => {
  const tint = color.value
  return [
    `radial-gradient(110% 60% at 50% 0%, ${rgba(tint, 0.7)}, rgba(0, 0, 0, 0) 72%)`,
    `radial-gradient(110% 55% at 50% 100%, ${rgba(tint, 0.55)}, rgba(0, 0, 0, 0) 72%)`,
    `radial-gradient(70% 50% at 0% 50%, ${rgba(tint, 0.24)}, rgba(0, 0, 0, 0) 72%)`,
    `radial-gradient(70% 50% at 100% 50%, ${rgba(tint, 0.24)}, rgba(0, 0, 0, 0) 72%)`,
  ].join(', ')
})
/**
 * 遮罩浓度对齐参考站：无遮罩=原亮度，最暗=rgba(0,0,0,.45)。
 * 我们的 brightness 越小越暗（20 最暗、100 完全透明），参考站是 dim 越大越暗，这里做线性映射。
 */
const mask = computed(() => {
  const level = Math.min(100, Math.max(0, props.dim))
  return Math.min(0.45, (0.45 * (100 - level)) / 80)
})
</script>

<template>
  <div class="sd-stage">
    <div class="sd-base" />
    <div class="sd-glow" :style="{ backgroundImage: glow }" />
    <div class="sd-media">
      <slot name="media" />
      <div class="sd-mask" data-sundome-video-shade :style="{ backgroundColor: `rgba(0, 0, 0, ${mask.toFixed(3)})` }" />
    </div>
    <div class="sd-top"><slot name="top" /></div>
    <div class="sd-center" :style="{ '--sd-text-opacity': String(opacity / 100), '--sd-text-scale': String(scale / 100) }">
      <div class="sd-center-inner"><slot /></div>
    </div>
    <div class="sd-bottom"><slot name="bottom" /></div>
  </div>
</template>

<style scoped>
.sd-stage {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  flex-direction: column;
  color: #fff;
  overflow: hidden;
  background: #0a0708;
  -webkit-tap-highlight-color: transparent;
}
.sd-base { position: absolute; inset: 0; z-index: 0; background: #0a0708; }
.sd-glow {
  position: absolute;
  inset: 0;
  z-index: 0;
  transition: background-image .8s ease;
  opacity: .92;
}
.sd-media {
  position: absolute;
  inset: 0;
  z-index: 1;
  overflow: hidden;
  background: #000;
  pointer-events: none;
}
.sd-mask { position: absolute; inset: 0; transition: background-color .3s ease; }
.sd-top { position: relative; z-index: 10; flex: none; }
.sd-center {
  position: relative;
  z-index: 10;
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
  text-align: center;
  padding: 0 24px;
  background: radial-gradient(70% 55% at 50% 50%, rgba(0, 0, 0, .6), rgba(0, 0, 0, 0) 100%);
  text-shadow: 0 2px 18px rgba(0, 0, 0, .95), 0 0 6px rgba(0, 0, 0, .9);
}
.sd-center-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  opacity: var(--sd-text-opacity, 1);
  transform: scale(var(--sd-text-scale, 1));
  transition: opacity .2s ease, transform .2s ease;
}
.sd-bottom { position: relative; z-index: 10; flex: none; }
</style>
