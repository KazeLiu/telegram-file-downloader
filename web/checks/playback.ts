import assert from 'node:assert/strict'
import {
  customCommandLimit, exportConfiguration, importConfiguration, legacyPlaybackConfigFormats, mediaKey, newPlaylist, nextBeatTime, playbackConfigFormat,
  playbackCycle, playbackSchemaVersion, playbackStorageKey, readPreferences, recoverPreferences, shownImagesLimit, trimShownImages,
  validPlaylist, type CommandType, type Playlist, type PlaybackMedia
} from '../src/playback.ts'

function messageOf(run: () => unknown) {
  try { run() } catch (error) { return (error as Error).message }
  return ''
}

// —— 版本与存储键 ——
assert.equal(playbackSchemaVersion, 3)
assert.equal(playbackStorageKey, 'shicun.playback.v1')
assert.equal(playbackConfigFormat, 'shicun.playback.config.v3')
assert.equal(legacyPlaybackConfigFormats[0], 'shicun.playback.config.v1')
assert.equal(legacyPlaybackConfigFormats[1], 'shicun.playback.config.v2')
assert.equal(legacyPlaybackConfigFormats.length, 2)
assert.equal(shownImagesLimit, 20000)
assert.equal(customCommandLimit, 30)

// —— newPlaylist 默认值与 validPlaylist 边界 ——
const playlist = newPlaylist()
assert.equal(playlist.imageTiming, 'time')
assert.equal(validPlaylist(playlist), true)
// v3 新增字段的默认值：addedDefaults / newPlaylist 必须给出可直接使用的完整列表。
assert.equal(playlist.difficulty, 'normal')
assert.equal(playlist.ratioFast, 60)
assert.equal(playlist.ratioSlow, 20)
assert.equal(playlist.ratioRest, 20)
assert.equal(playlist.ratioFast + playlist.ratioSlow + playlist.ratioRest, 100)
assert.equal(playlist.permitBase, 70)
assert.equal(playlist.ending, 'draw')
assert.equal(playlist.edgeWindow, 10)
assert.equal(playlist.waitMode, 'random')
assert.equal(playlist.waitPreset, '8-16')
assert.equal(playlist.waitMin, 8)
assert.equal(playlist.waitMax, 16)
assert.equal(playlist.instructionPace, 'standard')
assert.deepEqual(playlist.tones, ['firm'])
assert.equal(playlist.hand, 'right')
assert.deepEqual(playlist.commandTypes, ['fast', 'slow', 'rest', 'tease', 'nipple', 'glans'])
assert.deepEqual(playlist.props, [])
assert.deepEqual(playlist.customCommands, [])
assert.deepEqual(playlist.disabledCommands, [])
assert.equal(playlist.heartbeat, true)
assert.equal(playlist.heartbeatVolume, 100)
assert.equal(playlist.vibrate, 'off')
assert.equal(playlist.voicePitch, 'auto')
// 列表字段必须逐份拷贝：改一个播放列表不能连带改到别的播放列表。
const isolated = newPlaylist()
isolated.tones.push('gentle')
isolated.customCommands.push({ text: '听话', type: 'tease' })
isolated.disabledCommands.push('fast-1')
assert.deepEqual(playlist.tones, ['firm'])
assert.deepEqual(playlist.customCommands, [])
assert.deepEqual(playlist.disabledCommands, [])
assert.notEqual(isolated.tones, playlist.tones)
assert.equal(isolated.tones.length, 2, '同一个播放列表内仍可自由增删')
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

