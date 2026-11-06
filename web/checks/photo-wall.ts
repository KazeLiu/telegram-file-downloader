import assert from 'node:assert/strict'
import { groupPhotos, photoRows } from '../src/photoWall.ts'

const items = Array.from({ length: 10000 }, (_, id) => ({ id, sort_time: 1793538000000 - Math.floor(id / 250) * 86400000 }))
const groups = groupPhotos(items)
assert.equal(groups.length, 40)
assert.equal(groups[0]!.items.length, 250)
for (const columns of [3, 10, 22, 30]) {
  const rows = photoRows(groups, columns)
  assert.equal(rows.filter(row => row.kind === 'day').length, groups.length)
  assert.deepEqual(rows.flatMap(row => row.items), items)
  assert.ok(rows.every(row => row.items.length <= columns))
  assert.equal(rows.find(row => row.kind === 'photos')!.start, 0)
  const last = rows.at(-1)!
  assert.equal(last.start + last.items.length, items.length)
  assert.equal(new Set(rows.map(row => row.key)).size, rows.length)
}
assert.deepEqual(photoRows(groupPhotos([]), 10), [])
