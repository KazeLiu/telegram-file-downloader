// 「整局只玩一个部位」模式（参考站 focus）：文案与部位表。
// 该模式下不会插入中途的乳头 / 龟头专属段，指令池整局换成该部位的专属池。
export const focusAreas = ['none', 'nipple', 'glans'] as const
export type FocusArea = (typeof focusAreas)[number]

export const focusLegend = '整局只玩一个部位'

export const focusLabels: Record<FocusArea, string> = {
  none: '不限制',
  nipple: '只玩乳头',
  glans: '只玩龟头'
}

/** 选中某个部位时显示在设置项下面的说明。 */
export const focusNotes: Record<FocusArea, string> = {
  none: '',
  nipple: '从头到尾只出乳头指令。最后允许前，下面一下都不许碰。',
  glans: '从头到尾只出龟头指令。不许握柱身。'
}

/** 单部位模式下，「只玩乳头的时间」「只玩龟头的时间」两个开关不生效。 */
export const focusSectionsOff = '单部位模式下不会使用'

/** 只玩乳头且拿到许可时，奖励屏多一句「现在可以摸下面了」。 */
export const focusAllowBelow = '现在可以摸下面了。'
