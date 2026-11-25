<script setup lang="ts">
// 结算屏：照抄参考站的结算文案（Finished/Ruined/Denied/Lost 四套眉标+标题+正文）
// 以及「时间 / 指令 / 忍住」三格统计。背景是 radial 渐变（松手偏橙，其余偏粉）。
import { computed } from 'vue'
import type { FinishReason } from './types.ts'

const props = defineProps<{
  outcome: FinishReason
  elapsed: string
  durationMinutes: number
  percent: number
  held: number
  commands: number
  rounds: number
  /** 加时赛加了几次（0 表示没有加时；>0 时多显示一行「加时 N 次后获得许可」） */
  extends?: number
}>()

const emit = defineEmits<{ again: []; exit: [] }>()

/** 结算文案：key 是结束原因，缺省落到 deny 那一套。 */
const copy = computed(() => {
  switch (props.outcome) {
    case 'allow':
    case 'duration':
      return {
        eyebrow: 'Finished',
        title: '坚持到底了',
        body: '撑满了时间，拿到了许可。',
        ruin: false
      }
    case 'ruin':
      return {
        eyebrow: 'Ruined',
        title: '松手收场',
        body: '如果在射出的瞬间松手了，就算成功。留下一种没尽兴的感觉才是对的。',
        ruin: true
      }
    case 'lost':
      return {
        eyebrow: 'Lost',
        title: '没忍住，射了',
        body: `坚持了 ${props.elapsed}，完成了设定的 ${props.durationMinutes} 分钟中的 ${props.percent}%。`,
        ruin: true
      }
    case 'manual':
      return {
        eyebrow: 'Finished',
        title: '就到这儿',
        body: '自己想停就停。下次想撑久一点，把时间调长一点点就好。',
        ruin: false
      }
    case 'queue':
      return {
        eyebrow: 'Finished',
        title: '素材放完了',
        body: '这一轮的媒体已经全部播过。换个图库，或者把「循环」打开。',
        ruin: false
      }
    default:
      return {
        eyebrow: 'Denied',
        title: '今天被禁止了',
        body: '没有拿到许可。松手，就这样结束。下次也许会中。',
        ruin: false
      }
  }
})

const background = computed(() => (copy.value.ruin
  ? 'radial-gradient(ellipse at 50% 30%, #c86a2a 0%, #6b2f0f 55%, #2a1206 100%)'
  : 'radial-gradient(ellipse at 50% 30%, #ff4d6d 0%, #a4123a 55%, #3a0612 100%)'))

/** 三格统计：时间 / 指令 / 忍住，和参考站一致。 */
const facts = computed(() => [
  { label: '时间', value: props.elapsed },
  { label: '指令', value: `${props.commands}次` },
  { label: '忍住', value: `${props.held}次` }
])
</script>

<template>
  <div
    class="sd-finished"
    :style="{ background }"
    role="dialog"
    aria-modal="true"
    data-sundome="done"
    :data-result="copy.ruin ? 'ruin' : 'success'"
  >
    <p class="sd-eyebrow">{{ copy.eyebrow }}</p>
    <h2 class="sd-title">{{ copy.title }}</h2>
    <p v-if="(props.extends ?? 0) > 0" class="sd-extend-result" data-sundome-extend-result>
      加时 {{ props.extends }} 次后获得许可
    </p>
    <p class="sd-body" data-sundome-done-body>{{ copy.body }}</p>
    <dl class="sd-facts">
      <div v-for="fact in facts" :key="fact.label" data-sundome-done-stat>
        <dt>{{ fact.label }}</dt>
        <dd>{{ fact.value }}</dd>
      </div>
    </dl>
    <p v-if="rounds > 1" class="sd-rounds">第 {{ rounds }} 轮</p>
    <div class="sd-actions" data-sundome-done-actions>
      <button class="sd-primary" type="button" data-sundome-again @click="emit('again')">再来一次</button>
      <button class="sd-secondary" type="button" @click="emit('exit')">返回播放列表</button>
    </div>
  </div>
</template>

<style scoped>
.sd-finished {
  position: fixed; inset: 0; z-index: 100;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 24px; color: #fff; text-align: center;
}
.sd-eyebrow {
  margin: 0; font-size: 12px; font-weight: 600; letter-spacing: .35em; text-indent: .35em;
  text-transform: uppercase; color: rgba(255, 255, 255, .7);
}
.sd-title {
  margin: 12px 0 0; font-size: clamp(40px, 12vw, 88px); font-style: italic; font-weight: 800;
  line-height: 1; text-wrap: balance;
}
.sd-body {
  margin: 24px 0 0; max-width: 32rem; font-size: 16px; line-height: 1.7;
  color: rgba(255, 255, 255, .88); text-wrap: balance; word-break: auto-phrase;
}
.sd-extend-result { margin: 8px 0 0; font-size: 14px; font-weight: 700; color: #ffd0dc; }
.sd-facts { display: flex; gap: 24px; margin: 24px 0 0; padding: 0; }
.sd-facts > div {
  display: flex; flex-direction: column; gap: 4px; padding: 10px 20px;
  border-radius: 12px; background: rgba(0, 0, 0, .22);
}
.sd-facts dt { font-size: 10px; letter-spacing: .2em; text-transform: uppercase; color: rgba(255, 255, 255, .7); }
.sd-facts dd { margin: 0; font-size: 22px; font-style: italic; font-weight: 700; font-variant-numeric: tabular-nums; }
.sd-rounds { margin: 12px 0 0; font-size: 12px; color: rgba(255, 255, 255, .7); }
.sd-actions { display: flex; flex-direction: column; gap: 10px; margin-top: 28px; width: min(320px, 100%); }
.sd-primary, .sd-secondary {
  min-height: 0; padding: 13px 20px; border-radius: 12px; font-size: 15px; font-weight: 700; cursor: pointer;
  transition: background .15s ease, opacity .15s ease;
}
.sd-primary { border: 0; background: #fff; color: #1a0a10; }
.sd-primary:hover { opacity: .9; }
.sd-secondary { border: 1px solid rgba(255, 255, 255, .45); background: transparent; color: #fff; font-weight: 500; }
.sd-secondary:hover { background: rgba(255, 255, 255, .12); }
</style>
