import assert from 'node:assert/strict'
import {
  exportConfiguration, importConfiguration, legacyPlaybackConfigFormats, mediaKey, newPlaylist, nextBeatTime, playbackConfigFormat,
  playbackCycle, playbackSchemaVersion, playbackStorageKey, readPreferences, recoverPreferences, shownImagesLimit, trimShownImages,
  validPlaylist, type Playlist, type PlaybackMedia
} from '../src/playback.ts'

function messageOf(run: () => unknown) {
  try { run() } catch (error) { return (error as Error).message }
  return ''
}

// —— 版本与存储键 ——
assert.equal(playbackSchemaVersion, 2)
assert.equal(playbackStorageKey, 'shicun.playback.v1')
assert.equal(playbackConfigFormat, 'shicun.playback.config.v2')
assert.equal(legacyPlaybackConfigFormats[0], 'shicun.playback.config.v1')
assert.equal(shownImagesLimit, 20000)

// —— newPlaylist 默认值与 validPlaylist 边界 ——
const playlist = newPlaylist()
assert.equal(playlist.imageTiming, 'time')
assert.equal(validPlaylist(playlist), true)
assert.ok(validPlaylist({ ...playlist, kind: 'image', imageTiming: 'beat' }))
for (const key of ['mediaVolume', 'beatVolume', 'speechVolume'] as const) {
  assert.equal(validPlaylist({ ...playlist, [key]: 0 }), true, `${key} 允许 0`)
  assert.equal(validPlaylist({ ...playlist, [key]: 100 }), true, `${key} 允许 100`)
  assert.equal(validPlaylist({ ...playlist, [key]: 101 }), false, `${key} 拒绝 101`)
  assert.equal(validPlaylist({ ...playlist, [key]: -1 }), false, `${key} 拒绝 -1`)
  assert.equal(validPlaylist({ ...playlist, [key]: 50.5 }), false, `${key} 拒绝非整数`)
}
assert.equal(validPlaylist({ ...playlist, brightness: 20 }), true)
assert.equal(validPlaylist({ ...playlist, brightness: 100 }), true)
assert.equal(validPlaylist({ ...playlist, brightness: 19 }), false)
assert.equal(validPlaylist({ ...playlist, brightness: 101 }), false)
assert.equal(validPlaylist({ ...playlist, imageSeconds: 1 }), true)
assert.equal(validPlaylist({ ...playlist, imageSeconds: 300 }), true)
assert.equal(validPlaylist({ ...playlist, imageSeconds: 0 }), false)
assert.equal(validPlaylist({ ...playlist, imageSeconds: 301 }), false)
assert.equal(validPlaylist({ ...playlist, minutes: 0 }), true)
assert.equal(validPlaylist({ ...playlist, minutes: 180 }), true)
assert.equal(validPlaylist({ ...playlist, minutes: 181 }), false)
assert.equal(validPlaylist({ ...playlist, bpm: 30 }), true)
assert.equal(validPlaylist({ ...playlist, bpm: 180 }), true)
assert.equal(validPlaylist({ ...playlist, bpm: 29 }), false)
assert.equal(validPlaylist({ ...playlist, bpm: 181 }), false)
assert.equal(validPlaylist({ ...playlist, imageCount: 0 }), true)
assert.equal(validPlaylist({ ...playlist, imageCount: 100000 }), true)
assert.equal(validPlaylist({ ...playlist, imageCount: 100001 }), false)
assert.equal(validPlaylist({ ...playlist, imageCount: -1 }), false)
for (const rate of [0.8, 1, 1.2]) assert.equal(validPlaylist({ ...playlist, speechRate: rate }), true)
assert.equal(validPlaylist({ ...playlist, speechRate: 0.9 }), false)
for (const name of ['', '   ']) assert.equal(validPlaylist({ ...playlist, name }), false)
assert.equal(validPlaylist({ ...playlist, name: '名'.repeat(80) }), true)
assert.equal(validPlaylist({ ...playlist, name: '名'.repeat(81) }), false)
assert.equal(validPlaylist({ ...playlist, kind: 'audio' as Playlist['kind'] }), false)
assert.equal(validPlaylist({ ...playlist, order: 'random' as Playlist['order'] }), false)
assert.equal(validPlaylist({ ...playlist, imageTiming: 'unknown' as Playlist['imageTiming'] }), false)
assert.equal(validPlaylist({ ...playlist, roots: [1] as unknown as string[] }), false)
assert.equal(validPlaylist({ ...playlist, hideTime: 'yes' as unknown as boolean }), false)

