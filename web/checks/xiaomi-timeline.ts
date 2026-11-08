import assert from 'node:assert/strict'
import { photoRows } from '../src/photoWall.ts'
import { accountViews, albumView, invalidateAlbum, mergeDay, removeDayItems, timelineLabel, type TimelineDay } from '../src/xiaomiTimeline.ts'

const day: TimelineDay = { date: '20200102', count: 61, items: [], page: 0, removed: 0, last: false, loading: false, error: '' }
const photo = (id: number) => ({ id: String(id), name: `${id}.jpg`, kind: 'image' as const, size: 1, taken_at: null, sort_time: 0 })
mergeDay(day, Array.from({ length: 30 }, (_, i) => photo(i)), false, 0)
assert.equal(day.items[0]!.timeline_day, '20200102')
const rows = photoRows([{ key: day.date, count: day.count, items: day.items }], 10)
assert.equal(rows.length, 8)
assert.equal(rows.reduce((sum, row) => sum + row.count, 0), 61)
assert.equal(rows.filter(row => row.kind === 'photos' && !row.items.length).length, 4)
removeDayItems(day, new Set(['0']))
assert.equal(day.count, 60)
assert.equal(Math.max(0, day.page - Math.ceil(day.removed / 30)), 0)
mergeDay(day, Array.from({ length: 30 }, (_, i) => photo(i + 1)), false, 0)
assert.equal(day.items.length, 30)
assert.equal(new Set(day.items.map(item => item.id)).size, 30)
mergeDay(day, [photo(31)], true, 1)
assert.equal(day.count, 31)
assert.equal(timelineLabel('20200102'), '2020年1月2日')
accountViews('one')
const view = albumView('one', '1')
view.days.push(day); view.scroll = 1234
assert.equal(albumView('one', '1'), view)
assert.equal(albumView('one', '1').scroll, 1234)
invalidateAlbum('one', '1')
assert.notEqual(albumView('one', '1'), view)
accountViews('two')
assert.equal(albumView('two', '1').days.length, 0)
const oldest = albumView('two', '1')
for (let i = 2; i <= 9; i++) albumView('two', String(i))
assert.notEqual(albumView('two', '1'), oldest)
