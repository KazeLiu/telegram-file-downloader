<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api, ApiError, bytes, date, duration, percent, groupPercent, waitRemaining, phaseLabels, taskLabels, type Settings, type Status, type Task, type TaskAction } from '../src/api'
import Icon from '../src/Icon.vue'
import TaskList from '../src/TaskList.vue'
import SettingsPanel from '../src/SettingsPanel.vue'
import WorkflowSteps from '../src/WorkflowSteps.vue'
import TaskActions from '../src/TaskActions.vue'
import FilesPanel from '../src/FilesPanel.vue'
import ImagesPanel from '../src/ImagesPanel.vue'
import XiaomiPanel from '../src/XiaomiPanel.vue'
import LogsPanel from '../src/LogsPanel.vue'

const appModel = reactive({ booting: true, page: 'overview', status: null as Status | null,
  settings: null as Settings | null, error: '', toast: '', busy: false, refreshing: false, workflowTask: null as number | null })
const authModel = reactive({ initialized: false, authenticated: false, password: '', confirm: '', busy: false, error: '' })
const historyModel = reactive({ items: [] as Task[], total: 0, page: 1, status: '', search: '', appliedSearch: '', selected: null as Task | null, busy: false })
const dialog = ref<HTMLDialogElement>()
const lastLocalRecycle = ref<string[]>([])
const archiveDialog = ref<HTMLDialogElement>()
const archiveConfirm = reactive({ action: 'extract_only' as 'extract_only' | 'mark_manual_extracted', taskId: 0,
  members: [] as { id: number; filename: string }[], busy: false, error: '' })
let timer: ReturnType<typeof setInterval>
let toastTimer: ReturnType<typeof setTimeout>
const navigation = [{ id: 'overview', title: '工作流', icon: 'workflow' }, { id: 'history', title: '下载记录', icon: 'history' }, { id: 'files', title: '文件管理', icon: 'folder' }, { id: 'images', title: '图片管理', icon: 'photo' }, { id: 'xiaomi', title: '小米云相册', icon: 'cloud' }, { id: 'logs', title: '运行日志', icon: 'file' }, { id: 'settings', title: '设置', icon: 'settings' }]
const title = computed(() => navigation.find(n => n.id === appModel.page)?.title)
const running = computed(() => appModel.status?.phase === 'watching' && appModel.status?.connection === 'Connected')
const completed = computed(() => (appModel.status?.counts.completed || 0) + (appModel.status?.counts.extracted || 0) + (appModel.status?.counts.organized || 0) + (appModel.status?.counts.manual_extracted || 0))
const phase = computed(() => appModel.status?.pending ? '正在应用设置' : appModel.status?.phase === 'watching' && !running.value ? '正在连接' : phaseLabels[appModel.status?.phase || 'unconfigured'])
const recent = computed(() => historyModel.items.slice(0, 5))
const workflowTask = computed(() => appModel.status?.active_tasks.find(t => t.id === appModel.workflowTask) || appModel.status?.active)