// —— v3 新字段的 validPlaylist 区间 ——
assert.equal(validPlaylist({ ...playlist, difficulty: 'hell' }), true)
assert.equal(validPlaylist({ ...playlist, difficulty: 'impossible' as Playlist['difficulty'] }), false)
assert.equal(validPlaylist({ ...playlist, permitBase: 30 }), true)
assert.equal(validPlaylist({ ...playlist, permitBase: 95 }), true)
assert.equal(validPlaylist({ ...playlist, permitBase: 29 }), false)
assert.equal(validPlaylist({ ...playlist, permitBase: 96 }), false)
assert.equal(validPlaylist({ ...playlist, permitBase: 70.5 }), false)
assert.equal(validPlaylist({ ...playlist, ending: 'overtime' }), true)
assert.equal(validPlaylist({ ...playlist, ending: 'random' as Playlist['ending'] }), false)
assert.equal(validPlaylist({ ...playlist, edgeWindow: 5 }), true)
assert.equal(validPlaylist({ ...playlist, edgeWindow: 60 }), true)
assert.equal(validPlaylist({ ...playlist, edgeWindow: 4 }), false)
assert.equal(validPlaylist({ ...playlist, edgeWindow: 61 }), false)
assert.equal(validPlaylist({ ...playlist, waitMode: 'fixed' }), true)
assert.equal(validPlaylist({ ...playlist, waitMode: 'sometimes' as Playlist['waitMode'] }), false)
assert.equal(validPlaylist({ ...playlist, waitPreset: '20-60' }), true)
assert.equal(validPlaylist({ ...playlist, waitPreset: '1-2' as Playlist['waitPreset'] }), false)
assert.equal(validPlaylist({ ...playlist, waitMin: 3, waitMax: 120 }), true)
assert.equal(validPlaylist({ ...playlist, waitMin: 16, waitMax: 16 }), true)
assert.equal(validPlaylist({ ...playlist, waitMin: 2 }), false)
assert.equal(validPlaylist({ ...playlist, waitMax: 121 }), false)
assert.equal(validPlaylist({ ...playlist, waitMin: 20, waitMax: 10 }), false)
assert.equal(validPlaylist({ ...playlist, instructionPace: 'veryLong' }), true)
assert.equal(validPlaylist({ ...playlist, instructionPace: 'forever' as Playlist['instructionPace'] }), false)
assert.equal(validPlaylist({ ...playlist, hand: 'left' }), true)
assert.equal(validPlaylist({ ...playlist, hand: 'both' as Playlist['hand'] }), false)
assert.equal(validPlaylist({ ...playlist, heartbeat: false }), true)
assert.equal(validPlaylist({ ...playlist, heartbeat: 'yes' as unknown as boolean }), false)
assert.equal(validPlaylist({ ...playlist, heartbeatVolume: 0 }), true)
assert.equal(validPlaylist({ ...playlist, heartbeatVolume: 100 }), true)
assert.equal(validPlaylist({ ...playlist, heartbeatVolume: 101 }), false)
assert.equal(validPlaylist({ ...playlist, heartbeatVolume: -1 }), false)
assert.equal(validPlaylist({ ...playlist, vibrate: 'edge' }), true)
assert.equal(validPlaylist({ ...playlist, vibrate: 'always' as Playlist['vibrate'] }), false)
assert.equal(validPlaylist({ ...playlist, voicePitch: 'high' }), true)
assert.equal(validPlaylist({ ...playlist, voicePitch: 'chipmunk' as Playlist['voicePitch'] }), false)
// 三比例：各自 0–100 的整数，且合计必须正好 100。
assert.equal(validPlaylist({ ...playlist, ratioFast: 40, ratioSlow: 30, ratioRest: 30 }), true)
assert.equal(validPlaylist({ ...playlist, ratioFast: 100, ratioSlow: 0, ratioRest: 0 }), true)
assert.equal(validPlaylist({ ...playlist, ratioFast: 41, ratioSlow: 30, ratioRest: 30 }), false)
assert.equal(validPlaylist({ ...playlist, ratioFast: 101, ratioSlow: 0, ratioRest: 0 }), false)
assert.equal(validPlaylist({ ...playlist, ratioFast: -1, ratioSlow: 51, ratioRest: 50 }), false)
assert.equal(validPlaylist({ ...playlist, ratioFast: 60.5, ratioSlow: 19.5, ratioRest: 20 }), false)
// 已知项列表：空列表与未知项都不合法。
assert.equal(validPlaylist({ ...playlist, tones: ['firm', 'gentle'] }), true)
assert.equal(validPlaylist({ ...playlist, tones: [] }), false)
assert.equal(validPlaylist({ ...playlist, tones: ['unknown'] as unknown as Playlist['tones'] }), false)
assert.equal(validPlaylist({ ...playlist, commandTypes: ['fast'] }), true)
assert.equal(validPlaylist({ ...playlist, commandTypes: [] }), false)
assert.equal(validPlaylist({ ...playlist, commandTypes: ['unknown'] as unknown as Playlist['commandTypes'] }), false)
assert.equal(validPlaylist({ ...playlist, props: ['cup', 'aneros'] }), true)
assert.equal(validPlaylist({ ...playlist, props: ['banana'] }), false)
assert.equal(validPlaylist({ ...playlist, disabledCommands: ['fast-1', 'rest-4'] }), true)
assert.equal(validPlaylist({ ...playlist, disabledCommands: ['unknown'] }), false)
assert.equal(validPlaylist({ ...playlist, disabledCommands: ['fast-0'] }), false)
assert.equal(validPlaylist({ ...playlist, disabledCommands: [1] as unknown as string[] }), false)
// 自定义口令：≤30 条、每条 text 1–60 字、type 合法。
const command = (text: string, type: CommandType = 'fast') => ({ text, type })
assert.equal(validPlaylist({ ...playlist, customCommands: [command('再快一点')] }), true)
assert.equal(validPlaylist({ ...playlist, customCommands: Array.from({ length: 30 }, (_, index) => command(`第 ${index} 条`)) }), true)
assert.equal(validPlaylist({ ...playlist, customCommands: Array.from({ length: 31 }, (_, index) => command(`第 ${index} 条`)) }), false)
assert.equal(validPlaylist({ ...playlist, customCommands: [command('   ')] }), false)
assert.equal(validPlaylist({ ...playlist, customCommands: [command('字'.repeat(60))] }), true)
assert.equal(validPlaylist({ ...playlist, customCommands: [command('字'.repeat(61))] }), false)
assert.equal(validPlaylist({ ...playlist, customCommands: [{ text: '好', type: 'unknown' as CommandType }] }), false)
assert.equal(validPlaylist({ ...playlist, customCommands: ['junk'] as unknown as Playlist['customCommands'] }), false)

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
// v3 新增字段：迁移测试里要当作"旧数据本来没有"删掉。
const v3Fields = [
  'difficulty', 'ratioFast', 'ratioSlow', 'ratioRest', 'permitBase', 'ending', 'edgeWindow', 'waitMode', 'waitPreset',
  'waitMin', 'waitMax', 'instructionPace', 'tones', 'hand', 'commandTypes', 'props', 'customCommands', 'disabledCommands',
  'heartbeat', 'heartbeatVolume', 'vibrate', 'voicePitch'
] as const
const legacyPlaylist = { ...playlist } as Record<string, unknown>
for (const key of ['imageTiming', 'imageCount', 'mediaVolume', 'beatVolume', 'speechVolume', 'speechRate', 'hideTime', 'brightness', ...v3Fields] as const) delete legacyPlaylist[key]
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
// v1 数据缺 v3 新字段：按契约补默认值，列表本身仍然可读、可用。
assert.equal(upgraded.playlists[0]!.difficulty, 'normal')
assert.equal(upgraded.playlists[0]!.ratioFast, 60)
assert.equal(upgraded.playlists[0]!.ratioSlow, 20)
assert.equal(upgraded.playlists[0]!.ratioRest, 20)
assert.equal(upgraded.playlists[0]!.permitBase, 70)
assert.equal(upgraded.playlists[0]!.ending, 'draw')
assert.equal(upgraded.playlists[0]!.edgeWindow, 10)
assert.equal(upgraded.playlists[0]!.waitMode, 'random')
assert.equal(upgraded.playlists[0]!.waitPreset, '8-16')
assert.equal(upgraded.playlists[0]!.waitMin, 8)
assert.equal(upgraded.playlists[0]!.waitMax, 16)
assert.equal(upgraded.playlists[0]!.instructionPace, 'standard')
assert.deepEqual(upgraded.playlists[0]!.tones, ['firm'])
assert.equal(upgraded.playlists[0]!.hand, 'right')
assert.deepEqual(upgraded.playlists[0]!.commandTypes, ['fast', 'slow', 'rest', 'tease', 'nipple', 'glans'])
assert.deepEqual(upgraded.playlists[0]!.props, [])
assert.deepEqual(upgraded.playlists[0]!.customCommands, [])
assert.deepEqual(upgraded.playlists[0]!.disabledCommands, [])
assert.equal(upgraded.playlists[0]!.heartbeat, true)
assert.equal(upgraded.playlists[0]!.heartbeatVolume, 100)
assert.equal(upgraded.playlists[0]!.vibrate, 'off')
assert.equal(upgraded.playlists[0]!.voicePitch, 'auto')
assert.equal(validPlaylist(upgraded.playlists[0]!), true)
assert.equal(upgraded.playlists[0]!.id, playlist.id)
assert.equal(upgraded.playlists[0]!.name, playlist.name)
assert.deepEqual(upgraded.favorites, ['downloads/a.jpg', 'downloads/b.jpg'])
assert.deepEqual(upgraded.shownImages, ['downloads/a.jpg', 'downloads/c.jpg', 'downloads/d.jpg'])
assert.equal(upgraded.selected, second.id)
// 升级后的对象就是写回本机的形态：带 schemaVersion 3，且再次读取不再产生迁移。
const writtenBack = JSON.parse(JSON.stringify(upgraded)) as Record<string, unknown>
assert.equal(writtenBack.schemaVersion, 3)
assert.deepEqual(readPreferences(JSON.stringify(upgraded)), upgraded)
const partialV1 = readPreferences(JSON.stringify({ playlists: [legacyPlaylist], selected: playlist.id, favorites: ['kept'] }))
assert.deepEqual(partialV1.shownImages, [])
assert.deepEqual(partialV1.favorites, ['kept'])
assert.equal(partialV1.schemaVersion, playbackSchemaVersion)
assert.deepEqual(readPreferences(JSON.stringify({ playlists: [legacyPlaylist], selected: 'missing', favorites: [] })).selected, playlist.id)

