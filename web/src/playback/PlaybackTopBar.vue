<script setup lang="ts">
import type { PlaybackPosition } from './types'

defineProps<{
  name: string
  position: PlaybackPosition
  remaining: string
  hideTime: boolean
  paused: boolean
  playing: boolean
  /** 忍住次数（寸止玩法的主计数），替代原来的喜欢计数。 */
  held: number
  noCrop: boolean
  pipAvailable: boolean
  landscapeAvailable: boolean
  volumeOpen: boolean
  fullscreen: boolean
}>()

defineEmits<{
  toggleCrop: []
  pip: []
  volume: []
  landscape: []
  fullscreen: []
  togglePause: []
  exit: []
}>()
</script>

<template>
  <header class="playback-top" :title="name">
    <div class="top-left">
      <span class="item-count">第 {{ position.index + 1 }} / {{ position.total }} 项</span>
      <time v-if="!hideTime && remaining" class="remaining" aria-label="剩余时间">{{ remaining }}</time>
      <span class="held-count" aria-label="忍住次数">忍住 {{ held }}</span>
    </div>

    <div class="top-right">
      <button
        class="icon-button"
        type="button"
        :aria-label="noCrop ? '铺满屏幕（会裁切）' : '显示完整画面（不裁切）'"
        :aria-pressed="noCrop"
        :class="{ active: noCrop }"
        @click="$emit('toggleCrop')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9 4H4v5M15 4h5v5M15 20h5v-5M9 20H4v-5" />
        </svg>
      </button>
      <button
        class="icon-button"
        type="button"
        aria-label="悬浮窗（边浏览其他网页边玩）"
        :disabled="!pipAvailable"
        @click="$emit('pip')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <rect x="12" y="12" width="7" height="5" rx="1" />
        </svg>
      </button>
      <button
        class="icon-button"
        type="button"
        aria-label="音量"
        :aria-expanded="volumeOpen"
        :class="{ active: volumeOpen }"
        @click="$emit('volume')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 10v4h3l4 3V7L7 10H4Z" />
          <path d="M15 9.5a3.5 3.5 0 0 1 0 5M17.5 7a7 7 0 0 1 0 10" />
        </svg>
      </button>
      <button
        v-if="landscapeAvailable"
        class="icon-button"
        type="button"
        aria-label="横屏"
        @click="$emit('landscape')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M5 9a8 8 0 0 1 13-3.5M19 15a8 8 0 0 1-13 3.5" />
          <path d="M18 3v4h-4M6 21v-4h4" />
        </svg>
      </button>
      <button
        v-if="fullscreen"
        class="icon-button desktop-only"
        type="button"
        aria-label="全屏"
        @click="$emit('fullscreen')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 9V4h5M20 9V4h-5M20 15v5h-5M4 15v5h5" />
        </svg>
      </button>

      <button
        class="pill-button"
        type="button"
        :disabled="!playing"
        :aria-label="paused ? '继续' : '暂停'"
        @click="$emit('togglePause')"
      >{{ paused ? '继续' : '暂停' }}</button>
      <button class="pill-button" type="button" aria-label="退出" @click="$emit('exit')">退出</button>
    </div>
  </header>
</template>

<style scoped>
.playback-top {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 48px;
  padding: 6px max(10px, env(safe-area-inset-right)) 6px max(10px, env(safe-area-inset-left));
  color: #fff;
  pointer-events: auto;
  background: linear-gradient(180deg, rgba(0, 0, 0, .72), rgba(0, 0, 0, 0));
}
.top-left {
  display: flex;
  flex: 1;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.item-count {
  overflow: hidden;
  max-width: 40%;
  color: rgba(255, 255, 255, .72);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.remaining {
  color: #fff;
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
  white-space: nowrap;
}
.held-count {
  color: rgba(255, 255, 255, .72);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.top-right {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 6px;
}
.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  color: #fff;
  background: rgba(255, 255, 255, .12);
}
.icon-button:hover:not(:disabled) { background: rgba(255, 255, 255, .24); }
.icon-button:disabled { opacity: .35; }
.icon-button.active { background: rgba(53, 214, 164, .28); color: #8ff0cd; }
.icon-button svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.8;
}
.pill-button {
  min-width: 46px;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  color: #fff;
  font-size: 13px;
  background: rgba(0, 0, 0, .72);
  transition: background .15s;
}
.pill-button:hover:not(:disabled) { background: #272729; }
.pill-button:disabled { opacity: .4; }
.icon-button:focus-visible,
.pill-button:focus-visible {
  outline: 2px solid var(--color-primary-on-dark);
  outline-offset: 2px;
}
@media (max-width: 560px) {
  .playback-top { gap: 6px; }
  .top-left { gap: 8px; }
  .top-right { gap: 4px; }
  .icon-button { width: 30px; height: 30px; }
  .remaining { font-size: 18px; }
  .item-count { max-width: 30%; }
}
@media (max-width: 400px) {
  .held-count { display: none; }
  .item-count { max-width: 34%; }
}
@media (min-width: 900px) {
  .desktop-only { display: inline-flex; }
}
</style>