// —— 节拍与选图保持原行为 ——
assert.equal(nextBeatTime(0, 1000, 120), 1500)
assert.equal(nextBeatTime(1500, 1525, 120), 2000)
assert.equal(nextBeatTime(1500, 3500, 120), 4000)
assert.equal(nextBeatTime(0, 1000, 60), 2000)

const images: PlaybackMedia[] = [1, 2, 3, 4, 5].map(id => ({ root: 'downloads', path: `${id}.jpg`, name: `${id}.jpg`, kind: 'image', version: '1' }))
const options = { ...playlist, imageCount: 2, order: 'sequential' as const }
const first = playbackCycle(images, options, [])
assert.deepEqual(first.queue, images.slice(0, 2))
assert.deepEqual(first.shownImages, [])
// Selecting or preloading a file does not consume it; only the renderer records displayed files.
const partial = playbackCycle(images, options, [mediaKey(images[0]!)])
assert.deepEqual(partial.queue, images.slice(1, 3))
const next = playbackCycle(images, options, images.slice(0, 2).map(mediaKey))
assert.deepEqual(next.queue, images.slice(2, 4))
const reset = playbackCycle(images, options, [...images.slice(0, 4).map(mediaKey), 'other-gallery'])
assert.equal(reset.reset, true)
assert.deepEqual(reset.shownImages, ['other-gallery'])
assert.deepEqual(reset.queue, images.slice(0, 2))
assert.deepEqual(playbackCycle(images, { ...options, imageCount: 0 }, images.slice(0, 2).map(mediaKey)).queue, images.slice(2))
assert.equal(playbackCycle(images, options, images.map(mediaKey)).reset, true)
assert.equal(playbackCycle(images, { ...options, imageCount: 100 }, []).queue.length, images.length)
const video: PlaybackMedia = { root: 'downloads', path: 'video.mp4', name: 'video.mp4', kind: 'video', version: '1' }
assert.deepEqual(playbackCycle([video], options, []).queue, [video])
assert.deepEqual(playbackCycle([...images, video], options, []).queue, [...images.slice(0, 2), video])
assert.equal(playbackCycle(images, { ...options, order: 'shuffle' }, images.slice(0, 2).map(mediaKey)).queue.every(item => !images.slice(0, 2).includes(item)), true)
assert.equal(playbackCycle([{ ...images[0]!, root: 'overlap', identity: '/same/photo.jpg' }, ...images.slice(1)], options, ['/same/photo.jpg']).queue.some(item => item.identity === '/same/photo.jpg'), false)

// —— 迁移：v1（无 schemaVersion，缺新增字段）补齐后升级，条数不变 ——
const legacyPlaylist = { ...playlist } as Record<string, unknown>
for (const key of ['imageTiming', 'imageCount', 'mediaVolume', 'beatVolume', 'speechVolume', 'speechRate', 'hideTime', 'brightness'] as const) delete legacyPlaylist[key]
const second = { ...newPlaylist(), id: 'second-list', name: '第二个列表' }
const third = { ...newPlaylist(), id: 'third-list', name: '第三个列表' }
const v1Stored = JSON.stringify({
  playlists: [legacyPlaylist, second, third], selected: second.id,
  favorites: ['downloads/a.jpg', 'downloads/b.jpg'], shownImages: ['downloads/a.jpg', 'downloads/c.jpg', 'downloads/d.jpg']
})
assert.equal('schemaVersion' in (JSON.parse(v1Stored) as Record<string, unknown>), false)
const upgraded = readPreferences(v1Stored)
assert.equal(upgraded.schemaVersion, playbackSchemaVersion)
assert.equal(upgraded.playlists.length, 3)
assert.equal(upgraded.playlists[0]!.imageTiming, 'time')
assert.equal(upgraded.playlists[0]!.imageCount, 0)
assert.equal(upgraded.playlists[0]!.mediaVolume, 100)
assert.equal(upgraded.playlists[0]!.beatVolume, 100)
assert.equal(upgraded.playlists[0]!.speechVolume, 100)
assert.equal(upgraded.playlists[0]!.speechRate, 1)
assert.equal(upgraded.playlists[0]!.hideTime, false)
assert.equal(upgraded.playlists[0]!.brightness, 100)
assert.equal(validPlaylist(upgraded.playlists[0]!), true)
assert.equal(upgraded.playlists[0]!.id, playlist.id)
assert.equal(upgraded.playlists[0]!.name, playlist.name)
assert.deepEqual(upgraded.favorites, ['downloads/a.jpg', 'downloads/b.jpg'])
assert.deepEqual(upgraded.shownImages, ['downloads/a.jpg', 'downloads/c.jpg', 'downloads/d.jpg'])
assert.equal(upgraded.selected, second.id)
// 升级后的对象就是写回本机的形态：带 schemaVersion 2，且再次读取不再产生迁移。
const writtenBack = JSON.parse(JSON.stringify(upgraded)) as Record<string, unknown>
assert.equal(writtenBack.schemaVersion, 2)
assert.deepEqual(readPreferences(JSON.stringify(upgraded)), upgraded)
const partialV1 = readPreferences(JSON.stringify({ playlists: [legacyPlaylist], selected: playlist.id, favorites: ['kept'] }))
assert.deepEqual(partialV1.shownImages, [])
assert.deepEqual(partialV1.favorites, ['kept'])
assert.equal(partialV1.schemaVersion, playbackSchemaVersion)
assert.deepEqual(readPreferences(JSON.stringify({ playlists: [legacyPlaylist], selected: 'missing', favorites: [] })).selected, playlist.id)

