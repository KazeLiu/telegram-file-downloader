// 播放器运行层的共享类型与常量：运行层各展示组件只接受这里的形状，不改业务状态。
export type PhaseKind = 'slow' | 'fast' | 'rest'

export const phaseOrder: PhaseKind[] = ['slow', 'fast', 'rest']

export const phaseLabels: Record<PhaseKind, string> = { slow: '慢速', fast: '快速', rest: '休息' }

/** 中央大字提示：说明这一阶段手要怎么动。 */
export const phaseHints: Record<PhaseKind, string> = {
  slow: '放慢，跟着节拍一下一下地动',
  fast: '快一点，跟上节拍',
  rest: '松手，等它平息',
}

/** 阶段占比（快速为基准速率的倍数），供色条与节拍速率使用。 */
export const phaseRatios: Record<PhaseKind, number> = { slow: 0.6, fast: 1, rest: 0 }

export interface LegendItem {
  label: string
  tone: 'slow' | 'fast' | 'rest'
}

/** 底部图例：三档颜色各代表什么。 */
export const phaseLegend: LegendItem[] = [
  { label: '慢速：放慢、跟着节拍', tone: 'slow' },
  { label: '快速：跟上节拍', tone: 'fast' },
  { label: '休息：松手，别碰', tone: 'rest' },
]

/** 底部快捷键提示。 */
export const keyHints = ['← → 上一项 / 下一项', '空格 暂停 / 继续', 'F 全屏', 'Esc 退出']

export interface GuideStep {
  title: string
  body: string
}

export interface PlaybackPosition {
  index: number
  total: number
  cycle: number
}

// 结束原因：前三种是原有的计时／列表／手动结束，后四种是寸止玩法的结算。
export type FinishReason = 'duration' | 'queue' | 'manual' | 'edge' | 'deny' | 'allow' | 'ruin'

export const finishLabels: Record<FinishReason, string> = {
  duration: '本次计时已完成',
  queue: '已播放完列表',
  manual: '已结束播放',
  edge: '这次没忍住',
  deny: '一直忍到结束，没给许可',
  allow: '许可已给出',
  ruin: '松手射精',
}
