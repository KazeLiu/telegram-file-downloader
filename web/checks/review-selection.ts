import assert from 'node:assert/strict'
import { reviewNeedsRecycle, type ReviewDecision } from '../src/reviewSelection.ts'

for (const selected of [false, true]) {
  assert.equal(reviewNeedsRecycle(undefined, selected), selected)
  assert.equal(reviewNeedsRecycle('keep', selected), false)
  assert.equal(reviewNeedsRecycle('recycle', selected), true)
}
const decisions = new Map<number, ReviewDecision>()
const wallSelected = true
assert.equal(reviewNeedsRecycle(decisions.get(0), wallSelected), true)
decisions.set(0, 'keep')
assert.equal(reviewNeedsRecycle(decisions.get(0), wallSelected), false)
decisions.delete(0)
assert.equal(reviewNeedsRecycle(decisions.get(0), wallSelected), true)
decisions.set(0, 'recycle')
assert.equal(reviewNeedsRecycle(decisions.get(0), false), true)
