<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { GuideStep } from './types'

const props = defineProps<{ steps: GuideStep[]; open: boolean }>()

const emit = defineEmits<{ close: [skipped: boolean] }>()

const current = ref(0)
const card = ref<HTMLElement>()

const total = computed(() => props.steps.length)
const active = computed<GuideStep>(() => props.steps[Math.min(current.value, Math.max(0, total.value - 1))] ?? { title: '', body: '' })
const last = computed(() => total.value > 0 && current.value >= total.value - 1)
const canBack = computed(() => current.value > 0)

function go(delta: number) {
  const next = current.value + delta
  current.value = Math.min(Math.max(0, next), Math.max(0, total.value - 1))
}

function finish(skipped: boolean) {
  emit('close', skipped)
}

/** Esc 跳过，左右方向键翻页；只在本卡打开期间挂在 window 上。 */
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    finish(true)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    go(1)
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    go(-1)
  }
}

watch(
  () => props.open,
  async open => {
    if (typeof window === 'undefined') return
    if (!open) {
      window.removeEventListener('keydown', onKeydown)
      return
    }
    current.value = 0
    window.addEventListener('keydown', onKeydown)
    await nextTick()
    card.value?.focus()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div v-if="open && active" class="playback-guide">
    <section
      ref="card"
      class="guide-card"
      role="dialog"
      aria-modal="true"
      aria-labelledby="playback-guide-title"
      tabindex="-1"
    >
      <p class="guide-count">{{ current + 1 }} / {{ total }}</p>
      <h2 id="playback-guide-title" class="guide-title">{{ active.title }}</h2>
      <p class="guide-body">{{ active.body }}</p>
      <div class="guide-actions">
        <button type="button" class="guide-skip" @click="finish(true)">跳过</button>
        <div class="guide-steps">
          <button v-if="canBack" type="button" class="secondary" @click="go(-1)">上一步</button>
          <button v-if="last" type="button" class="primary" @click="finish(false)">开始</button>
          <button v-else type="button" class="primary" @click="go(1)">下一步</button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.playback-guide {
  position: fixed;
  inset: 0;
  z-index: 64;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(0, 0, 0, .72);
}
.guide-card {
  width: min(520px, 100%);
  padding: 26px 26px 22px;
  border-radius: var(--radius-panel);
  background: var(--color-canvas);
  color: var(--color-ink);
  box-shadow: 0 20px 52px rgba(0, 0, 0, .34);
}
.guide-card:focus-visible {
  outline: 2px solid var(--color-primary-focus);
  outline-offset: 3px;
}
.guide-count {
  color: var(--color-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  letter-spacing: .08em;
}
.guide-title {
  margin: 8px 0 12px;
  font-size: 21px;
  font-weight: 600;
}
.guide-body {
  color: var(--color-supporting);
  font-size: 15px;
  line-height: 1.7;
}
.guide-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 26px;
}
.guide-skip {
  min-width: 44px;
  min-height: 44px;
  padding: 8px 12px;
  border-radius: 10px;
  color: var(--color-muted);
  font-size: 14px;
}
.guide-skip:hover { background: var(--color-soft); }
.guide-skip:focus-visible,
.guide-steps button:focus-visible {
  outline: 2px solid var(--color-primary-focus);
  outline-offset: 2px;
}
.guide-steps {
  display: flex;
  gap: 10px;
}
.guide-steps button {
  min-height: 44px;
  min-width: 44px;
}
@media (max-width: 480px) {
  .guide-card { padding: 22px 20px 18px; }
  .guide-actions { flex-direction: column-reverse; align-items: stretch; }
  .guide-steps { flex-direction: column; }
  .guide-steps button { width: 100%; }
  .guide-skip { align-self: flex-start; }
}
</style>
