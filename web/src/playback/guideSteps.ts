// 首次进入播放时的引导文案与本机「已看过」标记。纯数据，不涉及 Vue。
import type { GuideStep } from './types'

/** 「已看过引导」的本机存储键。 */
export const guideSeenKey = 'shicun.playback.guide.v1'

/** 五步引导：切图、颜色含义、暂停与继续、键鼠手势、怎么结束。 */
export const guideSteps: GuideStep[] = [
  {
    title: '怎么切图',
    body: '左右方向键、点一下画面或左右滑动都能换一张。按时间播放会按间隔自动切；按 BPM 播放时每响一拍切一张。',
  },
  {
    title: '三档颜色',
    body: '慢速是放慢的节奏，快速要跟上节拍，休息时松手别碰。画面颜色跟着当前阶段变化，底部图例写着三段各做什么。',
  },
  {
    title: '怎么暂停与继续',
    body: '空格或下方中间按钮暂停，再按一次继续。暂停时节拍、自动切图和计时都会停下，画面留在当前这一张。',
  },
  {
    title: '键盘与手势',
    body: '← → 上一项与下一项，F 切换全屏，Esc 退出播放。手机上左右滑动换图，双指放大后可以拖动查看细节。',
  },
  {
    title: '怎么结束',
    body: '点右上角退出，或点下方结束，会停在结束卡上。时间到会按许可率结算：忍住得越多越容易拿到许可，没忍住可以点「射了」直接结束。返回播放列表不会删除任何文件。',
  },
]

/** 读取是否看过引导；存储不可用或值异常都当作没看过。 */
export function readGuideSeen(): boolean {
  try {
    return localStorage.getItem(guideSeenKey) === '1'
  } catch {
    return false
  }
}

/** 记下已看过引导；写不进去时静默忽略，下次再显示一次。 */
export function markGuideSeen(): void {
  try {
    localStorage.setItem(guideSeenKey, '1')
  } catch {
    // 隐私模式或存储已满时不影响播放，只是下次会再提示一次。
  }
}
