// 历史成绩：最近 30 局的详细记录 + 累计计数，对齐参考站的 sundome:history / sundome:tally。
// 只存在这台设备里；累计次数不会被「清空详细记录」以外的操作改变。
import type { Difficulty } from './engine'
import type { FinishReason } from './types'

/** 详细记录里的结局：只记这四种（与参考站一致）。 */
export type RecordOutcome = 'success' | 'ruin' | 'fail' | 'lost'

export interface ResultRecord {
  /** 时间戳（毫秒） */
  t: number
  /** 结局 */
  o: RecordOutcome
  /** 设定时长（分钟） */
  m: number
  /** 这一局走过多少条指令 */
  c: number
  /** 忍住次数 */
  e: number
  /** 难度 */
  d: Difficulty
  /** 第几局（全局累计序号） */
  n: number
  /** 中途结束时撑了多久（毫秒），只有 lost 有 */
  ms?: number
  /** 加时赛加时了几次 */
  x?: number
  /** 是否用了「自己调」的混合比例 */
  k?: boolean
}

export interface Tally {
  /** 累计局数 */
  n: number
  /** 各结局的累计次数 */
  r: Record<RecordOutcome, number>
  /** 是否已经从旧版成绩迁移过 */
  seeded: boolean
}

export const recordsStorageKey = 'shicun.edge.history.v1'
export const tallyStorageKey = 'shicun.edge.tally.v1'
export const recordLimit = 30

export const recordOrder: RecordOutcome[] = ['success', 'ruin', 'fail', 'lost']

export const recordLabels: Record<RecordOutcome, string> = {
  success: '完成',
  ruin: '松手收场',
  fail: '禁止',
  lost: '中途结束'
}

/** 列表与详情的大标题：与参考站 doneTitle / LOST_TEXT.title 对齐。 */
export const recordTitles: Record<RecordOutcome, string> = {
  success: '坚持到底了',
  ruin: '松手收场',
  fail: '今天被禁止了',
  lost: '没忍住，射了'
}

/** 详情页的斜体眉标：参考站用英文大写（Finished / Ruined / Denied / Lost）。 */
export const recordEyebrows: Record<RecordOutcome, string> = {
  success: 'Finished',
  ruin: 'Ruined',
  fail: 'Denied',
  lost: 'Lost'
}

export const recordsText = {
  open: '记录',
  title: '历史成绩',
  note: '只保存在这台设备上。最近 30 次的详细记录，新的在前。累计次数不会被清掉。',
  empty: '还没有详细记录。从下一局开始保存。',
  back: '返回列表',
  close: '关闭',
  clear: '清空全部记录',
  clearAsk: '确定清空这台设备上的全部记录和累计次数吗？',
  clearYes: '全部清空',
  cancel: '取消',
  remove: '删除这条记录',
  removeAsk: '确定删除这条记录吗？（累计次数不会减少）',
  removeYes: '删除',
  total: '累计',
  nth: '累计第',
  stampAria: '集章 10 个中的第',
  stampNote: '每 10 次集满一张，次数没有上限'
}

export const emptyTally: Tally = { n: 0, r: { success: 0, ruin: 0, fail: 0, lost: 0 }, seeded: false }

function whole(value: unknown, min: number, max: number, fallback: number) {
  const parsed = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(parsed)) return fallback
  return Math.min(max, Math.max(min, Math.floor(parsed)))
}

/** 把结局映射成记录用的四类：允许/时间到算完成，其余按名字。 */
export function recordOutcome(outcome: FinishReason): RecordOutcome {
  if (outcome === 'allow' || outcome === 'duration') return 'success'
  if (outcome === 'ruin') return 'ruin'
  if (outcome === 'lost') return 'lost'
  return 'fail'
}

const difficulties: Difficulty[] = ['easy', 'normal', 'hard', 'hell']

