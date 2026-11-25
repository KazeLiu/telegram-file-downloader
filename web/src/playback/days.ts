// 连续天数（每日打卡）：参考站 sundome:days 的移植，只存在这台设备里。
// 规则：同一天再玩不加天；隔一天就清零；里程碑按 3/7/14/30 天递进。

export interface EdgeDays {
  /** 最近一次玩是哪一天（YYYY-MM-DD，本机时区） */
  last: string
  /** 当前连续天数 */
  run: number
  /** 历史最高连续天数 */
  best: number
}

export interface EdgeDaysView {
  run: number
  best: number
  /** 今天是否已经玩过 */
  today: boolean
}

export const daysStorageKey = 'shicun.edge.days.v1'

export const emptyDays: EdgeDays = { last: '', run: 0, best: 0 }

/** 里程碑阶梯，与参考站 `nextMilestone` 一致。 */
export const dayMilestones = [3, 7, 14, 30]

export const daysText = {
  unit: '天',
  fresh: '连续纪录',
  doneToday: '今天的已完成。',
  reset: '断一天就清零',
  bestNow: '正在刷新最高纪录'
}

function pad(value: number) {
  return String(value).padStart(2, '0')
}

/** 本机时区的 YYYY-MM-DD。 */
export function dayKey(value: number | Date) {
  const date = value instanceof Date ? value : new Date(value)
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function dayNumber(key: string) {
  const [year, month, day] = key.split('-').map(Number)
  return Date.UTC(year ?? 0, (month ?? 1) - 1, day ?? 1)
}

/** 两个日期相差几天（按天取整，跳过夏令时）。 */
export function daysBetween(from: string, to: string) {
  return Math.round((dayNumber(to) - dayNumber(from)) / 86_400_000)
}

function validKey(value: unknown): string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : ''
}

function count(value: unknown, fallback = 0) {
  const parsed = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(parsed)) return fallback
  return Math.min(99_999, Math.max(0, Math.floor(parsed)))
}

/** 坏数据一律归零，不抛错。 */
export function normalizeDays(value: unknown): EdgeDays {
  if (!value || typeof value !== 'object') return { ...emptyDays }
  const raw = value as Record<string, unknown>
  const last = validKey(raw.last)
  // 没有合法的最近日期就整条当空，避免「没玩过却有最高纪录」这种脏数据。
  if (!last) return { ...emptyDays }
  const run = Math.max(1, count(raw.run))
  return { last, run, best: Math.max(run, count(raw.best)) }
}

export function readDays(value: string | null): EdgeDays {
  if (!value) return { ...emptyDays }
  try {
    return normalizeDays(JSON.parse(value))
  } catch {
    return { ...emptyDays }
  }
}

export function writeDays(days: EdgeDays) {
  try {
    localStorage.setItem(daysStorageKey, JSON.stringify(days))
    return ''
  } catch {
    return '无法保存连续天数到本机，请检查浏览器存储空间或隐私设置。'
  }
}

/** 只看不改：当前天数、最高纪录、今天是否已经玩过。 */
export function daysView(days: EdgeDays, now = Date.now()): EdgeDaysView {
  if (!days.last) return { run: 0, best: 0, today: false }
  const gap = daysBetween(days.last, dayKey(now))
  return { run: gap >= 0 && gap <= 1 ? days.run : 0, best: days.best, today: gap === 0 }
}

/** 记一次今天玩过了：同一天不重复加，否则天数 +1。返回新的记录与视图。 */
export function addDay(days: EdgeDays, now = Date.now()) {
  const view = daysView(days, now)
  const run = view.today ? view.run : view.run + 1
  const next: EdgeDays = { last: dayKey(now), run, best: Math.max(view.best, run) }
  return { next, view: { run, best: next.best, today: true } as EdgeDaysView }
}

/** 下一个里程碑：3 / 7 / 14 / 30，之后每 30 天一档。 */
export function nextMilestone(run: number) {
  for (const step of dayMilestones) {
    if (run < step) return step
  }
  return (Math.floor(run / 30) + 1) * 30
}

/** 今天还剩几个小时（至少 1）。 */
export function hoursLeftToday(now = Date.now()) {
  const date = new Date(now)
  const midnight = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1).getTime()
  return Math.max(1, Math.ceil((midnight - now) / 3_600_000))
}

/** 设置页顶部那几行文案；没玩过时只给「今天玩就是第 1 天」。 */
export function daysSummary(days: EdgeDays, now = Date.now()) {
  const view = daysView(days, now)
  const lines: string[] = []
  if (view.run > 0) {
    lines.push(view.today ? `已连续 ${view.run} ${daysText.unit}` : `连续 ${view.run} ${daysText.unit}`)
    lines.push(view.today ? daysText.doneToday : `今天玩就是第 ${view.run + 1} 天。${daysText.reset}`)
    if (view.best > view.run) lines.push(`最高纪录 ${view.best} 天`)
    else lines.push(daysText.bestNow)
  } else {
    lines.push(daysText.fresh)
    lines.push(`今天玩就是第 1 天。${daysText.reset}`)
  }
  lines.push(`下一个目标：连续 ${nextMilestone(view.run)} 天`)
  if (!view.today) lines.push(`今天还剩 ${hoursLeftToday(now)} 小时`)
  return lines
}
