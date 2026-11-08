import { reactive } from 'vue'
import type { CloudMedia } from './xiaomiMedia'

export type TimelineDay = { date: string; count: number; items: CloudMedia[]; page: number; removed: number; last: boolean; loading: boolean; error: string }
export type AlbumView = { days: TimelineDay[]; ready: boolean; stale: boolean; error: string; scroll: number; active: string; used: number }
const views = new Map<string, AlbumView>()
let owner = ''

export function albumView(connection: string, album: string) {
  const key = `${connection}:${album}`
  let view = views.get(key)
  if (!view || view.stale || Date.now() - view.used > 30 * 60_000) {
    view = reactive({ days: [], ready: false, stale: false, error: '', scroll: 0, active: '', used: Date.now() })
    views.set(key, view)
  }
  views.delete(key); views.set(key, view); view.used = Date.now()
  // Keep the current album intact; bound only the inactive views.
  let photos = 0, albums = 0
  for (const [id, cached] of [...views].reverse()) {
    albums++
    photos += cached.days.reduce((sum, day) => sum + day.items.length, 0)
    if (id !== key && (albums > 8 || photos > 20_000)) views.delete(id)
  }
  return view
}

export function accountViews(connection: string) {
  if (owner !== connection) { views.clear(); owner = connection }
}
export function invalidateAlbum(connection: string, album: string) {
  const view = views.get(`${connection}:${album}`)
  if (view) view.stale = true
}
export function invalidateOtherAlbums(connection: string, album: string) {
  for (const key of views.keys()) if (key.startsWith(`${connection}:`) && key !== `${connection}:${album}`) views.delete(key)
}

export function timelineLabel(day: string) {
  return `${day.slice(0, 4)}年${Number(day.slice(4, 6))}月${Number(day.slice(6, 8))}日`
}

export function mergeDay(day: TimelineDay, items: CloudMedia[], last: boolean, page: number) {
  const existing = new Set(day.items.map(item => item.id))
  day.items.push(...items.filter(item => !existing.has(item.id)).map(item => ({ ...item, timeline_day: day.date })))
  day.page = page + 1; day.removed = 0; day.last = last
  day.count = last ? day.items.length : Math.max(day.count, day.items.length + 1)
}

export function removeDayItems(day: TimelineDay, ids: Set<string>) {
  const removed = day.items.filter(item => ids.has(item.id)).length
  day.items = day.items.filter(item => !ids.has(item.id))
  day.count = Math.max(day.items.length, day.count - removed)
  day.removed += removed
}
