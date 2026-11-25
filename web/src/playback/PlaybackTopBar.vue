<script setup lang="ts">
// 顶栏：左边第几条指令 + 忍住次数，中间剩余时间，右边一排圆形/胶囊按钮。
import { computed } from 'vue'
import Icon from '../Icon.vue'
import type { PlaybackPosition } from './types.ts'

const props = defineProps<{
  name: string
  position: PlaybackPosition
  remaining: string
  hideTime: boolean
  paused: boolean
  playing: boolean
  held: number
  noCrop: boolean
  align: 'top' | 'center' | 'bottom'
  pipAvailable: boolean
  landscapeAvailable: boolean
  volumeOpen: boolean
  fullscreen: boolean
  note: string
}>()

const positionLabel = computed(() => ({ top: '上', center: '中', bottom: '下' } as Record<string, string>)[props.align] ?? '中')

const emit = defineEmits<{
  'toggle-crop': []
  'cycle-position': []
  'pip': []
  'volume': []
  'landscape': []
  'fullscreen': []
  'toggle-pause': []
  'exit': []
}>()
</script>

<template>
  <div class="sd-topbar">
    <div class="sd-left">
      <span class="sd-count" data-sundome-count>{{ note || (position.index + 1 ? `第 ${position.index + 1} 条指令` : '准备中') }}</span>
      <span v-if="held" class="sd-held">忍住 {{ held }}</span>
    </div>
    <span v-if="!hideTime && remaining" class="sd-clock" data-sundome-clock>{{ remaining }}</span>
    <div class="sd-buttons">
      <button class="sd-icon" type="button" data-sundome-fit-toggle :title="noCrop ? '铺满屏幕' : '完整显示'" :aria-label="noCrop ? '铺满屏幕' : '完整显示'" @click="emit('toggle-crop')">
        <Icon :name="noCrop ? 'expand' : 'shrink'" :size="14" />
      </button>
      <button v-if="noCrop" class="sd-icon" type="button" data-sundome-pos-toggle :data-pos="align" :title="`显示位置：${positionLabel}`" :aria-label="`显示位置：${positionLabel}`" @click="emit('cycle-position')">
        <Icon name="position" :size="14" />
      </button>
      <button v-if="pipAvailable" class="sd-icon" type="button" data-sundome-pip-toggle data-sundome-pip="1" title="悬浮窗" aria-label="悬浮窗" @click="emit('pip')">
        <Icon name="pip" :size="14" />
      </button>
      <button class="sd-icon" :class="{ on: volumeOpen }" data-sundome-volume-toggle type="button" title="声音" aria-label="声音" @click="emit('volume')">
        <Icon name="volume" :size="14" />
      </button>
      <button v-if="landscapeAvailable" class="sd-icon sd-wide" type="button" data-sundome-landscape title="横屏" aria-label="横屏" @click="emit('landscape')">
        <Icon name="rotate" :size="14" />
      </button>
      <button class="sd-pill" type="button" data-sundome-fullscreen @click="emit('fullscreen')">{{ fullscreen ? '退出全屏' : '全屏' }}</button>
      <button class="sd-pill" type="button" data-sundome-pause :disabled="!playing" @click="emit('toggle-pause')">{{ paused ? '继续' : '暂停' }}</button>
      <button class="sd-pill" type="button" data-sundome-quit @click="emit('exit')">退出</button>
    </div>
  </div>
</template>

<style scoped>
.sd-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 16px 0;
  padding-top: max(12px, env(safe-area-inset-top));
  font-size: 14px;
}
.sd-left { display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1 1 auto; }
.sd-count { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 16px; font-weight: 800; font-style: italic; color: rgba(255, 255, 255, .7); }
.sd-held { flex: none; font-style: normal; color: rgba(255, 255, 255, .5); }
.sd-clock { flex: none; font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
.sd-buttons { display: flex; flex: none; align-items: center; gap: 6px; }
.sd-icon {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; min-height: 0; padding: 0;
  border: 1px solid rgba(255, 255, 255, .25); border-radius: 999px;
  background: transparent; color: rgba(255, 255, 255, .8); cursor: pointer;
  transition: background .15s ease, color .15s ease;
}
.sd-icon:hover { background: rgba(255, 255, 255, .1); }
.sd-icon.on { background: rgba(255, 255, 255, .2); color: #fff; }
.sd-wide { width: auto; padding: 0 8px; }
.sd-pill {
  min-height: 0; height: 30px; padding: 0 12px;
  display: inline-flex; align-items: center;
  border: 1px solid rgba(255, 255, 255, .25); border-radius: 999px;
  background: transparent; color: rgba(255, 255, 255, .8);
  font-size: 12px; font-weight: 500; cursor: pointer;
  transition: background .15s ease;
}
.sd-pill:hover { background: rgba(255, 255, 255, .1); }
.sd-pill:disabled { opacity: .4; cursor: default; }
@media (max-width: 520px) {
  .sd-topbar { padding: 8px 8px 0; gap: 6px; }
  .sd-count { font-size: 14px; }
  .sd-clock { font-size: 16px; }
  .sd-icon { width: 24px; height: 24px; }
  .sd-pill { height: 26px; padding: 0 8px; font-size: 11px; }
}
@media (max-width: 400px) { .sd-held { display: none; } }
</style>
