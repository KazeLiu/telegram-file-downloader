// 播放列表层的回归检查：存储键、字段夹取、配置导入导出、队列切分。
// v4 之后播放列表只剩媒体层，玩法字段全部搬进 settings.ts / engine.ts。
import assert from 'node:assert/strict'
import {
  clockTime, exportConfiguration, importConfiguration, legacyPlaybackConfigFormats, mediaKey, mediaUrl, newPlaylist,
  nextBeatTime, orderedMedia, playbackConfigFormat, playbackCycle, playbackSchemaVersion, playbackStorageKey,
  readPreferences, recoverPreferences, shownImagesLimit, trimShownImages, validPlaylist,
  type Playlist, type PlaybackMedia
} from '../src/playback.ts'

function messageOf(run: () => unknown) {
  try { run() } catch (error) { return (error as Error).message }
  return ''
}

// —— 版本与存储键 ——
assert.equal(playbackSchemaVersion, 4)
assert.equal(playbackStorageKey, 'shicun.playback.v1')
assert.equal(playbackConfigFormat, 'shicun.playback.config.v4')
assert.deepEqual(legacyPlaybackConfigFormats, ['shicun.playback.config.v1', 'shicun.playback.config.v2', 'shicun.playback.config.v3'])
assert.equal(shownImagesLimit, 20000)

// —— newPlaylist：默认值必须直接可用 ——
const playlist = newPlaylist()
assert.equal(validPlaylist(playlist), true)
assert.equal(playlist.name, '新播放列表')
assert.deepEqual(playlist.roots, [])
assert.equal(playlist.kind, 'mixed')
assert.equal(playlist.order, 'shuffle')
assert.equal(playlist.imageTiming, 'time')
assert.equal(playlist.imageSeconds, 8)
assert.equal(playlist.bpm, 100)
assert.equal(playlist.imageCount, 0)
assert.equal(playlist.mediaVolume, 100)
assert.equal(playlist.hideTime, false)
assert.equal(playlist.brightness, 100)
assert.equal(playlist.loop, true)
assert.equal(playlist.favoritesOnly, false)
// 玩法字段已经搬走：播放列表里不该再出现它们。
for (const legacy of ['difficulty', 'ratioFast', 'ratioSlow', 'ratioRest', 'permitBase', 'ending', 'edgeWindow', 'waitMode', 'waitPreset', 'waitMin', 'waitMax', 'instructionPace', 'tones', 'hand', 'commandTypes', 'props', 'customCommands', 'disabledCommands', 'heartbeat', 'heartbeatVolume', 'vibrate', 'voicePitch', 'speech', 'speechVolume', 'speechRate']) {
  assert.equal(legacy in playlist, false, `播放列表不应再带 ${legacy}`)
}

// —— validPlaylist：逐字段边界 ——
const base: Playlist = { ...playlist }
assert.equal(validPlaylist({ ...base, name: '' }), false, '空名称不合法')
assert.equal(validPlaylist({ ...base, name: 'x'.repeat(80) }), true, '80 字名称合法')
assert.equal(validPlaylist({ ...base, name: 'x'.repeat(81) }), false, '81 字名称不合法')
assert.equal(validPlaylist({ ...base, roots: ['/a'] }), true)
assert.equal(validPlaylist({ ...base, roots: [1] as unknown as string[] }), false, '图库必须是字符串')
assert.equal(validPlaylist({ ...base, kind: 'audio' as Playlist['kind'] }), false)
assert.equal(validPlaylist({ ...base, order: 'random' as Playlist['order'] }), false)
assert.equal(validPlaylist({ ...base, imageTiming: 'beat' }), true, '按节拍换图也合法')
assert.equal(validPlaylist({ ...base, imageTiming: 'nope' as Playlist['imageTiming'] }), false)
assert.equal(validPlaylist({ ...base, imageSeconds: 1 }), true)
assert.equal(validPlaylist({ ...base, imageSeconds: 300 }), true)
assert.equal(validPlaylist({ ...base, imageSeconds: 0 }), false)
assert.equal(validPlaylist({ ...base, imageSeconds: 301 }), false)
assert.equal(validPlaylist({ ...base, imageSeconds: 8.5 }), false, '必须是整数')
assert.equal(validPlaylist({ ...base, bpm: 20 }), true, 'bpm 下限已放宽到 20')
assert.equal(validPlaylist({ ...base, bpm: 300 }), true, 'bpm 上限已放宽到 300')
assert.equal(validPlaylist({ ...base, bpm: 19 }), false)
assert.equal(validPlaylist({ ...base, bpm: 301 }), false)
assert.equal(validPlaylist({ ...base, mediaVolume: 0 }), true)
assert.equal(validPlaylist({ ...base, mediaVolume: 100 }), true)
assert.equal(validPlaylist({ ...base, mediaVolume: 101 }), false)
assert.equal(validPlaylist({ ...base, brightness: 20 }), true)
assert.equal(validPlaylist({ ...base, brightness: 19 }), false, '变暗下限 20')
assert.equal(validPlaylist({ ...base, brightness: 100 }), true)
assert.equal(validPlaylist({ ...base, hideTime: 'yes' as unknown as boolean }), false)
assert.equal(validPlaylist({ ...base, loop: 1 as unknown as boolean }), false)
assert.equal(validPlaylist({ ...base, favoritesOnly: null as unknown as boolean }), false)
assert.equal(validPlaylist({ ...base, imageCount: 100000 }), true)
assert.equal(validPlaylist({ ...base, imageCount: -1 }), false)