// —— 坏数据：字段类型错误补齐默认值，不再要求重置 ——
const repaired = readPreferences(JSON.stringify({
  playlists: [{
    ...playlist, id: 'repaired', name: '   ', roots: 'downloads', imageTiming: 'unknown', imageSeconds: 0, minutes: 999, bpm: 12,
    imageCount: -5, mediaVolume: 101, speechRate: 0.9, brightness: 5, hideTime: 'yes'
  }],
  selected: 'missing-list', favorites: ['ok', 42, null], shownImages: ['a.jpg', null, 7]
}))
assert.equal(repaired.playlists.length, 1)
assert.equal(repaired.playlists[0]!.id, 'repaired')
assert.equal(repaired.playlists[0]!.name, '未命名播放列表')
assert.deepEqual(repaired.playlists[0]!.roots, [])
assert.equal(repaired.playlists[0]!.imageTiming, 'time')
assert.equal(repaired.playlists[0]!.imageSeconds, 1)
assert.equal(repaired.playlists[0]!.minutes, 180)
assert.equal(repaired.playlists[0]!.bpm, 30)
assert.equal(repaired.playlists[0]!.imageCount, 0)
assert.equal(repaired.playlists[0]!.mediaVolume, 100)
assert.equal(repaired.playlists[0]!.speechRate, 1)
assert.equal(repaired.playlists[0]!.brightness, 20)
assert.equal(repaired.playlists[0]!.hideTime, false)
assert.equal(validPlaylist(repaired.playlists[0]!), true)
assert.equal(repaired.selected, 'repaired')
assert.deepEqual(repaired.favorites, ['ok'])
assert.deepEqual(repaired.shownImages, ['a.jpg'])
// 缺失 id 时补一个新 id；重复 id 只保留第一个。
const reidentified = readPreferences(JSON.stringify({ playlists: [{ ...playlist, id: 42 }, { ...playlist }], selected: '' }))
assert.equal(typeof reidentified.playlists[0]!.id, 'string')
assert.equal(new Set(reidentified.playlists.map(item => item.id)).size, 2)
assert.equal(reidentified.playlists[1]!.id, playlist.id)

// —— 结构性损坏才抛错，文案指出坏在哪里并留有救数据的出口 ——
for (const broken of [
  '{broken', 'null', '[]', '"text"', JSON.stringify({ playlists: 'none' }),
  JSON.stringify({ playlists: [playlist, 3] }), JSON.stringify({ playlists: [], favorites: {} }),
  JSON.stringify({ playlists: [], shownImages: 'none' }), JSON.stringify({ playlists: [], schemaVersion: playbackSchemaVersion + 1 })
]) assert.throws(() => readPreferences(broken), /本机播放数据损坏/)
const listMessage = messageOf(() => readPreferences(JSON.stringify({ playlists: 'none' })))
assert.match(listMessage, /playlists/)
assert.match(listMessage, /备份|recoverPreferences/)
assert.equal(listMessage.includes('唯一'), false)
assert.equal(listMessage.includes('请重置'), false)
const jsonMessage = messageOf(() => readPreferences('{broken'))
assert.match(jsonMessage, /JSON/)
assert.match(jsonMessage, /备份|recoverPreferences/)
const futureMessage = messageOf(() => readPreferences(JSON.stringify({ playlists: [], schemaVersion: 99 })))
assert.match(futureMessage, /99/)
assert.match(futureMessage, /更新页面/)