// —— 迁移：v2（有 v1 字段、没有 v3 新字段）无损升级到 v3 ——
const v2Playlist = { ...playlist, id: 'v2-list', name: 'v2 列表', minutes: 25, bpm: 140, mediaVolume: 40 } as Record<string, unknown>
for (const key of v3Fields) delete v2Playlist[key]
const v2Read = readPreferences(JSON.stringify({ schemaVersion: 2, playlists: [v2Playlist], selected: 'v2-list', favorites: ['kept.jpg'], shownImages: [] }))
assert.equal(v2Read.schemaVersion, playbackSchemaVersion)
assert.equal(v2Read.playlists.length, 1)
assert.equal(v2Read.playlists[0]!.id, 'v2-list')
assert.equal(v2Read.playlists[0]!.name, 'v2 列表')
// 旧字段原样保留
assert.equal(v2Read.playlists[0]!.minutes, 25)
assert.equal(v2Read.playlists[0]!.bpm, 140)
assert.equal(v2Read.playlists[0]!.mediaVolume, 40)
assert.equal(v2Read.playlists[0]!.imageTiming, 'time')
// 新字段补默认
assert.equal(v2Read.playlists[0]!.difficulty, 'normal')
assert.equal(v2Read.playlists[0]!.ratioSlow, 20)
assert.equal(v2Read.playlists[0]!.permitBase, 70)
assert.equal(v2Read.playlists[0]!.ending, 'draw')
assert.equal(v2Read.playlists[0]!.waitMax, 16)
assert.equal(v2Read.playlists[0]!.heartbeat, true)
assert.deepEqual(v2Read.favorites, ['kept.jpg'])
assert.equal(validPlaylist(v2Read.playlists[0]!), true)

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