function message(value: string) {
  appModel.toast = value; clearTimeout(toastTimer)
  toastTimer = setTimeout(() => appModel.toast = '', 4000)
}
async function loadHistory() {
  const result = await api(`/history?page=${historyModel.page}&status=${encodeURIComponent(historyModel.status)}&search=${encodeURIComponent(historyModel.appliedSearch)}`)
  historyModel.items = result.items; historyModel.total = result.total
  if (historyModel.selected && dialog.value?.open) historyModel.selected = await api<Task>(`/history/${historyModel.selected.id}`)
}
async function refresh() {
  if (!authModel.authenticated || appModel.refreshing) return
  appModel.refreshing = true
  try {
    const [status, settings] = await Promise.all([api<Status>('/status'), api<Settings>('/settings')])
    appModel.status = status; appModel.settings = settings
    await loadHistory(); appModel.error = ''
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      authModel.authenticated = false; lastLocalRecycle.value = []
    }
    else appModel.error = (error as Error).message
  } finally { appModel.refreshing = false }
}
async function authenticate() {
  authModel.busy = true; authModel.error = ''
  try {
    if (!authModel.initialized && authModel.password !== authModel.confirm) throw new Error('两次输入的密码不一致')
    await api(authModel.initialized ? '/auth/login' : '/auth/setup', { password: authModel.password })
    authModel.password = authModel.confirm = ''; authModel.initialized = authModel.authenticated = true
    await refresh()
  } catch (error) { authModel.error = (error as Error).message }
  finally { authModel.busy = false }
}
async function toggleWatcher() {
  appModel.busy = true
  try { await api('/watcher', { enabled: !appModel.settings?.enabled }); message(appModel.settings?.enabled ? '收集已暂停，下载进度会保留' : '开始收集新消息'); await refresh() }
  catch (error) { appModel.error = (error as Error).message }
  finally { appModel.busy = false }
}
async function logout() {
  try { await api('/auth/logout', {}); authModel.authenticated = false; lastLocalRecycle.value = []; appModel.status = null; appModel.settings = null; historyModel.items = []; archiveDialog.value?.close(); dialog.value?.close() }
  catch (error) { appModel.error = (error as Error).message }
}
async function openTask(task: Task) {
  historyModel.selected = task
  await nextTick(); dialog.value?.showModal()
  try { historyModel.selected = await api<Task>(`/history/${task.id}`) }
  catch (error) { appModel.error = (error as Error).message }
}
async function taskAction(task: Task, action: TaskAction) {
  if (action === 'extract_only' || action === 'mark_manual_extracted') {
    try {
      const snapshot = task.group_members ? task : await api<Task>(`/history/${task.id}`)
      archiveConfirm.action = action; archiveConfirm.taskId = task.id; archiveConfirm.error = ''
      archiveConfirm.members = (snapshot.group_members?.length ? snapshot.group_members : [snapshot]).map(part => ({ id: part.id, filename: part.filename }))
      await nextTick(); archiveDialog.value?.showModal()
    } catch (error) { appModel.error = (error as Error).message }
    return
  }
  appModel.busy = true
  try { await api(`/history/${task.id}/action`, { action }); await refresh(); message(action === 'pause' ? '已暂停，下载分片已保留' : '任务已加入处理队列') }
  catch (error) { appModel.error = (error as Error).message }
  finally { appModel.busy = false }
}
async function confirmArchiveAction() {
  archiveConfirm.busy = true; archiveConfirm.error = ''
  try {
    await api(`/history/${archiveConfirm.taskId}/action`, { action: archiveConfirm.action, member_ids: archiveConfirm.members.map(part => part.id) })
    archiveDialog.value?.close()
    await refresh()
    message(archiveConfirm.action === 'mark_manual_extracted' ? '已标记为手动解压' : '已加入仅解压任务，原包会保留')
  } catch (error) { archiveConfirm.error = (error as Error).message }
  finally { archiveConfirm.busy = false }
}
async function toggleQueue() {
  appModel.busy = true
  try { await api('/queue', { paused: !appModel.status?.queue_paused }); await refresh(); message(appModel.status?.queue_paused ? '下载已暂停，新消息仍会进入队列' : '下载队列已继续') }
  catch (error) { appModel.error = (error as Error).message }
  finally { appModel.busy = false }
}
async function filterHistory() {
  historyModel.page = 1; historyModel.appliedSearch = historyModel.search
  try { await loadHistory() } catch (error) { appModel.error = (error as Error).message }
}
async function pageHistory(delta: number) {
  historyModel.page += delta
  try { await loadHistory() } catch (error) { appModel.error = (error as Error).message }
}
async function retryExtraction() {
  historyModel.busy = true
  try { await api(`/history/${historyModel.selected!.id}/extract`, {}); await loadHistory(); message('解压处理已更新') }
  catch (error) { appModel.error = (error as Error).message; dialog.value?.close() }
  finally { historyModel.busy = false }
}
function navigate(page: string) {
  appModel.page = page
  if (page === 'overview') { historyModel.page = 1; historyModel.status = ''; historyModel.search = historyModel.appliedSearch = ''; void refresh() }
}
onMounted(async () => {
  try { Object.assign(authModel, await api('/auth/status')); if (authModel.authenticated) await refresh() }
  catch (error) { authModel.error = (error as Error).message }
  finally { appModel.booting = false }
  timer = setInterval(() => { if (!document.hidden) void refresh() }, 2000)
})
onUnmounted(() => { clearInterval(timer); clearTimeout(toastTimer) })
</script>

