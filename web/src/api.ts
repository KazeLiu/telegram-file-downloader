export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message) }
}

export async function api<T = any>(path: string, body?: unknown, method = 'POST'): Promise<T> {
  const response = await fetch(`/api${path}`, body === undefined ? { cache: 'no-store' } : {
    method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  const result = await response.json()
  if (!response.ok) throw new ApiError(typeof result.detail === 'string' ? result.detail : '请检查填写内容后重试', response.status)
  return result
}

export interface Settings {
  api_id: string; api_hash_saved: boolean; chat: string; chat_title: string
  proxy_type: string; proxy_host: string; proxy_port: string; proxy_username: string; proxy_password_saved: boolean
  videos: boolean; photos: boolean; archives: boolean; extract: boolean; delete_archive: boolean
  archive_passwords_count: number; receipts: boolean; mark_read: boolean; enabled: boolean
}
export interface Task {
  id: number; filename: string; status: string; kind: string; size: number; downloaded: number
  speed: number; average_speed: number; elapsed: number; eta: number | null; quality: string
  created_at: string; started_at: string | null; completed_at: string | null
  path: string; output: string; error: string; warning: string; archive_deleted: boolean; message_id: number
}
export interface Status {
  phase: string; connection: string; account: { name: string; username: string; id: number } | null
  error: string | null; pending: boolean; download_dir: string; data_dir: string
  extractor_available: boolean; counts: Record<string, number>; total_bytes: number; active: Task | null
}
export const taskLabels: Record<string, string> = {
  queued: '等待下载', downloading: '下载中', downloaded: '下载完成', extracting: '解压中', completed: '已下载',
  extracted: '已解压', failed: '下载失败', extraction_failed: '待处理', interrupted: '等待恢复',
}
export const phaseLabels: Record<string, string> = {
  unconfigured: '尚未连接', connecting: '正在连接', phone: '等待登录', code: '等待验证码', password: '两步验证',
  choose_chat: '请选择群', ready: '已暂停收集', watching: '正在收集', connection_error: '连接异常',
}
export function bytes(value = 0): string {
  if (!value) return '0 B'
  const index = Math.min(Math.floor(Math.log(Math.max(value, 1)) / Math.log(1024)), 4)
  return `${(value / 1024 ** index).toFixed(index ? 1 : 0)} ${['B', 'KB', 'MB', 'GB', 'TB'][index]}`
}
export function duration(seconds: number | null): string {
  if (seconds === null) return '计算中'
  if (seconds < 60) return `${Math.ceil(seconds)} 秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分 ${Math.floor(seconds % 60)} 秒`
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor(seconds % 3600 / 60)} 分`
}
export function date(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '—'
}
export function percent(task: Task): number { return task.size ? Math.min(100, task.downloaded / task.size * 100) : 0 }
