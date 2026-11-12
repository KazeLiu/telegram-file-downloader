import assert from 'node:assert/strict'
import { newPlaylist, nextBeatTime, readPreferences, validPlaylist } from '../src/playback.ts'

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