// —— 存储：读回、升级、损坏 ——
const stored = JSON.stringify({
  schemaVersion: 3,
  playlists: [{ id: 'x', name: '老列表', roots: ['/g'], kind: 'image', order: 'sequential', difficulty: 'hard', ratioFast: 55, permitBase: 55 }],
  selected: 'x', favorites: [], shownImages: [],
})
const upgraded = readPreferences(stored)
assert.equal(upgraded.schemaVersion, 4, '旧版本要升级到 4')
assert.equal(upgraded.playlists.length, 1)
assert.equal(upgraded.playlists[0]!.name, '老列表')
assert.equal(upgraded.playlists[0]!.kind, 'image')
assert.equal(upgraded.playlists[0]!.order, 'sequential')
assert.equal('difficulty' in upgraded.playlists[0]!, false, '旧玩法字段必须被丢弃')
assert.equal(upgraded.selected, 'x')
assert.ok(messageOf(() => readPreferences('{bad')).includes('本机播放数据损坏'))
assert.ok(messageOf(() => readPreferences('[]')).includes('顶层不是对象'))
assert.ok(messageOf(() => readPreferences(JSON.stringify({ schemaVersion: 99, playlists: [] }))).includes('高于当前支持的'))
// 救数据出口不抛错。
const salvaged = recoverPreferences(JSON.stringify({ schemaVersion: 9, playlists: [{ id: 1, name: '', roots: 'oops' }] }))
assert.equal(salvaged.preferences.playlists.length, 1, '坏条目也要尽量救回来')
assert.equal(salvaged.preferences.playlists[0]!.name, '未命名播放列表')
assert.ok(salvaged.issues.length > 0, '救数据必须报告改动')
const broken = recoverPreferences('not json')
assert.deepEqual(broken.preferences.playlists, [])
assert.equal(broken.issues.length, 1)
// 字段夹取与修正报告。
const clamped = recoverPreferences(JSON.stringify({
  schemaVersion: 4, selected: 'p', favorites: ['a'], shownImages: [],
  playlists: [{ id: 'p', name: '  收窄  ', roots: ['/g'], kind: 'video', order: 'sequential', imageSeconds: 999, bpm: 9, imageCount: -5, mediaVolume: 300, brightness: 5, loop: 'no', favoritesOnly: 1, imageTiming: 'beat' }],
}))
const fixed = clamped.preferences.playlists[0]!
assert.equal(fixed.name, '收窄', '名称要去空白')
assert.equal(fixed.imageSeconds, 300)
assert.equal(fixed.bpm, 20)
assert.equal(fixed.imageCount, 0)
assert.equal(fixed.mediaVolume, 100)
assert.equal(fixed.brightness, 20)
assert.equal(fixed.loop, true)
assert.equal(fixed.favoritesOnly, false)
assert.equal(fixed.imageTiming, 'beat', '按节拍换图是合法值，应保留')
assert.ok(clamped.issues.some(issue => issue.includes('imageSeconds')), '修正必须报告')

// —— trimShownImages ——
assert.deepEqual(trimShownImages([], 3), [])
assert.deepEqual(trimShownImages(['a', 'b'], 3), ['a', 'b'])
assert.deepEqual(trimShownImages(['a', 'b', 'c', 'd'], 3), ['b', 'c', 'd'], '超出上限时保留最新的')
assert.deepEqual(trimShownImages(['a', 'b', 'c', 'd'], 0), [])

// —— 媒体 URL 与键 ——
const media: PlaybackMedia = { root: '/g', path: 'a b.jpg', name: 'a b.jpg', kind: 'image', version: 'v1' }
assert.equal(mediaUrl(media), '/api/playback/media?root=%2Fg&path=a+b.jpg&version=v1')
assert.equal(mediaKey(media), '["/g","a b.jpg"]')
assert.equal(mediaUrl({ ...media, path: 'x&y=1' }), '/api/playback/media?root=%2Fg&path=x%26y%3D1&version=v1', '特殊字符要转义')
assert.equal(mediaUrl({ ...media, root: '/r', path: '/deep/f. mp4', version: 'v 2' }), '/api/playback/media?root=%2Fr&path=%2Fdeep%2Ff.+mp4&version=v+2')

