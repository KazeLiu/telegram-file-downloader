<script setup lang="ts">
// 玩法引导：第一次进入播放器时按步演示，Esc 跳过。样式与属性对齐参考站（深色卡片 + 聚光灯挖洞）。
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { GuideStep } from './types'

const props = defineProps<{ steps: GuideStep[]; open: boolean; anchor?: (step: number) => Element | null }>()
const emit = defineEmits<{ close: [skipped: boolean] }>()

const current = ref(0)
const card = ref<HTMLElement>()
const spot = ref<{ left: number; top: number; width: number; height: number } | null>(null)
const cardStyle = ref<Record<string, string>>({})
const total = computed(() => props.steps.length)
const active = computed<GuideStep>(() => props.steps[Math.min(current.value, Math.max(0, total.value - 1))] ?? { title: '', body: '' })
const last = computed(() => current.value >= total.value - 1)
const canBack = computed(() => current.value > 0)

function finish(skipped: boolean) {
  emit('close', skipped)
}

function go(delta: number) {
  const next = current.value + delta
  if (next < 0) return
  if (next > total.value - 1) {
    finish(false)
    return
  }
  current.value = next
}

function measure() {
  const target = props.anchor?.(current.value) ?? null
  const rect = target?.getBoundingClientRect() ?? null
  if (!rect || rect.width < 8 || rect.height < 8) {
    spot.value = null
    cardStyle.value = {}
    return
  }
  spot.value = { left: rect.left, top: rect.top, width: rect.width, height: rect.height }
  // 卡片贴在目标下方；下方放不下就贴上方；目标几乎占满屏幕时回到居中。
  const view = { w: window.innerWidth, h: window.innerHeight }
  const tall = rect.height > view.h * 0.6
  if (tall) {
    cardStyle.value = { left: '50%', bottom: '16px', top: 'auto', transform: 'translateX(-50%)' }
    return
  }
  const below = rect.bottom + 14
  const cardHeight = card.value?.offsetHeight ?? 200
  if (below + cardHeight < view.h - 12) {
    cardStyle.value = { left: '50%', top: `${Math.round(below)}px`, bottom: 'auto', transform: 'translateX(-50%)' }
  } else {
    cardStyle.value = { left: '50%', top: 'auto', bottom: `${Math.round(view.h - rect.top + 14)}px`, transform: 'translateX(-50%)' }
  }
}

function keydown(event: KeyboardEvent) {
  if (!props.open) return
  if (event.key === 'Escape') {
    event.preventDefault()
    finish(true)
    return
  }
  if (event.key === 'ArrowRight') {
    event.preventDefault()
    go(1)
    return
  }
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    go(-1)
  }
}

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    current.value = 0
    await nextTick()
    measure()
    card.value?.focus()
  },
)

watch(current, async () => {
  await nextTick()
  measure()
  card.value?.focus()
})

onMounted(() => {
  window.addEventListener('keydown', keydown)
  window.addEventListener('resize', measure)
  if (props.open) {
    void nextTick(() => {
      measure()
      card.value?.focus()
    })
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', keydown)
  window.removeEventListener('resize', measure)
})
</script>

<template>
  <div
    v-if="open && active"
    class="sd-guide"
    :data-sundome-guide="current + 1"
    :data-sundome-guide-step="current + 1"
    :data-sundome-guide-total="total"
    data-sundome-no-seek
    role="dialog"
    aria-modal="true"
    :aria-label="active.title"
    @click="go(1)"
    @pointerdown.stop
    @pointerup.stop
    @touchend.stop
  >
    <div
      class="sd-spot"
      aria-hidden="true"
      :class="{ 'sd-spot-on': Boolean(spot) }"
      :style="
        spot
          ? {
              left: `${spot.left}px`,
              top: `${spot.top}px`,
              width: `${spot.width}px`,
              height: `${spot.height}px`,
              boxShadow: '0 0 0 9999px rgba(8, 5, 7, .8), 0 0 0 2px rgba(255, 255, 255, .95), 0 0 18px 2px rgba(255, 255, 255, .35)',
            }
          : { boxShadow: '0 0 0 9999px rgba(8, 5, 7, .8)' }
      "
    />
    <section
      ref="card"
      class="sd-card"
      :data-sundome-guide-card="''"
      :style="cardStyle"
      tabindex="-1"
      @click.stop
    >
      <p class="sd-count" data-sundome-guide-count>{{ current + 1 }} / {{ total }}</p>
      <h2 class="sd-title" data-sundome-guide-title>{{ active.title }}</h2>
      <p class="sd-body" data-sundome-guide-body>{{ active.body }}</p>
      <div class="sd-actions">
        <button v-if="!last" type="button" class="sd-skip" data-sundome-guide-skip @click="finish(true)">跳过</button>
        <span v-else />
        <div class="sd-next-group">
          <button v-if="canBack" type="button" class="sd-back" @click="go(-1)">上一步</button>
          <button type="button" class="sd-next" data-sundome-guide-next @click="go(1)">{{ last ? '开始' : '下一步' }}</button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.sd-guide {
  position: fixed;
  inset: 0;
  z-index: 64;
  cursor: pointer;
  user-select: none;
}
.sd-spot {
  position: absolute;
  border-radius: 12px;
  transition: all .3s ease-out;
  pointer-events: none;
}
.sd-card {
  position: absolute;
  left: 50%;
  bottom: 24px;
  top: auto;
  width: min(420px, calc(100vw - 24px));
  max-height: min(60vh, 380px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 16px;
  border: 1px solid rgba(255, 255, 255, .15);
  border-radius: 16px;
  background: #1c1519;
  color: #fff;
  text-align: left;
  transform: translateX(-50%);
  box-shadow: 0 24px 60px rgba(0, 0, 0, .55);
  animation: sd-fade-in .25s ease both;
  cursor: default;
}
.sd-card:focus-visible {
  outline: 2px solid rgba(255, 255, 255, .6);
  outline-offset: 2px;
}
.sd-count {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .2em;
  color: rgba(255, 255, 255, .5);
  font-variant-numeric: tabular-nums;
}
.sd-title {
  margin: 4px 0 0;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.35;
  text-wrap: balance;
  word-break: auto-phrase;
}
.sd-body {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: rgba(255, 255, 255, .8);
  word-break: auto-phrase;
}
.sd-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
}
.sd-skip {
  min-height: 0;
  padding: 8px 4px;
  border-radius: 999px;
  color: rgba(255, 255, 255, .55);
  font-size: 13px;
  text-decoration: underline;
  text-underline-offset: 4px;
  background: none;
  cursor: pointer;
}
.sd-skip:hover { color: #fff; }
.sd-next-group {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
.sd-back {
  min-height: 0;
  padding: 8px 14px;
  border: 1px solid rgba(255, 255, 255, .3);
  border-radius: 999px;
  color: rgba(255, 255, 255, .85);
  font-size: 13px;
  background: none;
  cursor: pointer;
}
.sd-back:hover { background: rgba(255, 255, 255, .1); }
.sd-next {
  min-height: 0;
  padding: 8px 20px;
  border-radius: 999px;
  background: #fff;
  color: #000;
  font-size: 14px;
  font-weight: 700;
  white-space: nowrap;
  cursor: pointer;
}
.sd-next:hover { background: rgba(255, 255, 255, .9); }
@keyframes sd-fade-in {
  0% { opacity: 0; transform: translate(-50%, 8px); }
  100% { opacity: 1; transform: translate(-50%, 0); }
}
@media (min-width: 640px) {
  .sd-card { padding: 20px; }
  .sd-title { font-size: 18px; }
  .sd-body { font-size: 15px; }
}
</style>