function parseRecord(value: unknown): ResultRecord | null {
  if (!value || typeof value !== 'object') return null
  const raw = value as Record<string, unknown>
  const t = Number(raw.t)
  if (!Number.isFinite(t) || t <= 0) return null
  const o = String(raw.o)
  if (!recordOrder.includes(o as RecordOutcome)) return null
  const record: ResultRecord = {
    t,
    o: o as RecordOutcome,
    m: whole(raw.m, 1, 180, 10),
    c: whole(raw.c, 0, 999, 0),
    e: whole(raw.e, 0, 99, 0),
    d: difficulties.includes(raw.d as Difficulty) ? (raw.d as Difficulty) : 'normal',
    n: whole(raw.n, 0, 99_999, 0)
  }
  if (record.o === 'lost') record.ms = whole(raw.ms, 0, 10_800_000, 0)
  if (Number(raw.x) > 0) record.x = whole(raw.x, 1, 99, 1)
  if (raw.k === true) record.k = true
  return record
}

/** 坏记录直接丢掉，按时间倒序，最多 30 条。 */
export function parseRecords(value: unknown): ResultRecord[] {
  if (!Array.isArray(value)) return []
  return value
    .map(parseRecord)
    .filter((item): item is ResultRecord => item !== null)
    .sort((a, b) => b.t - a.t)
    .slice(0, recordLimit)
}

export function readRecords(value: string | null): ResultRecord[] {
  if (!value) return []
  try {
    return parseRecords(JSON.parse(value))
  } catch {
    return []
  }
}

export function writeRecords(records: ResultRecord[]) {
  try {
    localStorage.setItem(recordsStorageKey, JSON.stringify(records.slice(0, recordLimit)))
    return ''
  } catch {
    return '无法保存历史记录到本机，请检查浏览器存储空间或隐私设置。'
  }
}

export function normalizeTally(value: unknown): Tally {
  if (!value || typeof value !== 'object') return { ...emptyTally, r: { ...emptyTally.r } }
  const raw = value as Record<string, unknown>
  const counts = (raw.r && typeof raw.r === 'object' ? raw.r : {}) as Record<string, unknown>
  return {
    n: whole(raw.n, 0, 10_000_000, 0),
    r: {
      success: whole(counts.success, 0, 10_000_000, 0),
      ruin: whole(counts.ruin, 0, 10_000_000, 0),
      fail: whole(counts.fail, 0, 10_000_000, 0),
      lost: whole(counts.lost, 0, 10_000_000, 0)
    },
    seeded: raw.seeded === true
  }
}

export function readTally(value: string | null): Tally {
  if (!value) return { ...emptyTally, r: { ...emptyTally.r } }
  try {
    return normalizeTally(JSON.parse(value))
  } catch {
    return { ...emptyTally, r: { ...emptyTally.r } }
  }
}

export function writeTally(tally: Tally) {
  try {
    localStorage.setItem(tallyStorageKey, JSON.stringify(tally))
    return ''
  } catch {
    return '无法保存累计次数到本机，请检查浏览器存储空间或隐私设置。'
  }
}

/** 第一次用新结构时，把旧版成绩（stats + lost）折成累计次数，避免显示成 0 局。 */
export function tallyFromStats(tally: Tally, sessions: number, success: number, ruin: number, fail: number, lost: number): Tally {
  if (tally.seeded) return tally
  const base = Math.max(0, Math.round(sessions))
  return {
    n: base + Math.max(0, Math.round(lost)),
    r: {
      success: Math.max(0, Math.round(success)),
      ruin: Math.max(0, Math.round(ruin)),
      fail: Math.max(0, Math.round(fail)),
      lost: Math.max(0, Math.round(lost))
    },
    seeded: false
  }
}

/** 记一局：累计 +1、对应结局 +1，返回新的累计与这条记录要用的序号。 */
export function countResult(tally: Tally, outcome: FinishReason) {
  const key = recordOutcome(outcome)
  const next: Tally = {
    n: tally.n + 1,
    r: { ...tally.r, [key]: tally.r[key] + 1 },
    seeded: true
  }
  return { next, nth: next.n }
}

/** 插一条记录：新的在前，最多 30 条。 */
export function pushRecord(records: ResultRecord[], record: ResultRecord) {
  return [record, ...records].slice(0, recordLimit)
}

/** 集章：每 10 局一张，返回这一张上已点亮的数量（1–10）与总共满了几张。 */
export function stamps(nth: number) {
  const index = ((nth - 1) % 10) + 1
  return { index, sheets: Math.floor(Math.max(0, nth - 1) / 10) }
}

/** 日期时间文案：本机时区，`2026/11/25 10:32`。 */
export function recordTime(t: number) {
  const date = new Date(t)
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
