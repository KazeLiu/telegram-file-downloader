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