// —— v3 新字段：非法值按契约区间修复，整份数据仍然可读 ——
const v3Repaired = readPreferences(JSON.stringify({
  playlists: [{
    ...playlist,
    difficulty: 'impossible', ratioFast: 40, ratioSlow: 40, ratioRest: 40,
    permitBase: 200, ending: 'sudden', edgeWindow: 0, waitMode: 'later', waitPreset: '2-3',
    waitMin: 500, waitMax: 1, instructionPace: 'slowest', tones: ['firm', 'unknown', 3],
    hand: 'both', commandTypes: ['fast', 'nope', 'slow', 'fast'], props: ['banana'],
    customCommands: [{ text: '好', type: 'fast' }, { text: '   ', type: 'fast' }, { text: '坏', type: 'nope' }, { text: 5, type: 'fast' }],
    disabledCommands: ['fast-1', 'junk', 'fast-0', 'fast-1'],
    heartbeat: 'yes', heartbeatVolume: 101, vibrate: 'always', voicePitch: 'robot'
  }]
}))
const v3Fixed = v3Repaired.playlists[0]!
assert.equal(v3Repaired.playlists.length, 1)
// 未知难度回落到 normal；三比例合计 120 不是 100，整组按 normal 档案重置。
assert.equal(v3Fixed.difficulty, 'normal')
assert.equal(v3Fixed.ratioFast, 60)
assert.equal(v3Fixed.ratioSlow, 20)
assert.equal(v3Fixed.ratioRest, 20)
// 超上界按区间上界夹住，不从默认值重来。
assert.equal(v3Fixed.permitBase, 95)
assert.equal(v3Fixed.edgeWindow, 5)
assert.equal(v3Fixed.heartbeatVolume, 100)
// 500 夹到 120、1 夹到 3，随后最小/最大颠倒，交换成 3/120。
assert.equal(v3Fixed.waitMin, 3)
assert.equal(v3Fixed.waitMax, 120)
// 枚举非法即回落默认值。
assert.equal(v3Fixed.ending, 'draw')
assert.equal(v3Fixed.waitMode, 'random')
assert.equal(v3Fixed.waitPreset, '8-16')
assert.equal(v3Fixed.instructionPace, 'standard')
assert.equal(v3Fixed.hand, 'right')
assert.equal(v3Fixed.vibrate, 'off')
assert.equal(v3Fixed.voicePitch, 'auto')
assert.equal(v3Fixed.heartbeat, true)
// 已知项列表只留合法项、去重；自定义口令只留格式正确且 text 非空的。
assert.deepEqual(v3Fixed.tones, ['firm'])
assert.deepEqual(v3Fixed.commandTypes, ['fast', 'slow'])
assert.deepEqual(v3Fixed.props, [])
assert.deepEqual(v3Fixed.customCommands, [{ text: '好', type: 'fast' }])
assert.deepEqual(v3Fixed.disabledCommands, ['fast-1'])
assert.equal(validPlaylist(v3Fixed), true)
// 修好之后再读一次不再产生迁移：幂等。
assert.deepEqual(readPreferences(JSON.stringify(v3Repaired)), v3Repaired)

