<script setup lang="ts">
// 中央区：模式胶囊 → 节拍点 → 指令文字 → 任务倒计时条 → 「忍住了」主按钮 → 「射了」。
// 布局与参考实现一致：全部居中竖排，指令字最重（28px / 大屏 48px）。
import { computed, ref, watch } from 'vue'
import { modeColors, modeLabels, type EdgeMode } from './engine.ts'

const props = defineProps<{
  mode: EdgeMode
  text: string
  hint: string
  bpm: number
  progress: number
  taskSeconds: number
  taskKey: number
  paused: boolean
  cooling: boolean
  canHold: boolean
  held: number
  note: string
  /** 口吻短句：放在指令前 / 后（没有口吻时为空串） */
  toneBefore?: string
  toneAfter?: string
}>()

const emit = defineEmits<{ hold: []; lost: []; guide: [] }>()

/** 「射了」先弹确认条（对齐参考站的「记为中途结束的一局吗？」），避免误触。 */
const asking = ref(false)
watch(() => props.taskKey, () => { asking.value = false })

const color = computed(() => modeColors[props.mode])
const label = computed(() => (props.paused ? '已暂停' : modeLabels[props.mode]))
const beatDuration = computed(() => (props.bpm > 0 ? `${(60 / props.bpm).toFixed(3)}s` : '0s'))
const showBeat = computed(() => !props.paused && (props.mode === 'go' || props.mode === 'slow') && props.bpm > 0)
const clampedProgress = computed(() => Math.min(1, Math.max(0, props.progress)))
/** 暂停时参考站会在「射了」下面多给一个「查看操作说明」的入口。 */
const showGuideButton = computed(() => props.paused && !props.cooling && !asking.value)

/**
 * 按句切分指令文字（对齐参考实现的 Sentences 组件）：
 * 逐字累积，遇到「。！？」，或「.!?」后跟空格就断句；单句时原样返回。
 * 多句时每句单独 inline-block，前一句不以中文句号结尾时补一个空格。
 */
const sentences = computed(() => {
  const text = props.text ?? ''
  const parts: string[] = []
  let buffer = ''
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]!
    buffer += char
    const cjk = char === '。' || char === '！' || char === '？'
    const latin = (char === '.' || char === '!' || char === '?') && text[index + 1] === ' '
    if (!cjk && !latin) continue
    parts.push(buffer.trim())
    buffer = ''
  }
  if (buffer.trim()) parts.push(buffer.trim())
  return parts.filter(Boolean)
})
</script>

<template>
  <div class="sd-center-stage" :style="{ '--sd-mode': color }">
    <div class="sd-pill-row">
      <span class="sd-pill" data-sundome-mode-label>{{ label }}</span>
      <span v-if="bpm > 0" class="sd-bpm" data-sundome-bpm>
        <span v-if="showBeat" class="sd-beat" :style="{ '--beat': beatDuration }" />
        <span>{{ bpm }} BPM</span>
      </span>
    </div>
    <p v-if="toneBefore" class="sd-tone sd-tone-before" data-sundome-tone="before">{{ toneBefore }}</p>
    <div class="sd-command-text" data-sundome-command-text>
      <p class="sd-command" :class="{ 'sd-command-tight': toneBefore }" data-sundome-command><span v-for="(line, index) in sentences" :key="index" class="sd-sentence">{{ line }}</span></p>
    </div>
    <p v-if="toneAfter" class="sd-tone sd-tone-after" data-sundome-tone="after">{{ toneAfter }}</p>
    <p v-if="hint" class="sd-command-hint" data-sundome-hint>{{ hint }}</p>
    <div class="sd-taskbar" data-sundome-task-bar role="progressbar" :aria-valuenow="Math.round(clampedProgress * 100)">
      <div
        :key="taskKey"
        class="sd-taskbar-fill"
        :style="{ background: color, animationDuration: `${Math.max(0.05, taskSeconds)}s`, animationPlayState: paused ? 'paused' : 'running' }"
      />
    </div>
    <button class="sd-hold" type="button" :disabled="!canHold" data-sundome-edge @click="emit('hold')">忍住了</button>
    <p class="sd-hint" data-sundome-edge-hint><span>在快射的前一刻停下来了就按。</span><span>按下后切换成“等它平息”</span></p>
    <p v-if="note" class="sd-note">{{ note }}</p>
    <div v-if="asking" class="sd-lost-ask" data-sundome-lost-ask>
      <p>记为中途结束的一局吗？</p>
      <div class="sd-lost-actions">
        <button type="button" class="sd-lost-yes" data-sundome-lost-yes @click="emit('lost')">记录并结束</button>
        <button type="button" class="sd-lost-no" data-sundome-lost-no @click="asking = false">继续</button>
      </div>
    </div>
    <button v-else class="sd-lost" type="button" data-sundome-lost @click="asking = true">射了</button>
    <button v-if="showGuideButton" class="sd-guide-open" type="button" data-sundome-guide-open @click="emit('guide')">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M9.5 9.5a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.1 1-1.1 1.8M12 17h.01" />
      </svg>
      查看操作说明
    </button>
  </div>
</template>

