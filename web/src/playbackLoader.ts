import { mediaKey, mediaUrl, type PlaybackMedia, type Playlist } from './playback.ts'

export async function loadPlaybackQueue(options: Playlist, signal: AbortSignal, receive: (items: PlaybackMedia[], done: boolean) => Promise<void>) {
  const response = await fetch('/api/playback/queue/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ roots: options.roots, kind: options.kind }), signal })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(typeof error.detail === 'string' ? error.detail : '读取媒体列表失败，请返回列表重新开始。')
  }
  const reader = response.body!.getReader(), decoder = new TextDecoder()
  let pending = '', complete = false
  try {
    while (!complete) {
      const chunk = await reader.read()
      pending += decoder.decode(chunk.value, { stream: !chunk.done })
      let newline: number
      while ((newline = pending.indexOf('\n')) >= 0) {
        const batch = JSON.parse(pending.slice(0, newline))
        pending = pending.slice(newline + 1)
        if (batch.error) throw new Error(batch.error)
        complete = batch.done === true
        await receive(batch.items, complete)
      }
      if (chunk.done && !complete) throw new Error('媒体列表传输中断，请返回列表重新开始。')
    }
  } finally { await reader.cancel(); reader.releaseLock() }
}

interface BufferedImage { controller: AbortController; promise: Promise<string>; url?: string }
export class PlaybackImageBuffer {
  private entries = new Map<string, BufferedImage>()
  private generation = 0

  async show(item: PlaybackMedia) {
    const cached = this.entries.has(`${mediaKey(item)}:${item.version}`)
    const url = await this.load(item)
    if (cached) {
      const response = await fetch(mediaUrl(item), { method: 'HEAD', cache: 'no-store' })
      if (!response.ok) throw new Error('图片已移动或变化，请返回列表重新开始。')
    }
    return url
  }

  remove(item: PlaybackMedia) {
    const key = `${mediaKey(item)}:${item.version}`, entry = this.entries.get(key)
    if (!entry) return
    entry.controller.abort()
    if (entry.url) URL.revokeObjectURL(entry.url)
    this.entries.delete(key)
  }

  load(item: PlaybackMedia) {
    const key = `${mediaKey(item)}:${item.version}`
    const cached = this.entries.get(key)
    if (cached) return cached.promise
    const controller = new AbortController()
    const entry: BufferedImage = { controller, promise: fetch(mediaUrl(item), { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('图片读取失败，文件可能已移动或变化，请重试或返回列表重新开始。')
      const blob = await response.blob()
      if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError')
      entry.url = URL.createObjectURL(blob)
      return entry.url
    }).catch(error => { if (this.entries.get(key) === entry) this.entries.delete(key); throw error }) }
    this.entries.set(key, entry)
    return entry.promise
  }

  async fill(items: PlaybackMedia[]) {
    const generation = ++this.generation
    const keep = new Set(items.map(item => `${mediaKey(item)}:${item.version}`))
    for (const [key, entry] of this.entries) if (!keep.has(key)) {
      entry.controller.abort()
      if (entry.url) URL.revokeObjectURL(entry.url)
      this.entries.delete(key)
    }
    // Two workers keep prefetching from competing with the current image or flooding mobile connections.
    let next = 0
    const worker = async () => {
      while (generation === this.generation && next < items.length) {
        const item = items[next++]!
        if (!keep.has(`${mediaKey(item)}:${item.version}`)) return
        try { await this.load(item) } catch { return }
        if (!this.entries.has(`${mediaKey(item)}:${item.version}`)) return
      }
    }
    await Promise.all([worker(), worker()])
  }

  clear() {
    this.generation++
    for (const entry of this.entries.values()) { entry.controller.abort(); if (entry.url) URL.revokeObjectURL(entry.url) }
    this.entries.clear()
  }
}
