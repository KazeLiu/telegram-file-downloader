// 玩法引导：第一次进入播放器时按步演示，Esc 跳过。
import type { GuideStep } from './types.ts'

export const guideSeenKey = 'shicun.edge.guide.v1'

export const guideSteps: GuideStep[] = [
  {
    title: '屏幕是绿色时可以撸',
    body: '手跟着光和声音的节拍。一拍一下，别抢也别慢。画面下方的进度条走完，这条指令就结束了。',
  },
  {
    title: '黄色是放慢、挑逗',
    body: '这时候不用急，慢慢来。节拍会变低，跟着低音一下一下地动。',
  },
  {
    title: '变红就松手',
    body: '屏幕变红、掉到闷红时，立刻松手。结束前不许碰。等它平息了才轮到下一条。',
  },
  {
    title: '忍住了就按「忍住了」',
    body: '在快忍不住的前一刻停下来就按。每按一次，最后拿到许可的概率 +5%，最多累计 +20%。',
  },
  {
    title: '射了就输',
    body: '时间到之前射了，这一局就结束。按下「射了」会记录你撑了多久。',
  },
  {
    title: '时间到之后要抽签',
    body: '按难度对应的概率决定「允许」还是「禁止」。允许了就要在倒计时内射出来。',
  },
  {
    title: '键盘也能操作',
    body: '空格 暂停 / 继续 · E 记一次忍住 · F 全屏 · Esc 退出。手机上直接点按钮。',
  },
  {
    title: '声音可以自己调',
    body: '右上角的喇叭图标里可以调视频音量、节拍声（最高 300%）和画面变暗程度。',
  },
  {
    title: '准备好就离开',
    body: '把手放好，别急。你也可以随时点「退出」回到列表换一套设置。',
  },
]

export function readGuideSeen() {
  if (typeof localStorage === 'undefined') return true
  try {
    return localStorage.getItem(guideSeenKey) === '1'
  } catch {
    return true
  }
}

export function markGuideSeen() {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(guideSeenKey, '1')
  } catch {
    // 忽略配额失败：引导只是提示，不该阻断播放。
  }
}