// —— 救数据的出口：recoverPreferences 不抛错，坏条目跳过、好条目保住 ——
const salvageable = recoverPreferences(JSON.stringify({
  playlists: [{ ...playlist, mediaVolume: 101 }, 'junk', { ...playlist, id: 'kept-2', name: '第二个' }],
  selected: 'missing', favorites: 'bad', shownImages: [null, 'keep.jpg']
}))
assert.equal(salvageable.preferences.playlists.length, 2)
assert.equal(salvageable.preferences.playlists[0]!.mediaVolume, 100)
assert.equal(salvageable.preferences.playlists[1]!.id, 'kept-2')
assert.equal(salvageable.preferences.selected, playlist.id)
assert.deepEqual(salvageable.preferences.favorites, [])
assert.deepEqual(salvageable.preferences.shownImages, ['keep.jpg'])
assert.equal(salvageable.preferences.schemaVersion, playbackSchemaVersion)
assert.ok(salvageable.issues.length > 0)
const unusable = recoverPreferences('{broken')
assert.equal(unusable.preferences.playlists.length, 0)
assert.equal(unusable.issues.length, 1)
assert.match(unusable.issues[0]!, /备份|recoverPreferences/)

// —— 已展示记录上限：超出按最早淘汰 ——
const many = Array.from({ length: shownImagesLimit + 5 }, (_, index) => `image-${index}.jpg`)
const capped = readPreferences(JSON.stringify({ playlists: [], selected: '', favorites: [], shownImages: many }))
assert.equal(capped.shownImages.length, shownImagesLimit)
assert.equal(capped.shownImages[0], many[5])
assert.equal(capped.shownImages.at(-1), many.at(-1))
assert.equal(new Set(capped.shownImages).size, shownImagesLimit)
assert.deepEqual(trimShownImages(['a', 'b']), ['a', 'b'])
assert.deepEqual(trimShownImages(['a', 'b', 'c'], 2), ['b', 'c'])
assert.deepEqual(trimShownImages([], 1), [])
const cycle = playbackCycle(images, options, Array.from({ length: shownImagesLimit + 2 }, (_, index) => `key-${index}`))
assert.equal(cycle.shownImages.length, shownImagesLimit)
assert.equal(cycle.reset, false)
assert.equal(cycle.queue.length, 2)

// —— 导出 / 导入：新格式往返一致，旧格式仍可导入 ——
const exported = exportConfiguration([{ ...playlist, roots: ['private-path'] }, second], playlist.id)
const exportedData = JSON.parse(exported) as Record<string, unknown>
assert.equal(exportedData.format, 'shicun.playback.config.v2')
assert.equal(exportedData.schemaVersion, 2)
assert.equal(exported.includes('private-path'), false)
const imported = importConfiguration(exported)
assert.equal(imported.schemaVersion, playbackSchemaVersion)
assert.equal(imported.selected, playlist.id)
assert.deepEqual(imported.favorites, [])
assert.deepEqual(imported.shownImages, [])
assert.equal(imported.playlists.length, 2)
assert.deepEqual(imported.playlists[0], { ...playlist, roots: [] })
assert.deepEqual(imported.playlists[1], { ...second, roots: [] })
assert.deepEqual(importConfiguration(exportConfiguration(imported.playlists, imported.selected)), imported)
const legacyConfig = JSON.stringify({
  format: 'shicun.playback.config.v1', selected: playlist.id,
  playlists: [legacyPlaylist, { ...second, imageCount: 5 }]
})
const legacyImported = importConfiguration(legacyConfig)
assert.equal(legacyImported.playlists.length, 2)
assert.equal(legacyImported.playlists[0]!.imageTiming, 'time')
assert.equal(legacyImported.playlists[0]!.brightness, 100)
assert.equal(legacyImported.playlists[0]!.id, playlist.id)
assert.equal(legacyImported.playlists[1]!.imageCount, 5)
assert.equal(legacyImported.selected, playlist.id)
assert.equal(validPlaylist(legacyImported.playlists[0]!), true)
assert.equal(importConfiguration(JSON.stringify({ format: playbackConfigFormat, selected: 'x', playlists: [{ ...playlist, imageCount: -1 }] })).playlists[0]!.imageCount, 0)
for (const bad of [
  '{broken', JSON.stringify(null), JSON.stringify({ format: 'other.v9', selected: '', playlists: [playlist] }),
  JSON.stringify({ format: playbackConfigFormat, selected: '', playlists: [] }),
  JSON.stringify({ format: legacyPlaybackConfigFormats[0]!, selected: '', playlists: [playlist, 'junk'] })
]) assert.throws(() => importConfiguration(bad), /播放配置/)
