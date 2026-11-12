import assert from 'node:assert/strict'
import { exportConfiguration, importConfiguration, mediaKey, newPlaylist, nextBeatTime, playbackCycle, readPreferences, validPlaylist, type PlaybackMedia } from '../src/playback.ts'

const playlist = newPlaylist()
assert.equal(playlist.imageTiming, 'time')
assert.ok(validPlaylist({ ...playlist, kind: 'image', imageTiming: 'beat' }))
const { imageTiming, ...legacy } = playlist
assert.equal(readPreferences(JSON.stringify({ playlists: [legacy], selected: playlist.id, favorites: ['kept'] })).playlists[0]!.imageTiming, 'time')
assert.throws(() => readPreferences(JSON.stringify({ playlists: [{ ...playlist, imageTiming: 'unknown' }], selected: playlist.id, favorites: [] })))

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

const old = { ...playlist } as Partial<typeof playlist>
for (const key of ['imageCount', 'mediaVolume', 'beatVolume', 'speechVolume', 'speechRate', 'brightness', 'hideTime'] as const) delete old[key]
const migrated = readPreferences(JSON.stringify({ playlists: [old], selected: playlist.id, favorites: ['kept'] }))
assert.equal(migrated.playlists[0]!.imageCount, 0)
assert.deepEqual(migrated.shownImages, [])
assert.deepEqual(migrated.favorites, ['kept'])
const exported = exportConfiguration([{ ...playlist, roots: ['private-path'] }], playlist.id)
assert.equal(exported.includes('private-path'), false)
assert.deepEqual(importConfiguration(exported).playlists[0]!.roots, [])
assert.throws(() => importConfiguration('{broken'))
assert.throws(() => importConfiguration(JSON.stringify({ format: 'shicun.playback.config.v1', selected: '', playlists: [{ ...playlist, imageCount: -1 }] })))
assert.throws(() => readPreferences(JSON.stringify({ playlists: [playlist], selected: '', favorites: [], shownImages: [null] })))
