import assert from 'node:assert/strict'
import { nextWallPage } from '../src/xiaomiMedia.ts'

assert.equal(nextWallPage(3, 0), 4)
assert.equal(nextWallPage(3, 1), 3)
assert.equal(nextWallPage(3, 20), 3)
assert.equal(nextWallPage(3, 21), 2)
assert.equal(nextWallPage(3, 80), 0)

const all = Array.from({ length: 160 }, (_, id) => id)
for (const count of [1, 19, 20, 21, 35, 60, 80]) {
  const removed = new Set(all.slice(0, count))
  const remaining = all.filter(id => !removed.has(id))
  let loaded = all.slice(0, 80).filter(id => !removed.has(id))
  for (let page = nextWallPage(3, count); page * 20 < remaining.length; page++) {
    const known = new Set(loaded)
    loaded = loaded.concat(remaining.slice(page * 20, page * 20 + 20).filter(id => !known.has(id)))
  }
  assert.deepEqual(loaded, remaining)
}