<template>
  <div v-if="appModel.booting" class="grid min-h-dvh place-items-center text-muted" role="status">正在打开工作台…</div>
  <div v-else-if="!authModel.authenticated" class="auth-page">
    <div class="auth-brand"><span class="brand-symbol"><Icon name="inbox" :size="25" /></span><strong>拾存</strong></div>
    <main class="auth-main"><div class="auth-story" aria-hidden="true"><div class="archive-art"><div class="art-file back"><Icon name="video" :size="36" /></div><div class="art-file front"><Icon name="archive" :size="42" /></div><div class="art-tray"><Icon name="check" :size="24" /></div></div><p>Telegram<br />资源工作台</p></div>
      <section class="auth-form"><Icon name="lock" :size="24" class="text-blue" /><h1>{{ authModel.initialized ? '登录工作台' : '设置管理密码' }}</h1>
        <form @submit.prevent="authenticate"><label>管理密码<input v-model="authModel.password" type="password" :autocomplete="authModel.initialized ? 'current-password' : 'new-password'" :minlength="authModel.initialized ? 1 : 10" maxlength="256" required :placeholder="authModel.initialized ? '输入管理密码' : '至少 10 个字符'" /></label><label v-if="!authModel.initialized">确认密码<input v-model="authModel.confirm" type="password" autocomplete="new-password" minlength="10" maxlength="256" required placeholder="再输入一次" /></label><p v-if="authModel.error" class="form-error" role="alert">{{ authModel.error }}</p><button class="primary" :disabled="authModel.busy">{{ authModel.busy ? '请稍候…' : authModel.initialized ? '进入工作台' : '创建工作台' }}<Icon name="arrow" :size="18" /></button></form>
      </section>
    </main>
  </div>
  <div v-else class="app-shell">
    <aside class="sidebar"><a href="#" class="brand" aria-label="拾存工作流" @click.prevent="navigate('overview')"><span class="brand-symbol"><Icon name="inbox" :size="25" /></span><span><strong>拾存</strong></span></a>
      <nav class="main-nav" aria-label="主导航"><button v-for="item in navigation" :key="item.id" :class="{ selected: appModel.page === item.id }" :aria-label="item.title" :title="item.title" :aria-current="appModel.page === item.id ? 'page' : undefined" @click="navigate(item.id)"><Icon :name="item.icon" /><span>{{ item.title }}</span><span v-if="item.id === 'history' && completed" class="nav-count">{{ completed }}</span></button></nav>
      <div class="sidebar-bottom"><div v-if="appModel.status?.download_dir" class="storage-label" :title="appModel.status.download_dir"><Icon name="folder" :size="16" /><span class="truncate">{{ appModel.status.download_dir }}</span></div><button class="account-menu" aria-label="退出管理页面" @click="logout"><Icon name="logout" :size="18" /><span>退出工作台</span></button></div>
    </aside>
    <div class="min-w-0">
      <main class="page-content">
        <header class="page-heading"><h1>{{ title }}</h1><div v-if="appModel.page === 'overview'" class="flex flex-wrap items-center justify-end gap-2 sm:gap-4"><span class="connection"><span class="status-dot" :class="{ online: running }"></span>{{ phase }}</span><button v-if="appModel.status?.account && appModel.settings?.chat" :class="appModel.settings.enabled ? 'secondary' : 'primary'" :disabled="appModel.busy || appModel.status.pending" @click="toggleWatcher"><Icon :name="appModel.settings.enabled ? 'pause' : 'play'" :size="17" />{{ appModel.settings.enabled ? '暂停收集' : '开始收集' }}</button></div></header>
        <p v-if="appModel.error && appModel.page !== 'xiaomi'" class="notice error" role="alert">{{ appModel.error }}<button class="text-button" @click="refresh">重试</button></p>
        <p v-if="appModel.status?.error && !['history', 'xiaomi'].includes(appModel.page)" class="notice error" role="alert">{{ appModel.status.error }}</p>
        <XiaomiPanel v-if="appModel.page === 'xiaomi'" :last-local-recycle="lastLocalRecycle" @message="message" />
        <template v-else-if="appModel.settings && appModel.status">
          <template v-if="appModel.page === 'overview'">
            <WorkflowSteps :task="workflowTask" :settings="appModel.settings" />
            <section v-if="appModel.status.active_tasks.length || (appModel.status.account && appModel.settings.chat)" class="queue-panel"><div class="section-heading"><h2>下载队列<span v-if="appModel.status.queue_paused" class="badge ml-2">已暂停</span></h2><button class="secondary" :disabled="appModel.busy" @click="toggleQueue"><Icon :name="appModel.status.queue_paused ? 'play' : 'pause'" :size="16" />{{ appModel.status.queue_paused ? '继续下载' : '暂停下载' }}</button></div>
              <div v-for="task in appModel.status.active_tasks.slice(0, 10)" :key="task.id" class="queue-item" :class="{ focused: workflowTask?.id === task.id }"><div class="queue-file"><button class="queue-filename" @click="appModel.workflowTask = task.id"><Icon :name="task.kind === 'archive' ? 'archive' : 'file'" :size="20" /><strong>{{ task.filename }}</strong></button><span class="badge" :class="task.status">{{ taskLabels[task.status] }}</span></div><progress :value="percent(task)" max="100" :aria-label="task.filename + ' 下载进度'" /><div class="queue-meta"><span>{{ bytes(task.downloaded) }} / {{ bytes(task.size) }}</span><span>{{ bytes(task.speed) }}/s</span><span>{{ task.status === 'waiting' ? duration(waitRemaining(task)) + '后恢复' : task.status === 'downloading' ? '剩余 ' + duration(task.eta) : taskLabels[task.status] }}</span><button class="text-button" @click="openTask(task)">详情</button><TaskActions :task="task" :busy="appModel.busy" @action="taskAction(task, $event)" /></div><p v-if="task.error" class="queue-error">{{ task.error }}</p></div><div v-if="!appModel.status.active_tasks.length" class="empty-list"><Icon name="inbox" :size="28" /><p>等待下一次转发</p></div><button v-if="appModel.status.active_tasks.length > 10" class="text-button" @click="navigate('history')">查看全部任务</button>
            </section>
            <section v-if="!appModel.status.account || !appModel.settings.chat" class="welcome-panel"><span class="welcome-icon"><Icon name="inbox" :size="28" /></span><div class="grow"><h2>{{ !appModel.status.account ? '尚未连接 Telegram' : '尚未选择收集群' }}</h2><p v-if="!appModel.status.account" class="muted mt-1">首次连接只收集新消息。</p></div><button class="primary" @click="navigate('settings')">{{ !appModel.status.account ? '连接 Telegram' : '选择收集群' }}</button></section>
            <section class="summary-strip" aria-label="收集统计"><div><span>已收集文件</span><strong>{{ completed }}<small>个</small></strong></div><div><span>累计下载</span><strong>{{ bytes(appModel.status.total_bytes) }}</strong></div><div><span>收集入口</span><strong class="group-title">{{ appModel.settings.chat_title || '尚未选择' }}</strong></div></section>
            <section class="recent-section"><div class="section-heading"><h2>最近收集</h2><button class="text-button" @click="navigate('history')">全部记录<Icon name="chevron" :size="16" /></button></div><TaskList v-if="recent.length" :tasks="recent" compact @select="openTask" /><div v-else class="empty-list"><Icon name="history" :size="28" /><p>还没有下载记录</p></div></section>
          </template>
          <template v-else-if="appModel.page === 'history'">
            <form class="history-toolbar" @submit.prevent="filterHistory"><div class="search-box"><Icon name="search" :size="18" /><input v-model="historyModel.search" type="search" placeholder="搜索文件名" aria-label="搜索文件名" /><button class="text-button" type="submit">搜索</button></div><select v-model="historyModel.status" aria-label="按处理状态筛选" @change="filterHistory"><option value="">全部状态</option><option v-for="(label, status) in taskLabels" :key="status" :value="status">{{ label }}</option></select><span>{{ historyModel.total }} 条记录</span></form>
            <section class="history-panel"><TaskList v-if="historyModel.items.length" :tasks="historyModel.items" @select="openTask" /><div v-else class="empty-list tall"><Icon name="history" :size="38" /><h2>{{ historyModel.appliedSearch || historyModel.status ? '没有符合条件的记录' : '暂无下载记录' }}</h2><p v-if="historyModel.appliedSearch || historyModel.status">试试其他文件名或状态。</p><button v-if="!appModel.status.account" class="secondary mt-4" @click="navigate('settings')">连接 Telegram</button></div></section>
            <div v-if="historyModel.total > 25" class="pagination"><span>第 {{ historyModel.page }} / {{ Math.ceil(historyModel.total / 25) }} 页</span><button class="secondary" :disabled="historyModel.page === 1" @click="pageHistory(-1)">上一页</button><button class="secondary" :disabled="historyModel.page * 25 >= historyModel.total" @click="pageHistory(1)">下一页</button></div>
          </template>
          <FilesPanel v-else-if="appModel.page === 'files'" @message="message" />
          <ImagesPanel v-else-if="appModel.page === 'images'" :last-local-recycle="lastLocalRecycle" @recycled="lastLocalRecycle = $event" @message="message" />
          <LogsPanel v-else-if="appModel.page === 'logs'" />
          <SettingsPanel v-else :settings="appModel.settings" :status="appModel.status" @refresh="refresh" @message="message" />
        </template>
      </main>
    </div>
    <dialog ref="dialog" class="task-dialog" @click="(event: MouseEvent) => { if (event.target === dialog) dialog?.close() }">
      <template v-if="historyModel.selected">
        <div class="section-heading"><h2>文件详情</h2><button class="icon-button" aria-label="关闭详情" @click="dialog?.close()"><Icon name="close" /></button></div>
        <div class="detail-title"><span class="file-icon large"><Icon :name="historyModel.selected.kind === 'archive' ? 'archive' : 'file'" :size="30" /></span><div><h3>{{ historyModel.selected.archive_name || historyModel.selected.filename }}</h3><p v-if="(historyModel.selected.group_count || 0) > 1" class="muted">{{ historyModel.selected.group_count }} 个分卷 · {{ bytes(historyModel.selected.group_size) }}</p></div></div>
        <span class="badge" :class="historyModel.selected.display_status || historyModel.selected.status">{{ taskLabels[historyModel.selected.display_status || historyModel.selected.status] }}</span>
        <WorkflowSteps :task="historyModel.selected" :settings="appModel.settings || undefined" />
        <TaskActions :task="historyModel.selected" :busy="appModel.busy" archive-controls @action="taskAction(historyModel.selected!, $event)" />
        <p v-if="historyModel.selected.archive_group_warning" class="notice">{{ historyModel.selected.archive_group_warning }}</p>
        <p v-if="historyModel.selected.manual_source === 'external'" class="notice">已按你的确认标记为手动解压；未检查原包，不会再自动处理这一组记录。</p>
        <p v-else-if="historyModel.selected.manual_extract_only" class="notice">仅解压并保留原包，不自动平铺或清理。需要在图片管理中处理时，先到文件管理整理此文件夹。</p>
        <progress :value="groupPercent(historyModel.selected)" max="100" aria-label="整组下载进度" />
        <p v-if="(historyModel.selected.group_count || 0) > 1" class="detail-member-label">以下为当前分卷：{{ historyModel.selected.filename }}<br />暂停、继续与下载重试只影响此分卷；手动解压操作作用于整组。</p>
        <dl class="detail-grid">
          <div><dt>接收时间</dt><dd>{{ date(historyModel.selected.created_at) }}</dd></div>
          <div><dt>开始下载</dt><dd>{{ date(historyModel.selected.started_at) }}</dd></div>
          <div><dt>完成时间</dt><dd>{{ date(historyModel.selected.completed_at) }}</dd></div>
          <div v-if="historyModel.selected.manual_processed_at"><dt>手动解压时间</dt><dd>{{ date(historyModel.selected.manual_processed_at) }}</dd></div>
          <div><dt>下载耗时</dt><dd>{{ duration(historyModel.selected.elapsed) }}</dd></div>
          <div><dt>下载大小</dt><dd>{{ bytes(historyModel.selected.downloaded) }} / {{ bytes(historyModel.selected.size) }}</dd></div>
          <div><dt>下载进度</dt><dd>{{ percent(historyModel.selected).toFixed(1) }}%</dd></div>
          <div><dt>平均速度</dt><dd>{{ bytes(historyModel.selected.average_speed) }}/s</dd></div>
          <div><dt>最近进度更新</dt><dd>{{ date(historyModel.selected.last_progress_at || null) }}</dd></div>
          <div v-if="historyModel.selected.result_files"><dt>整理文件</dt><dd>{{ historyModel.selected.result_files }} 个</dd></div>
          <div v-if="historyModel.selected.recycled_psds"><dt>回收 PSD</dt><dd>{{ historyModel.selected.recycled_psds }} 个</dd></div>
          <div v-if="historyModel.selected.recycled_txts"><dt>回收 TXT</dt><dd>{{ historyModel.selected.recycled_txts }} 个</dd></div>
          <div v-if="(historyModel.selected.deleted_psds || 0) > (historyModel.selected.recycled_psds || 0)"><dt>旧版已删除 PSD</dt><dd>{{ (historyModel.selected.deleted_psds || 0) - (historyModel.selected.recycled_psds || 0) }} 个</dd></div>
          <div v-if="(historyModel.selected.deleted_txts || 0) > (historyModel.selected.recycled_txts || 0)"><dt>旧版已删除 TXT</dt><dd>{{ (historyModel.selected.deleted_txts || 0) - (historyModel.selected.recycled_txts || 0) }} 个</dd></div>
          <div v-if="historyModel.selected.deleted_pdfs"><dt>旧版已删除 PDF</dt><dd>{{ historyModel.selected.deleted_pdfs }} 个</dd></div>
          <div v-if="historyModel.selected.status === 'downloading'"><dt>预计剩余</dt><dd>{{ duration(historyModel.selected.eta) }}</dd></div>
          <div v-if="historyModel.selected.parallelism"><dt>分片并发上限</dt><dd>{{ historyModel.selected.parallelism }} 路</dd></div>
          <div v-if="historyModel.selected.status === 'waiting'"><dt>恢复下载</dt><dd>{{ duration(waitRemaining(historyModel.selected)) }}后</dd></div>
          <div v-if="historyModel.selected.status === 'waiting'"><dt>等待原因</dt><dd>{{ historyModel.selected.wait_reason === 'premium' ? '账号下载限速' : 'Telegram 请求限流' }}</dd></div>
          <div v-if="historyModel.selected.quality"><dt>下载版本</dt><dd>{{ historyModel.selected.quality }}</dd></div>
          <div v-if="historyModel.selected.kind === 'archive'"><dt>原压缩包</dt><dd>{{ historyModel.selected.manual_source === 'external' ? '由你自行处理，未检查是否存在' : historyModel.selected.archive_deleted ? '解压成功后已删除' : '程序未删除' }}</dd></div>
          <div class="full"><dt>下载位置</dt><dd>{{ historyModel.selected.path || '尚未完成' }}</dd></div>
          <div v-if="historyModel.selected.output" class="full"><dt>解压位置</dt><dd>{{ historyModel.selected.output }}</dd></div>
        </dl>
        <p v-if="historyModel.selected.error" class="notice error">{{ historyModel.selected.error }}</p>
        <p v-if="appModel.error" class="notice error" role="alert">{{ appModel.error }}</p>
        <p v-if="historyModel.selected.warning" class="notice">{{ historyModel.selected.warning }}</p>
        <details v-if="historyModel.selected.manual_previous_error" class="previous-error"><summary>处理前的错误记录</summary><p>{{ historyModel.selected.manual_previous_error }}</p></details>
        <div v-if="historyModel.selected.group_members && historyModel.selected.group_members.length > 1" class="volume-list"><h3>同组分卷</h3><article v-for="part in historyModel.selected.group_members" :key="part.id"><div><strong>{{ part.filename }}</strong><small>{{ bytes(part.downloaded) }} / {{ bytes(part.size) }} · 平均 {{ bytes(part.average_speed) }}/s</small></div><span class="badge" :class="part.status">{{ taskLabels[part.status] }}</span><button v-if="part.id !== historyModel.selected.id" class="text-button" @click="openTask({ ...historyModel.selected!, ...part })">详情</button></article></div>
        <button v-if="historyModel.selected.kind === 'archive' && historyModel.selected.path && ['completed','interrupted'].includes(historyModel.selected.status) && !historyModel.selected.archive_deleted && !historyModel.selected.manual_extract_only" class="primary" :disabled="historyModel.busy" @click="retryExtraction">{{ historyModel.busy ? '正在加入队列…' : '尝试解压并整理' }}</button>
      </template>
    </dialog>
    <dialog ref="archiveDialog" class="task-dialog archive-confirm-dialog" aria-labelledby="archive-confirm-title" @cancel="archiveConfirm.busy && $event.preventDefault()">
      <div class="section-heading"><h2 id="archive-confirm-title">{{ archiveConfirm.action === 'extract_only' ? '仅解压到文件夹' : '标记为手动解压' }}</h2><button class="icon-button" aria-label="取消" :disabled="archiveConfirm.busy" @click="archiveDialog?.close()"><Icon name="close" /></button></div>
      <p>{{ archiveConfirm.action === 'extract_only' ? '将以下压缩包作为一组解压到下载根目录中的资源文件夹。保留原包，不平铺、不清理 PSD/TXT，也不上传。' : '确认你已自行完成这一组资源的解压。只更新记录，即使原包已删除也能标记；不会操作磁盘文件。' }}</p>
      <div class="archive-confirm-list"><p v-for="part in archiveConfirm.members" :key="part.id"><Icon name="archive" :size="18" /><span>{{ part.filename }}</span></p></div>
      <p v-if="archiveConfirm.error" class="notice error" role="alert">{{ archiveConfirm.error }}</p>
      <div class="dialog-actions"><button class="secondary" :disabled="archiveConfirm.busy" @click="archiveDialog?.close()">取消</button><button class="primary" :disabled="archiveConfirm.busy" @click="confirmArchiveAction"><Icon v-if="archiveConfirm.busy" name="loader" class="loading-icon" :size="17" />{{ archiveConfirm.busy ? '正在提交…' : archiveConfirm.action === 'extract_only' ? `解压 ${archiveConfirm.members.length} 个文件` : `标记 ${archiveConfirm.members.length} 个文件` }}</button></div>
    </dialog>
  </div>
  <div v-if="appModel.toast" class="toast" role="status"><Icon name="check" :size="18" />{{ appModel.toast }}</div>
</template>
