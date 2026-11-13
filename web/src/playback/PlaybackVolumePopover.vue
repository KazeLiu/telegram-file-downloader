<script setup lang="ts">
const props = defineProps<{
  open: boolean
  mediaVolume: number
  beatVolume: number
  speechVolume: number
  brightness: number
}>()

const emit = defineEmits<{
  close: []
  change: [payload: { key: 'mediaVolume' | 'beatVolume' | 'speechVolume' | 'brightness'; value: number }]
  openSettings: []
}>()

type VolumeKey = 'mediaVolume' | 'beatVolume' | 'speechVolume' | 'brightness'

function onInput(key: VolumeKey, event: Event) {
  const target = event.target as HTMLInputElement | null
  if (!target) return
  const value = Number(target.value)
  if (!Number.isFinite(value)) return
  emit('change', { key, value })
}

const rows: { key: VolumeKey; label: string; min: number; hint?: string }[] = [
  { key: 'mediaVolume', label: '视频音量', min: 0 },
  { key: 'beatVolume', label: '节拍声（节拍器）', min: 0, hint: '100% ＝ 和以前一样。被视频声音盖过就调高。' },
  { key: 'speechVolume', label: '语音音量', min: 0 },
  { key: 'brightness', label: '视频变暗程度', min: 20, hint: '20% 最暗，100% ＝ 完全透明不变暗。' },
]

function readValue(key: VolumeKey): number {
  return props[key]
}
</script>

<template>
  <div v-if="open" class="volume-layer">
    <button class="volume-backdrop" type="button" aria-label="关闭音量设置" @click="$emit('close')"></button>
    <section class="volume-card" role="dialog" aria-label="音量与画面">
      <div class="volume-head">
        <h3>音量与画面</h3>
        <button class="close-button" type="button" aria-label="关闭" @click="$emit('close')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>

      <label v-for="row in rows" :key="row.key" class="volume-row">
        <span class="row-label">
          <span>{{ row.label }}</span>
          <strong>{{ readValue(row.key) }}%</strong>
        </span>
        <input
          class="slider"
          type="range"
          :min="row.min"
          max="100"
          step="1"
          :value="readValue(row.key)"
          :aria-label="row.label"
          @input="onInput(row.key, $event)"
        />
        <span v-if="row.hint" class="row-hint">{{ row.hint }}</span>
      </label>

      <button class="settings-link" type="button" @click="$emit('openSettings')">打开播放设置</button>
    </section>
  </div>
</template>

<style scoped>
.volume-layer {
  position: fixed;
  inset: 0;
  z-index: 66;
  pointer-events: none;
}
.volume-backdrop {
  position: absolute;
  inset: 0;
  pointer-events: auto;
  background: radial-gradient(120% 90% at 70% 0%, rgba(0, 0, 0, .28), rgba(0, 0, 0, .58));
  border: 0;
}
.volume-card {
  position: absolute;
  top: calc(52px + env(safe-area-inset-top));
  right: max(12px, env(safe-area-inset-right));
  width: min(320px, calc(100vw - 24px));
  max-height: min(70dvh, 460px);
  padding: 14px 16px 12px;
  overflow-y: auto;
  pointer-events: auto;
  color: #fff;
  background: rgba(18, 18, 20, .97);
  border: 1px solid rgba(255, 255, 255, .12);
  border-radius: 16px;
  box-shadow: 0 18px 48px rgba(0, 0, 0, .55);
}
.volume-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.volume-head h3 { margin: 0; font-size: 15px; font-weight: 600; }
.close-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  color: rgba(255, 255, 255, .72);
}
.close-button:hover { background: rgba(255, 255, 255, .12); color: #fff; }
.close-button svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-width: 1.8;
}
.volume-row {
  display: block;
  padding: 8px 0;
  border-top: 1px solid rgba(255, 255, 255, .08);
}
.row-label {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  color: rgba(255, 255, 255, .86);
}
.row-label strong { font-variant-numeric: tabular-nums; font-size: 12px; color: #8ff0cd; }
.slider {
  width: 100%;
  margin: 6px 0 2px;
  accent-color: #35d6a4;
}
.row-hint { display: block; color: rgba(255, 255, 255, .5); font-size: 11px; line-height: 1.5; }
.settings-link {
  width: 100%;
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  color: #fff;
  font-size: 13px;
  background: rgba(255, 255, 255, .1);
}
.settings-link:hover { background: rgba(255, 255, 255, .18); }
.slider:focus-visible,
.settings-link:focus-visible {
  outline: 2px solid var(--color-primary-on-dark);
  outline-offset: 2px;
}
</style>
