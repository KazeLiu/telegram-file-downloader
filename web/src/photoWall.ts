import { photoDay } from './xiaomiMedia.ts'

export type WallPhoto = { id: string | number; sort_time: number | null }
export type PhotoGroup<T> = { key: string; label?: string; count?: number; items: T[] }
export type PhotoRow<T> = { key: string; group: PhotoGroup<T>; kind: 'day' | 'photos'; items: T[]; start: number; count: number }

export function groupPhotos<T extends WallPhoto>(items: T[]): PhotoGroup<T>[] {
  const groups = new Map<string, PhotoGroup<T>>()
  for (const item of items) {
    const key = photoDay(item.sort_time)
    let group = groups.get(key)
    if (!group) { group = { key, items: [] }; groups.set(key, group) }
    group.items.push(item)
  }
  return [...groups.values()]
}

export function photoRows<T>(groups: PhotoGroup<T>[], columns: number): PhotoRow<T>[] {
  const rows: PhotoRow<T>[] = []
  let start = 0
  for (const group of groups) {
    const count = Math.max(group.count ?? 0, group.items.length)
    rows.push({ key: `day:${group.key}`, group, kind: 'day', items: [], start, count: 0 })
    for (let offset = 0; offset < count; offset += columns) {
      const items = group.items.slice(offset, offset + columns)
      const size = Math.min(columns, count - offset)
      rows.push({ key: `photos:${group.key}:${offset / columns}`, group, kind: 'photos', items, start, count: size })
      start += size
    }
  }
  return rows
}
