export type MediaKind = 'image' | 'video' | 'mixed'
export interface Gallery { id: string; path: string }
export interface PlaybackMedia { root: string; path: string; name: string; kind: 'image' | 'video'; version: string }
export interface Playlist {
  id: string; name: string; roots: string[]; kind: MediaKind; order: 'sequential' | 'shuffle'
  imageSeconds: number; minutes: number; loop: boolean; bpm: number; metronome: boolean; speech: boolean; favoritesOnly: boolean
}
export interface PlaybackPreferences { playlists: Playlist[]; selected: string; favorites: string[] }
export const playbackStorageKey = 'shicun.playback.v1'

export function newPlaylist(): Playlist {
  return { id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`, name: '新播放列表', roots: [], kind: 'mixed', order: 'shuffle', imageSeconds: 8,
    minutes: 10, loop: true, bpm: 100, metronome: false, speech: false, favoritesOnly: false }
}

export function readPreferences(value: string): PlaybackPreferences {
  const data = JSON.parse(value)
  if (!data || !Array.isArray(data.playlists) || typeof data.selected !== 'string' || !strings(data.favorites)
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
    && typeof item.loop === 'boolean' && typeof item.metronome === 'boolean' && typeof item.speech === 'boolean' && typeof item.favoritesOnly === 'boolean'
}

export function mediaUrl(item: PlaybackMedia) {
  return `/api/playback/media?${new URLSearchParams({ root: item.root, path: item.path, version: item.version })}`
}
export function mediaKey(item: PlaybackMedia) { return JSON.stringify([item.root, item.path]) }
export function clockTime(milliseconds: number) {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000))
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`
}
export function orderedMedia(items: PlaybackMedia[], order: Playlist['order']) {
  const result = items.slice()
  if (order === 'shuffle') for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[result[i], result[j]] = [result[j]!, result[i]!]
  }
  return result
}
