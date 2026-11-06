import { photoDay } from './xiaomiMedia.ts'

export type WallPhoto = { id: string | number; sort_time: number | null }
export type PhotoGroup<T> = { key: string; items: T[] }
export type PhotoRow<T> = { key: string; group: PhotoGroup<T>; kind: 'day' | 'photos'; items: T[]; start: number }

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
    rows.push({ key: `day:${group.key}`, group, kind: 'day', items: [], start })
    for (let offset = 0; offset < group.items.length; offset += columns) {
      const items = group.items.slice(offset, offset + columns)
      rows.push({ key: `photos:${group.key}:${offset / columns}`, group, kind: 'photos', items, start })
      start += items.length
    }
  }
  return rows
}
