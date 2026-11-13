<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { phaseLabels, type PhaseKind } from './types'

const props = defineProps<{
  phase: PhaseKind
  bpm: number
  paused: boolean
  finished: boolean
  loading: boolean
  error: string
  hint: string
  progress: number
  likeLabel: string
  likeCount: number
  likeActive: boolean
  canLike: boolean
}>()

const emit = defineEmits<{
  like: []
  skip: []
}>()

/** 阶段色调：慢速琥珀、快速青绿、休息玫红；暂停时统一换成青绿。 */
const phaseTones: Record<PhaseKind, string> = { slow: '#e6b34a', fast: '#35d6a4', rest: '#f2637c' }

/** 操作说明是否展开：只在暂停时可开，恢复播放自动收起。 */
const helpOpen = ref(false)
watch(
  () => props.paused,
  (paused) => {
    if (!paused) helpOpen.value = false
  },
)

const tone = computed(() => (props.paused ? phaseTones.fast : phaseTones[props.phase]))
const pillLabel = computed(() => (props.finished ? '已结束' : props.paused ? '已暂停' : phaseLabels[props.phase]))
const showBpm = computed(() => props.bpm > 0 && !props.paused && !props.finished)
const hasError = computed(() => !!props.error)
const showProgress = computed(() => Number.isFinite(props.progress) && props.progress > 0)
const progressValue = computed(() => (Number.isFinite(props.progress) ? Math.min(100, Math.max(0, props.progress)) : 0))
/** 暂停、出错、加载中或不允许喜欢时主按钮不可点。 */
const mainDisabled = computed(() => !props.canLike || props.paused || hasError.value || props.loading)
const showHelp = computed(() => props.paused && !hasError.value)
const showLikes = computed(() => props.likeCount > 0 && !hasError.value)
</script>

