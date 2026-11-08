export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message) }
}

export async function api<T = any>(path: string, body?: unknown, method = 'POST', signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api${path}`, body === undefined ? { cache: 'no-store', signal } : {
    method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal,
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
  download_parallelism: 1 | 2 | 4
  parallel_files: number; flatten: boolean; delete_psd: boolean
}
export interface Task {
  id: number; filename: string; status: string; kind: string; size: number; downloaded: number
  speed: number; average_speed: number; elapsed: number; eta: number | null; quality: string
  created_at: string; started_at: string | null; completed_at: string | null
  path: string; output: string; error: string; warning: string; archive_deleted: boolean; message_id: number
  wait_until?: number | null; wait_reason?: string; parallelism?: number | null
  stage?: string; steps?: Record<string, string>; group_id?: string
  volume?: { base: string; scheme: string; index: number; split: boolean } | null
  last_progress_at?: string | null; result_files?: number; deleted_psds?: number; deleted_txts?: number; deleted_pdfs?: number; recycled_psds?: number; recycled_txts?: number; attempts?: number
  group_members?: { id: number; filename: string; status: string; downloaded: number; size: number; average_speed: number }[]
  group_count?: number; group_size?: number; group_downloaded?: number; display_status?: string; archive_name?: string
  archive_group_warning?: string; manual_extract_only?: boolean; manual_source?: 'app' | 'external'
  manual_processed_at?: string; manual_previous_error?: string
}
export type TaskAction = 'pause' | 'resume' | 'retry' | 'extract_only' | 'mark_manual_extracted'
export interface Status {
  phase: string; connection: string; account: { name: string; username: string; id: number } | null
  error: string | null; pending: boolean; download_dir: string; data_dir: string
  extractor_available: boolean; counts: Record<string, number>; total_bytes: number; active: Task | null
  active_tasks: Task[]; queue_paused: boolean
  server_download_limits: { small?: number; large?: number }
}
export interface LibraryPicture {
  id: number; name: string; size: number; width: number | null; height: number | null
  version: string; monochrome: boolean | null; error: string
  sort_time: number; time_source: 'taken' | 'digitized' | 'image' | 'created' | 'modified' | null
}
export function imageThumbnail(item: LibraryPicture) {
  return `/api/images/${item.id}/thumbnail?version=${encodeURIComponent(item.version)}`
}
export const taskLabels: Record<string, string> = {
  queued: '等待下载', downloading: '下载中', downloaded: '下载完成', extracting: '解压中', completed: '已下载',
  extracted: '已解压', failed: '下载失败', extraction_failed: '待处理', interrupted: '等待恢复', waiting: '限流等待',
  organized: '已整理', organizing: '整理中', processing_failed: '整理失败', waiting_volumes: '等待分卷', paused: '已暂停', retrying: '恢复连接中',
  manual_extracted: '手动解压',
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
export function groupPercent(task: Task): number { return task.group_size ? Math.min(100, (task.group_downloaded || 0) / task.group_size * 100) : percent(task) }
export function waitRemaining(task: Task): number { return Math.max(0, (task.wait_until || 0) - Date.now() / 1000) }
