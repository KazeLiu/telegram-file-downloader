export type ReviewAxis = 'horizontal' | 'vertical' | null

export function reviewWheelStep(deltaX: number, deltaY: number): -1 | 0 | 1 {
  if (!deltaY || Math.abs(deltaX) >= Math.abs(deltaY)) return 0
  return deltaY > 0 ? 1 : -1
}

export function reviewAxis(locked: ReviewAxis, x: number, y: number): ReviewAxis {
  if (locked) return locked
  if (Math.abs(x) >= 8 && Math.abs(x) > Math.abs(y) * 1.25) return 'horizontal'
  if (Math.abs(y) >= 8 && Math.abs(y) > Math.abs(x) * 1.25) return 'vertical'
  return null
}

export function reviewDrag(offset: number, height: number, marked: boolean) {
  const y = Math.max(-height / 2, Math.min(height / 2, offset))
  // The image centre must enter the visible top or bottom quarter of the preview.
  const threshold = marked ? 56 : Math.max(56, height / 2 - Math.min(120, height / 4))
  const edge: -1 | 0 | 1 = Math.abs(y) >= threshold ? y < 0 ? -1 : 1 : 0
  const progress = marked ? 0 : Math.min(1, Math.abs(y) / threshold)
  return { y, edge, top: y < 0 ? progress : 0, bottom: y > 0 ? progress : 0 }
}
