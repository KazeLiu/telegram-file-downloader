<script setup lang="ts">
// 许可屏：时间到、抽签成功后盖满整屏的渐变色屏（参考站叫 reward）。
// 松手射精用橙色系，其余用粉色系；中间是倒计时条与剩余秒数。
import { computed } from 'vue'

const props = defineProps<{
  ruined: boolean
  windowLeft: number
  windowTotal: number
}>()

/** 已经用掉的比例 0–1。 */
const used = computed(() => {
  if (props.windowTotal <= 0) return 1
  const left = Math.max(0, props.windowLeft)
  return Math.min(1, Math.max(0, 1 - left / props.windowTotal))
})

const remaining = computed(() => Math.max(0, Math.ceil(props.windowLeft)))

const background = computed(() => (props.ruined
  ? 'radial-gradient(ellipse at 50% 30%, #c86a2a 0%, #6b2f0f 55%, #2a1206 100%)'
  : 'radial-gradient(ellipse at 50% 30%, #ff4d6d 0%, #a4123a 55%, #3a0612 100%)'))
</script>

<template>
  <div
    class="sd-reward" :style="{ background }" role="dialog" aria-modal="true"
    data-sundome="reward" :data-result="ruined ? 'ruin' : 'allow'"
  >
    <p class="sd-eyebrow">{{ ruined ? 'Ruined' : 'Permission' }}</p>
    <h2 class="sd-title">{{ ruined ? '可以射' : '可以射了' }}</h2>
    <p class="sd-body">{{ ruined ? '但射出的瞬间要松手。不碰，让它自己流' : '在进度条消失前射出来' }}</p>
    <div class="sd-bar" data-sundome-reward-bar>
      <div class="sd-bar-fill" :style="{ width: `${(1 - used) * 100}%` }" />
    </div>
    <p class="sd-remain" data-sundome-reward-seconds>剩余 {{ remaining }} 秒</p>
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
.sd-bar {
  position: relative; z-index: 10; margin: 32px 0 0; width: 100%; max-width: 28rem;
  height: 12px; overflow: hidden; border-radius: 999px; background: rgba(255, 255, 255, .2);
}
.sd-bar-fill {
  height: 100%; border-radius: 999px; background: #fff;
  transition: width .1s linear;
}
.sd-remain {
  position: relative; z-index: 10; margin: 12px 0 0;
  font-size: 14px; color: rgba(255, 255, 255, .7); font-variant-numeric: tabular-nums;
}
</style>
