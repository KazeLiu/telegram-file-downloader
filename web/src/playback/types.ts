// 运行时共用的类型与文案：相位标签搬到 engine.ts（go/slow/stop 三档），
// 这里只保留结束原因、引导步骤与位置信息这些和玩法无关的东西。
import type { EdgeMode } from './engine.ts'

/** 本次播放为什么结束。 */
export type FinishReason = 'duration' | 'queue' | 'manual' | 'lost' | 'allow' | 'deny' | 'ruin'

export const finishLabels: Record<FinishReason, string> = {
  duration: '时间到',
  queue: '媒体播完了',
  manual: '自己结束的',
  lost: '射了',
  allow: '拿到许可',
  deny: '没拿到许可',
  ruin: '松手射精'
}

/** 结束屏的标题层级：允许 / 禁止 / 松手 / 中途结束。 */
export const finishTitles: Record<FinishReason, string> = {
  duration: '时间到',
  queue: '媒体播完了',
  manual: '就到这儿',
  lost: '输了',
  allow: '可以了',
  deny: '不许射',
  ruin: '松手'
}

export interface GuideStep {
  title: string
  body: string
}

/** 运行层顶部的位置信息。 */
export interface PlaybackPosition {
  index: number
  total: number
  cycle: number
}

/** 底栏图例的一项。 */
export interface LegendItem {
  label: string
  tone: string
}

/** 三档相位（与 engine.ts 的 EdgeMode 同义，运行时直接复用）。 */
export type PhaseKind = EdgeMode
