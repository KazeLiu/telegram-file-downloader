import assert from 'node:assert/strict'
import { loadPlaybackQueue, PlaybackImageBuffer } from '../src/playbackLoader.ts'
import { newPlaylist, type PlaybackMedia } from '../src/playback.ts'

const originalFetch = globalThis.fetch
try {
  const text = new TextEncoder().encode('{"items":[],"done":false}\n{"items":[],"done":true}\n')
  globalThis.fetch = async () => new Response(new ReadableStream({ start(controller) {
    controller.enqueue(text.slice(0, 12)); controller.enqueue(text.slice(12)); controller.close()
  } }))
  const received: boolean[] = []
  await loadPlaybackQueue(newPlaylist(), new AbortController().signal, async (_, done) => { received.push(done) })
  assert.deepEqual(received, [false, true])
  globalThis.fetch = async () => new Response('{"items":[]}\n')
  await assert.rejects(loadPlaybackQueue(newPlaylist(), new AbortController().signal, async () => {}), /传输中断/)
  globalThis.fetch = async () => new Response('{"error":"目录无法读取"}\n')
  await assert.rejects(loadPlaybackQueue(newPlaylist(), new AbortController().signal, async () => {}), /目录无法读取/)

  const calls: string[] = []
  globalThis.fetch = async (url, options) => {
    calls.push(`${options?.method || 'GET'} ${url}`)
    return new Response(new Blob(['fixture'], { type: 'image/jpeg' }))
  }
  const items: PlaybackMedia[] = Array.from({length: 40}, (_, i) => ({ root: 'downloads', path: `${i}.jpg`, name: `${i}.jpg`, kind: 'image', version: '1' }))
  const buffer = new PlaybackImageBuffer()
  await buffer.fill(items.slice(0, 20))
  assert.equal(calls.filter(call => call.startsWith('GET')).length, 20)
  await buffer.show(items[1]!)
  assert.equal(calls.filter(call => call.startsWith('GET')).length, 20)
  assert.equal(calls.filter(call => call.startsWith('HEAD')).length, 1)
  await buffer.fill(items.slice(1, 21))
  assert.equal(calls.filter(call => call.startsWith('GET')).length, 21)
  buffer.remove(items[1]!)
  await buffer.show(items[1]!)
  assert.equal(calls.filter(call => call.startsWith('GET')).length, 22)
  buffer.clear()
} finally { globalThis.fetch = originalFetch }