// —— 三比例：合计不为 100 时按各自难度的默认档案归一 ——
const ratioOf = (raw: Record<string, unknown>) => {
  const fixed = readPreferences(JSON.stringify({ playlists: [{ ...playlist, ...raw }] })).playlists[0]!
  return [fixed.ratioFast, fixed.ratioSlow, fixed.ratioRest]
}
assert.deepEqual(ratioOf({ difficulty: 'hard', ratioFast: 50, ratioSlow: 50, ratioRest: 50 }), [55, 20, 25])
assert.deepEqual(ratioOf({ difficulty: 'hell', ratioFast: 10, ratioSlow: 10, ratioRest: 10 }), [45, 20, 35])
assert.deepEqual(ratioOf({ difficulty: 'easy', ratioFast: 100, ratioSlow: 100, ratioRest: 100 }), [50, 30, 20])
// 合计正好 100 时保持用户自选的分配，不被覆盖。
assert.deepEqual(ratioOf({ difficulty: 'hard', ratioFast: 50, ratioSlow: 30, ratioRest: 20 }), [50, 30, 20])
// 单个比例越界先夹到 0–100，合计仍不对时再整组归一。
assert.deepEqual(ratioOf({ difficulty: 'normal', ratioFast: 120, ratioSlow: 20, ratioRest: -20 }), [60, 20, 20])
// 比例不是整数：四舍五入成整数（59.6+20.4+20 = 100，因此不触发归一）。
assert.deepEqual(ratioOf({ difficulty: 'normal', ratioFast: 59.6, ratioSlow: 20.4, ratioRest: 20 }), [60, 20, 20])
// 只把最小/最大颠倒，不整组重置。
const swappedWait = readPreferences(JSON.stringify({ playlists: [{ ...playlist, waitMin: 30, waitMax: 10 }] })).playlists[0]!
assert.equal(swappedWait.waitMin, 10)
assert.equal(swappedWait.waitMax, 30)
assert.equal(validPlaylist(swappedWait), true)
// 自定义口令超上限：保留最早的 30 条，其余截掉但仍可读。
const tooManyCommands = readPreferences(JSON.stringify({
  playlists: [{ ...playlist, customCommands: Array.from({ length: 35 }, (_, index) => ({ text: `第${index}条`, type: 'fast' })) }]
})).playlists[0]!
assert.equal(tooManyCommands.customCommands.length, customCommandLimit)
assert.equal(tooManyCommands.customCommands[0]!.text, '第0条')
assert.equal(validPlaylist(tooManyCommands), true)
// 单条口令超 60 字：截断而不是丢弃。
const longCommand = readPreferences(JSON.stringify({
  playlists: [{ ...playlist, customCommands: [{ text: '字'.repeat(80), type: 'tease' }] }]
})).playlists[0]!
assert.equal(longCommand.customCommands[0]!.text.length, 60)
assert.equal(longCommand.customCommands[0]!.type, 'tease')

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
assert.equal(exportedData.format, 'shicun.playback.config.v3')
assert.equal(exportedData.schemaVersion, 3)
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
// 导入旧 v1 文件：新字段全部补默认值，返回的永远是当前 schemaVersion。
assert.equal(legacyImported.schemaVersion, 3)
assert.equal(legacyImported.playlists[0]!.difficulty, 'normal')
assert.equal(legacyImported.playlists[0]!.ratioFast, 60)
assert.equal(legacyImported.playlists[0]!.permitBase, 70)
assert.deepEqual(legacyImported.playlists[0]!.tones, ['firm'])
assert.equal(legacyImported.playlists[0]!.heartbeatVolume, 100)
assert.equal(legacyImported.playlists[0]!.vibrate, 'off')
assert.equal(legacyImported.playlists[0]!.voicePitch, 'auto')
// 导入旧 v2 文件：同样就地升级到 v3，旧字段一个不丢。
const v2Imported = importConfiguration(JSON.stringify({ format: legacyPlaybackConfigFormats[1]!, selected: 'v2-list', playlists: [v2Playlist] }))
assert.equal(v2Imported.schemaVersion, 3)
assert.equal(v2Imported.playlists.length, 1)
assert.equal(v2Imported.playlists[0]!.id, 'v2-list')
assert.equal(v2Imported.playlists[0]!.minutes, 25)
assert.equal(v2Imported.playlists[0]!.bpm, 140)
assert.equal(v2Imported.playlists[0]!.mediaVolume, 40)
assert.equal(v2Imported.playlists[0]!.difficulty, 'normal')
assert.equal(v2Imported.playlists[0]!.ending, 'draw')
assert.equal(v2Imported.playlists[0]!.waitMax, 16)
assert.equal(v2Imported.selected, 'v2-list')
assert.equal(validPlaylist(v2Imported.playlists[0]!), true)
assert.equal(importConfiguration(JSON.stringify({ format: playbackConfigFormat, selected: 'x', playlists: [{ ...playlist, imageCount: -1 }] })).playlists[0]!.imageCount, 0)
for (const bad of [
  '{broken', JSON.stringify(null), JSON.stringify({ format: 'other.v9', selected: '', playlists: [playlist] }),
  JSON.stringify({ format: playbackConfigFormat, selected: '', playlists: [] }),
  JSON.stringify({ format: legacyPlaybackConfigFormats[0]!, selected: '', playlists: [playlist, 'junk'] })
]) assert.throws(() => importConfiguration(bad), /播放配置/)
