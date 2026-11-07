export type ReviewDecision = 'keep' | 'recycle'

export function reviewNeedsRecycle(decision: ReviewDecision | undefined, selected: boolean) {
  return decision === undefined ? selected : decision === 'recycle'
}
