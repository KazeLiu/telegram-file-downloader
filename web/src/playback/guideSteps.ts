// 玩法引导：第一次进入播放器时按步演示，Esc 跳过。文案与指向对齐参考站（中文）。
import type { GuideStep } from './types.ts'

export const guideSeenKey = 'shicun.edge.guide.v2'

export const guideSteps: GuideStep[] = [
  {
    title: '照着指示做',
    body: '指示会显示在这里，屏幕的颜色就是信号：绿色是「可以撸」，黄色是「慢慢来」，红色是「不许碰」。',
    target: '[data-sundome-command-text]',
  },
  {
    title: '忍住了',
    body: '在快射的前一刻停下来了就按。按下后切换成“等它平息”。',
    target: '[data-sundome-edge]',
  },
  {
    title: '射了',
    body: '中途没忍住射了，就点这里。确认后会记录并结束这一局。',
    target: '[data-sundome-lost]',
  },
  {
    title: '视频快进／快退 10 秒',
    body: '双击视频右侧快进 10 秒，双击左侧后退 10 秒。连续点击可以 20 秒、30 秒地跳。电脑上也可以用 → ← 键。',
    target: '[data-sundome-video]:not([data-video-kind="image"])',
  },
  {
    title: '换个视频',
    body: '跳过当前视频，换下一个。',
    target: '[data-sundome-video-skip]',
  },
  {
    title: '视频大小',
    body: '在铺满屏幕和显示完整画面之间切换。',
    target: '[data-sundome-fit-toggle]',
  },
  {
    title: '悬浮小窗',
    body: '把指示放进悬浮小窗，可以一边看别的页面或应用一边继续。',
    target: '[data-sundome-pip]',
  },
  {
    title: '音量',
    body: '视频声音和节拍声音可以分别调节，节拍声最高能到 300%。',
    target: '[data-sundome-volume-toggle]',
  },
  {
    title: '横屏',
    body: '切换成横屏，视频看得更大。',
    target: '[data-sundome-landscape]',
  },
  {
    title: '暂停・退出',
    body: '可以随时暂停或结束。暂停时可以再看一遍这份说明。',
    target: '[data-sundome-pause]',
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