<style scoped>
.sd-center-stage { display: flex; flex-direction: column; align-items: center; width: 100%; }
.sd-pill-row { display: flex; align-items: center; justify-content: center; gap: 10px; }
.sd-pill {
  padding: 4px 12px;
  border: 1px solid var(--sd-mode);
  border-radius: 999px;
  color: var(--sd-mode);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .25em;
  text-indent: .25em;
}
.sd-beat {
  display: inline-block;
  width: 12px; height: 12px; border-radius: 999px;
  background: var(--sd-mode);
  animation: sd-beat var(--beat, 1s) ease-in-out infinite;
}
.sd-bpm { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 700; letter-spacing: .12em; color: rgba(255, 255, 255, .6); font-variant-numeric: tabular-nums; }
.sd-command-text { display: flex; flex-direction: column; align-items: center; width: 100%; }
.sd-command {
  margin: 24px 0 0;
  max-width: 30ch;
  font-size: 28px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -.025em;
  text-shadow: 0 0 28px rgba(0, 0, 0, .35);
  text-wrap: balance;
  word-break: auto-phrase;
  animation: sd-fade-in .35s ease both;
}
/* 口吻短句：比指令淡一点、加字距，位置在指令上下（对齐参考站 data-sundome-tone）。 */
.sd-tone {
  margin: 20px 0 0;
  max-width: 30ch;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: .08em;
  line-height: 1.4;
  color: rgba(255, 255, 255, .85);
  text-wrap: balance;
  animation: sd-fade-in .35s ease both;
}
.sd-tone-after { margin: 12px 0 0; font-size: 16px; }
.sd-command-tight { margin-top: 12px; }
@media (min-width: 640px) {
  .sd-tone { font-size: 24px; }
  .sd-tone-after { font-size: 20px; }
  .sd-command-tight { margin-top: 12px; }
}
/* 多句时逐句 inline-block：每句尽量整句换行（对齐参考站 Sentences）。 */
.sd-sentence { display: inline-block; max-width: 100%; word-break: keep-all; overflow-wrap: anywhere; }
.sd-taskbar {
  position: relative;
  margin-top: 16px;
  width: 160px; height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, .15);
}
.sd-taskbar-fill {
  width: 100%; height: 100%;
  transform-origin: left center;
  border-radius: 999px;
  animation-name: sd-shrink;
  animation-timing-function: linear;
  animation-fill-mode: forwards;
}
.sd-progress {
  margin-top: 10px;
  width: min(320px, 70%);
  height: 2px;
  border-radius: 999px;
  background: rgba(255, 255, 255, .12);
  overflow: hidden;
}
.sd-progress-fill { width: 100%; height: 100%; transform-origin: left center; transition: transform .2s linear; }
.sd-hold {
  margin-top: 32px;
  min-width: 100px; padding: 12px 24px;
  border: 2px solid rgba(255, 255, 255, .6);
  border-radius: 999px;
  background: transparent;
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
  transition: background .15s ease, border-color .15s ease, color .15s ease;
}
.sd-hold:hover:not(:disabled) { background: rgba(255, 255, 255, .1); }
.sd-hold:disabled { border-color: rgba(255, 255, 255, .2); color: rgba(255, 255, 255, .3); cursor: default; }
.sd-hint {
  margin: 12px 0 0;
  max-width: 28em;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(255, 255, 255, .5);
}
.sd-hint span { display: inline-block; max-width: 100%; }
.sd-command-hint {
  margin: 16px 0 0;
  max-width: 30em;
  font-size: 16px;
  line-height: 1.6;
  color: rgba(255, 255, 255, .7);
}
.sd-held { margin: 8px 0 0; font-size: 12px; color: rgba(255, 255, 255, .55); }
.sd-note { margin: 8px 0 0; font-size: 12px; font-weight: 700; color: var(--sd-mode); }
.sd-lost {
  margin-top: 20px;
  min-height: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: rgba(255, 255, 255, .55);
  font-size: 13px;
  text-decoration: underline;
  text-underline-offset: 4px;
  cursor: pointer;
}
.sd-lost:hover { color: rgba(255, 255, 255, .8); }
.sd-guide-open {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 16px;
  min-height: 0;
  padding: 6px 12px;
  border: 1px solid rgba(255, 255, 255, .3);
  border-radius: 999px;
  background: rgba(0, 0, 0, .3);
  color: rgba(255, 255, 255, .85);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}
.sd-guide-open:hover { background: rgba(255, 255, 255, .1); }
/* 「射了」的二次确认条：参考站是半透明黑底圆角块 + 白底主按钮 + 描边次按钮。 */
.sd-lost-ask {
  margin-top: 20px;
  padding: 12px 16px;
  border-radius: 12px;
  background: rgba(0, 0, 0, .55);
  text-align: center;
}
.sd-lost-ask p { margin: 0; font-size: 14px; color: rgba(255, 255, 255, .85); }
.sd-lost-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin-top: 8px; }
.sd-lost-yes, .sd-lost-no {
  min-height: 0; padding: 8px 16px;
  border-radius: 999px; font-size: 14px; cursor: pointer;
  transition: background .15s ease;
}
.sd-lost-yes { border: 0; background: #fff; color: #000; font-weight: 700; }
.sd-lost-yes:hover { opacity: .9; }
.sd-lost-no { border: 1px solid rgba(255, 255, 255, .4); background: transparent; color: #fff; font-weight: 500; }
.sd-lost-no:hover { background: rgba(255, 255, 255, .1); }
@media (min-width: 640px) { .sd-command { font-size: 48px; } }
@media (max-width: 520px) {
  .sd-command { font-size: 24px; margin-top: 18px; }
  .sd-hold { margin-top: 24px; padding: 10px 20px; }
}
@keyframes sd-shrink { from { transform: scaleX(1); } to { transform: scaleX(0); } }
@keyframes sd-fade-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes sd-beat {
  0% { opacity: .55; transform: scale(1); }
  12% { opacity: 1; transform: scale(1.35); }
  100% { opacity: .55; transform: scale(1); }
}
</style>
