// 本机成绩记录：参考站的 sundome:stats 迁移而来，只存在这台设备里。
import type { FinishReason } from './types'

export interface EdgeStats {
  /** 一共玩了几局 */
  sessions: number
  /** 拿到许可（成功）的局数 */
  success: number
  /** 松手收场的局数 */
  ruin: number
  /** 没拿到许可的局数 */
  fail: number
  /** 累计忍住次数 */
  edges: number
  /** 累计玩了多少分钟 */
  minutes: number
  /** 单局最长坚持了多少分钟 */
  longest: number
}

export const statsStorageKey = 'shicun.edge.stats.v1'

export const emptyStats: EdgeStats = { sessions: 0, success: 0, ruin: 0, fail: 0, edges: 0, minutes: 0, longest: 0 }

function whole(value: unknown, fallback = 0) {
  const parsed = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(parsed) || parsed < 0) return fallback
  return Math.round(parsed)
}

/** 逐个字段夹取，坏数据一律归零，不抛错。 */
export function normalizeStats(value: unknown): EdgeStats {
  if (!value || typeof value !== 'object') return { ...emptyStats }
  const raw = value as Record<string, unknown>
  return {
    sessions: whole(raw.sessions),
    success: whole(raw.success),
    ruin: whole(raw.ruin),
    fail: whole(raw.fail),
    edges: whole(raw.edges),
    minutes: whole(raw.minutes),
    longest: whole(raw.longest)
  }
}

export function readStats(value: string | null): EdgeStats {
  if (!value) return { ...emptyStats }
  try {
    return normalizeStats(JSON.parse(value))
  } catch {
    return { ...emptyStats }
  }
}

export function writeStats(stats: EdgeStats) {
  try {
    localStorage.setItem(statsStorageKey, JSON.stringify(stats))
    return ''
  } catch {
    return '无法保存成绩到本机，请检查浏览器存储空间或隐私设置。'
  }
}

/** 参考站 addSession 的口径：success 只认 success，ruin / fail 各算各的。 */
export function addSession(stats: EdgeStats, outcome: FinishReason, minutes: number, edges: number): EdgeStats {
  const played = Math.max(0, Math.round(minutes))
  return {
    sessions: stats.sessions + 1,
    success: stats.success + (outcome === 'allow' || outcome === 'duration' ? 1 : 0),
    ruin: stats.ruin + (outcome === 'ruin' ? 1 : 0),
    fail: stats.fail + (outcome === 'deny' ? 1 : 0),
    edges: stats.edges + Math.max(0, Math.round(edges)),
    minutes: stats.minutes + played,
    longest: Math.max(stats.longest, played)
  }
}

/** 设置页顶部那行「至今 N 次 · 完成 N 次 …」，没玩过就返回空串。 */
export function statsSummary(stats: EdgeStats) {
  if (!stats.sessions) return ''
  const parts = [
    `至今 ${stats.sessions} 次`,
    `完成 ${stats.success} 次`,
    `禁止 ${stats.fail} 次`
  ]
  if (stats.ruin) parts.push(`松手 ${stats.ruin} 次`)
  parts.push(`忍住 ${stats.edges} 次`, `最长 ${stats.longest} 分钟`)
  return `${parts.join(' · ')}（本机记录）`
}

/** 「射了」单独记一档：中途结束了几次、最长坚持了多久（对齐参考站的 lost 存储）。 */
export interface LostRecord {
  /** 中途结束过几次 */
  count: number
  /** 中途结束的各局里最长坚持了多少毫秒 */
  bestMs: number
}

export const lostStorageKey = 'shicun.edge.lost.v1'

export const emptyLost: LostRecord = { count: 0, bestMs: 0 }

export function normalizeLost(value: unknown): LostRecord {
  if (!value || typeof value !== 'object') return { ...emptyLost }
  const raw = value as Record<string, unknown>
  return { count: whole(raw.count), bestMs: whole(raw.bestMs) }
}

export function readLost(value: string | null): LostRecord {
  if (!value) return { ...emptyLost }
  try {
    return normalizeLost(JSON.parse(value))
  } catch {
    return { ...emptyLost }
  }
}

export function writeLost(record: LostRecord) {
  try {
    localStorage.setItem(lostStorageKey, JSON.stringify(record))
    return ''
  } catch {
    return '无法保存记录到本机，请检查浏览器存储空间或隐私设置。'
  }
}

/** 记一次中途结束：次数 +1、最长取大；只有不是第一次且这次更久才算破纪录。 */
export function addLost(record: LostRecord, elapsedMs: number) {
  const span = Math.max(0, Math.round(elapsedMs))
  return {
    next: { count: record.count + 1, bestMs: Math.max(record.bestMs, span) } as LostRecord,
    isBest: record.count > 0 && span > record.bestMs
  }
}

/** 完成度百分比：中途结束时最多显示 99%，避免看成「已完成」。 */
export function lostPct(elapsedMs: number, minutes: number) {
  if (!(minutes > 0)) return 0
  return Math.min(99, Math.max(0, Math.floor((elapsedMs / (60_000 * minutes)) * 100)))
}
