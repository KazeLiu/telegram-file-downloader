export type MediaKind = 'image' | 'video' | 'mixed'
export type ImageTiming = 'time' | 'beat'
export interface Gallery { id: string; path: string }
export interface PlaybackMedia { root: string; path: string; name: string; kind: 'image' | 'video'; version: string; identity?: string }
export interface Playlist {
  id: string; name: string; roots: string[]; kind: MediaKind; order: 'sequential' | 'shuffle'
  imageSeconds: number; imageTiming: ImageTiming; minutes: number; loop: boolean; bpm: number; metronome: boolean; speech: boolean; favoritesOnly: boolean
  imageCount: number; mediaVolume: number; beatVolume: number; speechVolume: number; speechRate: number; hideTime: boolean; brightness: number
}
export interface PlaybackPreferences { playlists: Playlist[]; selected: string; favorites: string[]; shownImages: string[] }
export const playbackStorageKey = 'shicun.playback.v1'
const addedDefaults = { imageTiming: 'time' as ImageTiming, imageCount: 0, mediaVolume: 100, beatVolume: 100, speechVolume: 100, speechRate: 1, hideTime: false, brightness: 100 }

export function newPlaylist(): Playlist {
  return { id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`, name: '新播放列表', roots: [], kind: 'mixed', order: 'shuffle', imageSeconds: 8,
    minutes: 10, loop: true, bpm: 100, metronome: false, speech: false, favoritesOnly: false, ...addedDefaults }
}

export function readPreferences(value: string): PlaybackPreferences {
  const data = JSON.parse(value)
  if (data && Array.isArray(data.playlists)) {
    for (const item of data.playlists) if (item && typeof item === 'object') {
      for (const [key, value] of Object.entries(addedDefaults)) if (item[key] === undefined) item[key] = value
    }
    if (data.shownImages === undefined) data.shownImages = []
  }
  if (!data || !Array.isArray(data.playlists) || typeof data.selected !== 'string' || !strings(data.favorites) || !strings(data.shownImages)
    || !data.playlists.every(validPlaylist)) {
    throw new Error('本机播放列表数据不完整；可重置播放设置后重新创建，图库原文件不受影响。')
  }
  return data
}

function strings(value: unknown): value is string[] { return Array.isArray(value) && value.every(item => typeof item === 'string') }
function numberIn(value: unknown, min: number, max: number) { return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value) && value >= min && value <= max }
export function validPlaylist(item: Playlist) {
  return item && typeof item.id === 'string' && typeof item.name === 'string' && !!item.name.trim() && item.name.length <= 80
    && strings(item.roots) && ['image', 'video', 'mixed'].includes(item.kind) && ['sequential', 'shuffle'].includes(item.order)
    && numberIn(item.imageSeconds, 1, 300) && numberIn(item.minutes, 0, 180) && numberIn(item.bpm, 30, 180)
    && ['time', 'beat'].includes(item.imageTiming) && numberIn(item.imageCount, 0, 100000)
    && numberIn(item.mediaVolume, 0, 100) && numberIn(item.beatVolume, 0, 100) && numberIn(item.speechVolume, 0, 100)
    && [.8, 1, 1.2].includes(item.speechRate) && typeof item.hideTime === 'boolean' && numberIn(item.brightness, 20, 100)
    && typeof item.loop === 'boolean' && typeof item.metronome === 'boolean' && typeof item.speech === 'boolean' && typeof item.favoritesOnly === 'boolean'
}

export function mediaUrl(item: PlaybackMedia) {
  return `/api/playback/media?${new URLSearchParams({ root: item.root, path: item.path, version: item.version })}`
}
export function mediaKey(item: PlaybackMedia) { return JSON.stringify([item.root, item.path]) }
export function imageKey(item: PlaybackMedia) { return item.identity || mediaKey(item) }
export function clockTime(milliseconds: number) {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000))
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`
}
export function nextBeatTime(previous: number, now: number, bpm: number) {
  const interval = 60000 / bpm
  const next = previous + interval
  return previous > 0 && next > now ? next : now + interval
}
export function orderedMedia(items: PlaybackMedia[], order: Playlist['order']) {
  // shortcut: streamed playback shuffles arriving batches; use a shared inventory index if uniform whole-library sampling is required.
  const result = items.slice()
  if (order === 'shuffle') for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[result[i], result[j]] = [result[j]!, result[i]!]
  }
  return result
}

export function playbackCycle(items: PlaybackMedia[], options: Playlist, shownImages: string[]) {
  const imageKeys = new Set(items.filter(item => item.kind === 'image').map(imageKey))
  const shown = new Set(shownImages)
  const available = [...imageKeys].filter(key => !shown.has(key)).length
  const count = Math.min(options.imageCount || available || imageKeys.size, imageKeys.size)
  const reset = available < count
  let selected = 0
  const queue = orderedMedia(items.filter(item => item.kind !== 'image' || reset || !shown.has(imageKey(item))), options.order)
    .filter(item => item.kind !== 'image' || selected++ < count)
  return { queue, shownImages: reset ? shownImages.filter(key => !imageKeys.has(key)) : shownImages, reset }
}

export function exportConfiguration(playlists: Playlist[], selected: string) {
  return JSON.stringify({ format: 'shicun.playback.config.v1', selected, playlists: playlists.map(item => ({ ...item, roots: [] })) }, null, 2)
}

export function importConfiguration(value: string) {
  const data = JSON.parse(value)
  if (data?.format !== 'shicun.playback.config.v1' || !Array.isArray(data.playlists) || !data.playlists.length
    || typeof data.selected !== 'string' || data.playlists.some((item: unknown) => !item || typeof item !== 'object')) throw new Error('请选择拾存导出的播放配置 JSON 文件。')
  const result = readPreferences(JSON.stringify({ playlists: data.playlists.map((item: Playlist) => ({ ...item, roots: [] })), selected: data.selected, favorites: [] }))
  if (new Set(result.playlists.map(item => item.id)).size !== result.playlists.length) throw new Error('配置中存在重复的播放列表。')
  if (!result.playlists.some(item => item.id === result.selected)) result.selected = result.playlists[0]!.id
  return result
}