// —— clockTime 与节拍 ——
assert.equal(clockTime(0), '00:00')
assert.equal(clockTime(999), '00:01', '向上取整到秒')
assert.equal(clockTime(1000), '00:01')
assert.equal(clockTime(61000), '01:01')
assert.equal(clockTime(600000), '10:00')
assert.equal(clockTime(-5), '00:00')
assert.equal(clockTime(3599000), '59:59')
// nextBeatTime：首次立即给下一拍，之后按间隔推进。
assert.equal(nextBeatTime(0, 1000, 60), 2000, '没有上一拍时从当前时间起算一个间隔')
assert.equal(nextBeatTime(2000, 2100, 60), 3000, '按 bpm 60 → 1000ms 推进')
assert.equal(nextBeatTime(2000, 5000, 60), 6000, '已经落后时以当前时间为基准')
assert.equal(nextBeatTime(0, 0, 120), 500, 'bpm 120 → 500ms')

// —— orderedMedia：有序与随机 ——
const media2: PlaybackMedia[] = [1, 2, 3, 4, 5].map(index => ({ root: '/g', path: `${index}.jpg`, name: `${index}.jpg`, kind: 'image' as const, version: 'v1' }))
assert.deepEqual(orderedMedia(media2, 'sequential').map(item => item.path), ['1.jpg', '2.jpg', '3.jpg', '4.jpg', '5.jpg'])
const shuffled = orderedMedia(media2, 'shuffle').map(item => item.path).sort()
assert.deepEqual(shuffled, ['1.jpg', '2.jpg', '3.jpg', '4.jpg', '5.jpg'], '随机顺序不能丢项')
assert.notEqual(orderedMedia(media2, 'shuffle'), media2, '必须返回新数组')

// —— playbackCycle：图片去重、轮次重开 ——
const cycleMedia: PlaybackMedia[] = [
  ...['a', 'b', 'c'].map(name => ({ root: '/g', path: `${name}.jpg`, name: `${name}.jpg`, kind: 'image' as const, version: 'v1', identity: `id-${name}` })),
  { root: '/g', path: 'v.mp4', name: 'v.mp4', kind: 'video' as const, version: 'v1' },
]
const firstCycle = playbackCycle(cycleMedia, { ...playlist, kind: 'mixed', order: 'sequential', imageCount: 0 }, [])
assert.equal(firstCycle.queue.length, 4, '首轮全部可用')
assert.equal(firstCycle.reset, false)
assert.deepEqual(firstCycle.shownImages, [])
// 已展示过两张图片后，只剩一张图片 + 一个视频。
const secondCycle = playbackCycle(cycleMedia, { ...playlist, order: 'sequential', imageCount: 0 }, ['id-a', 'id-b'])
assert.equal(secondCycle.queue.length, 2)
assert.equal(secondCycle.queue.filter(item => item.kind === 'image').length, 1)
// imageCount 限制本轮图片数。
const limited = playbackCycle(cycleMedia, { ...playlist, order: 'sequential', imageCount: 1 }, [])
assert.equal(limited.queue.filter(item => item.kind === 'image').length, 1)
// 图片全看过时重开一轮并释放记录。
const exhausted = playbackCycle(cycleMedia, { ...playlist, order: 'sequential', imageCount: 0 }, ['id-a', 'id-b', 'id-c'])
assert.equal(exhausted.reset, true, '图片看完必须重开一轮')
assert.equal(exhausted.queue.filter(item => item.kind === 'image').length, 3)
assert.deepEqual(exhausted.shownImages, [], '重开一轮要释放已展示记录')
// 只看视频时不受图片限制。
const videosOnly = playbackCycle([cycleMedia[3]!], { ...playlist, order: 'sequential', imageCount: 0 }, [])
assert.equal(videosOnly.queue.length, 1)

// —— 配置导入导出 ——
const exported = JSON.parse(exportConfiguration([{ ...playlist, name: '列表 A', roots: ['/g'] }], playlist.id))
assert.equal(exported.format, 'shicun.playback.config.v4')
assert.equal(exported.schemaVersion, 4)
assert.equal(exported.selected, playlist.id)
assert.deepEqual(exported.playlists[0].roots, [], '导出不包含本机图库路径')
assert.equal(exported.playlists[0].name, '列表 A')
const reimported = importConfiguration(JSON.stringify(exported))
assert.equal(reimported.playlists.length, 1)
assert.deepEqual(reimported.playlists[0]!.roots, [], '导入后需要重新选图库')
// v3 配置也能导入。
const v3 = importConfiguration(JSON.stringify({ format: 'shicun.playback.config.v3', schemaVersion: 3, selected: 'q', playlists: [{ id: 'q', name: '旧', roots: [], difficulty: 'hard' }] }))
assert.equal(v3.playlists.length, 1)
assert.equal(v3.playlists[0]!.name, '旧')
assert.equal(v3.selected, 'q')
// 坏配置要给出可读错误。
assert.ok(messageOf(() => importConfiguration('nope')).includes('拾存导出的播放配置'))
assert.ok(messageOf(() => importConfiguration('{"format":"other"}')).includes('播放配置'))
assert.ok(messageOf(() => importConfiguration(JSON.stringify({ format: 'shicun.playback.config.v4', playlists: [] }))).length > 0, '缺少 selected 应当报错')

console.log('playback list checks passed')