<template>
  <div class="playback-stage" :style="{ '--tone': tone }">
    <!-- 媒体内容固定在最底层，不参与中央竖排的排版 -->
    <div class="stage-media" :class="{ covered: hasError }">
      <slot />
    </div>

    <div class="stage-center">
      <p v-if="!hasError" class="stage-pills" role="status">
        <span class="phase-pill">{{ pillLabel }}</span>
        <template v-if="showBpm">
          <span class="pill-dot" aria-hidden="true"></span>
          <span class="stage-bpm">{{ bpm }} BPM</span>
        </template>
      </p>

      <p v-if="loading" class="stage-loading" role="status">正在加载…</p>
      <p v-else-if="hasError" class="stage-error" role="alert">{{ error }}</p>
      <p v-else class="stage-hint">{{ hint }}</p>

      <div
        v-if="showProgress"
        class="stage-progress"
        role="progressbar"
        aria-label="本次播放进度"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-valuenow="Math.round(progressValue)"
      >
        <span class="stage-progress-fill" :style="{ width: `${progressValue}%` }"></span>
      </div>

      <div v-if="hasError" class="stage-actions">
        <slot name="actions" />
      </div>
      <template v-else>
        <button
          v-if="!loading"
          class="stage-main"
          type="button"
          :disabled="mainDisabled"
          :aria-pressed="likeActive ? 'true' : 'false'"
          @click="emit('like')"
        >
          {{ likeLabel }}
        </button>
        <p v-if="!loading && showLikes" class="stage-likes">已喜欢 {{ likeCount }} 次</p>
        <button class="stage-skip" type="button" @click="emit('skip')">跳过</button>

        <button
          v-if="showHelp"
          class="stage-help"
          type="button"
          :aria-expanded="helpOpen ? 'true' : 'false'"
          @click="helpOpen = !helpOpen"
        >
          <svg class="help-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 11.2v5.4" />
            <path d="M12 7.6v.2" />
          </svg>
          查看操作说明
        </button>
        <div v-if="showHelp && helpOpen" class="stage-help-body">
          <slot name="help" />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.playback-stage {
  position: absolute;
  inset: 0;
  color: #fff;
  pointer-events: auto;
  -webkit-tap-highlight-color: transparent;
}
.stage-media {
  position: absolute;
  inset: 0;
  z-index: 0;
  display: grid;
  place-items: center;
}
.stage-media.covered {
  visibility: hidden;
}
/* 中央竖排：本层不拦截点击，只有按钮自己取回指针事件 */
.stage-center {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 96px 20px calc(132px + env(safe-area-inset-bottom));
  text-align: center;
  pointer-events: none;
}
.stage-pills {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  margin: 0;
}
.phase-pill {
  padding: 4px 14px;
  border: 1px solid var(--tone, #35d6a4);
  border-radius: 999px;
  color: var(--tone, #35d6a4);
  font-size: 13px;
  letter-spacing: .04em;
  line-height: 1.5;
  white-space: nowrap;
  text-shadow: 0 1px 6px rgba(0, 0, 0, .5);
}
.pill-dot {
  flex-shrink: 0;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: rgba(255, 255, 255, .5);
}
.stage-bpm {
  color: rgba(255, 255, 255, .78);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  letter-spacing: .02em;
  white-space: nowrap;
}
.stage-hint {
  display: -webkit-box;
  overflow: hidden;
  max-width: 22ch;
  margin: 4px 0 2px;
  color: #fff;
  font-size: clamp(22px, 6vw, 34px);
  font-weight: 700;
  line-height: 1.35;
  text-wrap: balance;
  text-shadow: 0 2px 16px rgba(0, 0, 0, .6), 0 1px 3px rgba(0, 0, 0, .55);
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.stage-loading {
  margin: 4px 0 2px;
  color: rgba(255, 255, 255, .82);
  font-size: 14px;
  text-shadow: 0 1px 8px rgba(0, 0, 0, .6);
}
.stage-error {
  max-width: 30ch;
  margin: 4px 0 2px;
  color: #fff;
  font-size: 14px;
  line-height: 1.6;
  text-shadow: 0 1px 8px rgba(0, 0, 0, .6);
  overflow-wrap: anywhere;
}
.stage-progress {
  position: relative;
  width: 62%;
  height: 3px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, .22);
}
.stage-progress-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--tone, #35d6a4);
  transition: width .25s linear;
}
.stage-main {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: clamp(96px, 30vw, 124px);
  height: clamp(96px, 30vw, 124px);
  margin-top: 4px;
  padding: 0;
  border: 2px solid #fff;
  border-radius: 50%;
  color: #fff;
  font-family: inherit;
  font-size: 17px;
  font-weight: 600;
  line-height: 1.2;
  text-shadow: 0 1px 10px rgba(0, 0, 0, .5);
  background: transparent;
  cursor: pointer;
  pointer-events: auto;
  transition: opacity .15s ease, background-color .15s ease;
}
.stage-main:hover:not(:disabled) {
  background: rgba(255, 255, 255, .1);
}
.stage-main:disabled {
  opacity: .45;
  cursor: default;
}
.stage-main:focus-visible,
.stage-skip:focus-visible,
.stage-help:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 3px;
}
.stage-likes {
  margin: -4px 0 0;
  color: rgba(255, 255, 255, .6);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
/* 文字按钮：下划线细线，靠透明 padding 把命中区抬到 44px */
.stage-skip {
  min-height: 44px;
  margin: -8px 0 0;
  padding: 0 12px;
  border: 0;
  color: rgba(255, 255, 255, .66);
  font-family: inherit;
  font-size: 13px;
  line-height: 1;
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 4px;
  background: transparent;
  cursor: pointer;
  pointer-events: auto;
}
.stage-skip:hover {
  color: #fff;
}
.stage-help {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border: 1px solid rgba(255, 255, 255, .32);
  border-radius: 999px;
  color: rgba(255, 255, 255, .72);
  font-family: inherit;
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
  background: transparent;
  cursor: pointer;
  pointer-events: auto;
}
/* 药丸视觉更小，但点击热区补到 44px 高 */
.stage-help::after {
  content: '';
  position: absolute;
  inset: -9px -6px;
  border-radius: 999px;
}
.stage-help:hover {
  color: #fff;
  border-color: rgba(255, 255, 255, .55);
}
.help-icon {
  flex-shrink: 0;
}
/* 说明正文由 help 插槽提供，展开时压在其他内容之上 */
.stage-help-body {
  max-width: min(340px, 86vw);
  max-height: min(30vh, 240px);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 12px 14px;
  border-radius: 12px;
  color: rgba(255, 255, 255, .74);
  font-size: 12.5px;
  line-height: 1.6;
  text-align: left;
  background: rgba(0, 0, 0, .55);
  pointer-events: auto;
}
/* 说明正文由父组件以列表形式传入，统一收紧缩进 */
.stage-help-body :deep(ul),
.stage-help-body :deep(ol) {
  display: grid;
  gap: 4px;
  margin: 0;
  padding-left: 16px;
}
.stage-help-body :deep(p) {
  margin: 0;
}
.stage-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  pointer-events: auto;
}
.stage-actions :deep(button) {
  min-width: 44px;
  min-height: 44px;
  padding: 8px 18px;
  border: 1px solid rgba(255, 255, 255, .32);
  border-radius: 10px;
  color: #fff;
  font-family: inherit;
  font-size: 14px;
  background: rgba(0, 0, 0, .28);
  cursor: pointer;
}
.stage-actions :deep(button:hover:not(:disabled)) {
  background: rgba(255, 255, 255, .14);
}
.stage-actions :deep(button:disabled) {
  opacity: .45;
}
.stage-actions :deep(button:focus-visible) {
  outline: 2px solid #fff;
  outline-offset: 2px;
}
@media (prefers-reduced-motion: reduce) {
  .stage-main,
  .stage-progress-fill {
    transition: none;
  }
}
/* 矮屏或横屏时收紧留白，避免竖排内容顶到上下栏 */
@media (max-height: 700px) {
  .stage-center {
    gap: 10px;
    padding-block: 72px calc(112px + env(safe-area-inset-bottom));
  }
  .stage-hint {
    font-size: clamp(20px, 5vw, 28px);
  }
}
</style>
