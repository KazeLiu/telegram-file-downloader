<script setup lang="ts">
// 许可屏：时间到、抽签成功后盖满整屏的渐变色屏（参考站叫 reward）。
// 松手射精用橙色系，其余用粉色系；中间是倒计时条与剩余秒数。
// 连续（多少次都行）结局换成「可以射。多少次都行」＋每 25 秒一条「再来一次」。
import { computed, onMounted, ref } from 'vue'
import { multiLines, multiRoundLabel, multiRounds, multiTitle } from './engine'

const props = defineProps<{
  ruined: boolean
  windowLeft: number
  windowTotal: number
  /** 连续（多少次都行）结局：换成多轮文案，不显示普通正文。 */
  multi?: boolean
  /** 连续结局的第几次（从 1 开始）。 */
  round?: number
  /** 只玩乳头且拿到许可时，多一句「现在可以摸下面了」。 */
  allowBelow?: string
  paused: boolean
}>()
const emit = defineEmits<{ 'toggle-pause': []; finish: [] }>()
const pauseButton = ref<HTMLButtonElement>()
onMounted(() => pauseButton.value?.focus())

/** 已经用掉的比例 0–1。 */
const used = computed(() => {
  if (props.windowTotal <= 0) return 1
  const left = Math.max(0, props.windowLeft)
  return Math.min(1, Math.max(0, 1 - left / props.windowTotal))
})

const remaining = computed(() => Math.max(0, Math.ceil(props.windowLeft)))

const multi = computed(() => Boolean(props.multi) && !props.ruined)

const round = computed(() => Math.min(multiRounds, Math.max(1, Math.round(props.round ?? 1))))

const roundText = computed(() => multiRoundLabel(round.value))

const line = computed(() => multiLines[(round.value - 1) % multiLines.length] ?? multiLines[0] ?? '')

const title = computed(() => {
  if (multi.value) return multiTitle
  return props.ruined ? '可以射' : '可以射了'
})

const background = computed(() => (props.ruined
  ? 'radial-gradient(ellipse at 50% 30%, #813a16c9 0%, #6b2f0fa8 55%, #2a1206e8 100%)'
  : 'radial-gradient(ellipse at 50% 30%, #ac2446c9 0%, #a4123aa8 55%, #3a0612e8 100%)'))
</script>

<template>
  <div
    class="sd-reward" :style="{ background }" role="dialog" aria-modal="true"
    data-sundome="reward" :data-result="ruined ? 'ruin' : 'allow'"
    :data-sundome-multi="multi ? 'true' : 'false'"
    :data-sundome-reward-seconds="Math.round(windowTotal)"
  >
    <p class="sd-eyebrow">{{ ruined ? 'Ruined' : 'Permission' }}</p>
    <h2 class="sd-title">{{ title }}</h2>
    <template v-if="multi">
      <p class="sd-multi-round" data-sundome-multi-round>{{ roundText }}</p>
      <p class="sd-multi-line" data-sundome-multi-line>{{ line }}</p>
    </template>
    <p v-else class="sd-body">{{ ruined ? '但射出的瞬间要松手。不碰，让它自己流' : '在进度条消失前射出来' }}</p>
    <p v-if="allowBelow" class="sd-allow-below" data-sundome-focus-allow>{{ allowBelow }}</p>
    <div class="sd-bar" data-sundome-reward-bar>
      <div class="sd-bar-fill" :style="{ width: `${(1 - used) * 100}%` }" />
    </div>
    <p class="sd-remain" data-sundome-reward-seconds>剩余 {{ remaining }} 秒</p>
    <div class="sd-reward-actions">
      <button ref="pauseButton" type="button" @click="emit('toggle-pause')">{{ paused ? '继续' : '暂停' }}</button>
      <button type="button" @click="emit('finish')">结束</button>
    </div>
  </div>
</template>

<style scoped>
.sd-reward {
  position: fixed; inset: 0; z-index: 95;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 0 24px; color: #fff; text-align: center;
}
.sd-eyebrow {
  position: relative; z-index: 10; margin: 0;
  font-size: 12px; font-weight: 600; letter-spacing: .35em; text-indent: .35em;
  text-transform: uppercase; color: rgba(255, 255, 255, .7);
}
.sd-title {
  position: relative; z-index: 10; margin: 12px 0 0;
  font-size: clamp(44px, 13vw, 96px); font-style: italic; font-weight: 800; line-height: 1;
  text-wrap: balance;
}
.sd-body {
  position: relative; z-index: 10; margin: 24px 0 0; max-width: 32rem;
  font-size: 18px; line-height: 1.6; text-wrap: balance;
}
.sd-multi-round {
  position: relative; z-index: 10; margin: 20px 0 0;
  font-size: 14px; font-weight: 600; letter-spacing: .2em; text-indent: .2em;
  color: rgba(255, 255, 255, .7); font-variant-numeric: tabular-nums;
}
.sd-multi-line {
  position: relative; z-index: 10; margin: 8px 0 0; max-width: 32rem;
  font-size: 20px; font-weight: 700; line-height: 1.5; text-wrap: balance;
}
.sd-bar {
  position: relative; z-index: 10; margin: 32px 0 0; width: 100%; max-width: 28rem;
  height: 12px; overflow: hidden; border-radius: 999px; background: rgba(255, 255, 255, .2);
}
.sd-bar-fill {
  height: 100%; border-radius: 999px; background: #fff;
  transition: width .1s linear;
}
.sd-allow-below {
  margin: 12px 0 0; max-width: 30rem;
  font-size: 16px; font-weight: 700; line-height: 1.5;
}
.sd-remain {
  position: relative; z-index: 10; margin: 12px 0 0;
  font-size: 14px; color: rgba(255, 255, 255, .7); font-variant-numeric: tabular-nums;
}
.sd-reward-actions { display: flex; gap: 8px; margin-top: 16px; }
.sd-reward-actions button { min-height: 44px; padding-inline: 18px; border: 1px solid #fff8; border-radius: 999px; background: #0006; color: #fff; }
@media (min-width: 640px) {
  .sd-multi-line { font-size: 24px; }
}
</style>
