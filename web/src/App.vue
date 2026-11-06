<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api, ApiError, bytes, date, duration, percent, waitRemaining, phaseLabels, taskLabels, type Settings, type Status, type Task } from './api'
import Icon from './Icon.vue'
import TaskList from './TaskList.vue'
import SettingsPanel from './SettingsPanel.vue'
import WorkflowSteps from './WorkflowSteps.vue'
import TaskActions from './TaskActions.vue'
import FilesPanel from './FilesPanel.vue'
import LogsPanel from './LogsPanel.vue'

const appModel = reactive({ booting: true, page: 'overview', status: null as Status | null,
  settings: null as Settings | null, error: '', toast: '', busy: false, refreshing: false, workflowTask: null as number | null })
const authModel = reactive({ initialized: false, authenticated: false, password: '', confirm: '', busy: false, error: '' })
const historyModel = reactive({ items: [] as Task[], total: 0, page: 1, status: '', search: '', appliedSearch: '', selected: null as Task | null, busy: false })
const dialog = ref<HTMLDialogElement>()
let timer: ReturnType<typeof setInterval>
let toastTimer: ReturnType<typeof setTimeout>
const navigation = [{ id: 'overview', title: '工作流', icon: 'workflow' }, { id: 'history', title: '下载记录', icon: 'history' }, { id: 'files', title: '文件管理', icon: 'folder' }, { id: 'logs', title: '运行日志', icon: 'file' }, { id: 'settings', title: '设置', icon: 'settings' }]
const title = computed(() => navigation.find(n => n.id === appModel.page)?.title)
const running = computed(() => appModel.status?.phase === 'watching' && appModel.status?.connection === 'Connected')
const completed = computed(() => (appModel.status?.counts.completed || 0) + (appModel.status?.counts.extracted || 0) + (appModel.status?.counts.organized || 0))
const phase = computed(() => appModel.status?.pending ? '正在应用设置' : appModel.status?.phase === 'watching' && !running.value ? '正在连接' : phaseLabels[appModel.status?.phase || 'unconfigured'])
const recent = computed(() => historyModel.items.slice(0, 5))
const workflowTask = computed(() => appModel.status?.active_tasks.find(t => t.id === appModel.workflowTask) || appModel.status?.active)
const pageDescriptions: Record<string, string> = { overview: '从接收、下载到整理，每一步都看得见。', history: '每一次下载，都有迹可循。', files: '把文件夹整理成一个平铺的资源库。', logs: '查看任务进展、连接恢复与失败原因。', settings: '按你的习惯，安排每一份资源。' }

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
    if (error instanceof ApiError && error.status === 401) authModel.authenticated = false
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
  try { await api('/auth/logout', {}); authModel.authenticated = false; appModel.status = null; appModel.settings = null; historyModel.items = []; dialog.value?.close() }
  catch (error) { appModel.error = (error as Error).message }
}
async function openTask(task: Task) {
  historyModel.selected = task
  await nextTick(); dialog.value?.showModal()
  try { historyModel.selected = await api<Task>(`/history/${task.id}`) }
  catch (error) { appModel.error = (error as Error).message }
}
async function taskAction(task: Task, action: 'pause' | 'resume' | 'retry') {
  appModel.busy = true
  try { await api(`/history/${task.id}/action`, { action }); await refresh(); message(action === 'pause' ? '已暂停，下载分片已保留' : '任务已加入处理队列') }
  catch (error) { appModel.error = (error as Error).message }
  finally { appModel.busy = false }
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
  <div v-if="appModel.booting" class="boot-screen" role="status">正在打开工作台…</div>
  <div v-else-if="!authModel.authenticated" class="auth-page">
    <div class="auth-brand"><span class="brand-symbol"><Icon name="inbox" :size="25" /></span><strong>拾存</strong><span>Telegram 资源工作台</span></div>
    <main class="auth-main"><div class="auth-story"><div class="archive-art" aria-hidden="true"><div class="art-file back"><Icon name="video" :size="36" /></div><div class="art-file front"><Icon name="archive" :size="42" /></div><div class="art-tray"><Icon name="check" :size="24" /></div></div><h1>值得留下的，<br />都在这里。</h1><p>从群里的一次转发，<br />到你的专属资源库。</p><div class="auth-caption"><Icon name="folder" :size="17" />本地保存 · 自主管理</div></div>
      <section class="auth-form"><span class="lock-symbol"><Icon name="lock" :size="24" /></span><h2>{{ authModel.initialized ? '欢迎回来。' : '设置你的工作台。' }}</h2><p class="muted">{{ authModel.initialized ? '输入管理密码，查看收集状态。' : '先设置管理密码，再连接 Telegram 小号。' }}</p>
        <form @submit.prevent="authenticate"><label>管理密码<input v-model="authModel.password" type="password" :autocomplete="authModel.initialized ? 'current-password' : 'new-password'" :minlength="authModel.initialized ? 1 : 10" maxlength="256" required :placeholder="authModel.initialized ? '输入管理密码' : '至少 10 个字符'" /></label><label v-if="!authModel.initialized">确认密码<input v-model="authModel.confirm" type="password" autocomplete="new-password" minlength="10" maxlength="256" required placeholder="再输入一次" /></label><p v-if="authModel.error" class="form-error" role="alert">{{ authModel.error }}</p><button class="primary" :disabled="authModel.busy">{{ authModel.busy ? '请稍候…' : authModel.initialized ? '进入工作台' : '创建工作台' }}<Icon name="arrow" :size="18" /></button></form>
        <p class="auth-help">管理密码只保护这个页面，<br />不会替代你的 Telegram 登录。</p>
      </section>
    </main><footer>你的收藏，留在你自己的设备。</footer>
  </div>
  <div v-else class="app-shell">
    <aside class="sidebar"><a href="#" class="brand" @click.prevent="navigate('overview')"><span class="brand-symbol"><Icon name="inbox" :size="25" /></span><span><strong>拾存</strong><small>Telegram 资源工作台</small></span></a>
      <nav class="main-nav" aria-label="主导航"><button v-for="item in navigation" :key="item.id" :class="{ selected: appModel.page === item.id }" :aria-current="appModel.page === item.id ? 'page' : undefined" @click="navigate(item.id)"><Icon :name="item.icon" /><span>{{ item.title }}</span><span v-if="item.id === 'history' && completed" class="nav-count">{{ completed }}</span></button></nav>
      <div class="sidebar-bottom"><div class="storage-label"><Icon name="folder" :size="18" /><span>文件保存在你的设备<small>{{ appModel.status?.download_dir || '正在读取…' }}</small></span></div><button class="account-menu" aria-label="退出管理页面" @click="logout"><Icon name="lock" :size="18" /><span>退出管理页面</span><Icon name="logout" :size="17" /></button></div>
    </aside>
    <div class="workspace"><header class="topbar"><span>我的资源库<span class="slash">/</span>{{ title }}</span><div class="connection"><span class="status-dot" :class="{ online: running }"></span>{{ phase }}</div></header>
      <main class="page-content"><div class="page-heading"><div><h1>{{ title }}</h1><p>{{ pageDescriptions[appModel.page] }}</p></div><button v-if="appModel.page === 'overview' && appModel.status?.account && appModel.settings?.chat" :class="appModel.settings.enabled ? 'secondary' : 'primary'" :disabled="appModel.busy || appModel.status.pending" @click="toggleWatcher"><Icon :name="appModel.settings.enabled ? 'pause' : 'play'" :size="17" />{{ appModel.settings.enabled ? '暂停收集' : '开始收集' }}</button></div>
        <p v-if="appModel.error" class="notice error" role="alert">{{ appModel.error }}<button class="text-button" @click="refresh">重试</button></p>
        <p v-if="appModel.status?.error && appModel.page !== 'history'" class="notice error" role="alert">{{ appModel.status.error }}</p>
        <template v-if="appModel.settings && appModel.status">
          <template v-if="appModel.page === 'overview'">
            <WorkflowSteps :task="workflowTask" :settings="appModel.settings" />
            <section v-if="appModel.status.active_tasks.length || appModel.status.account" class="queue-panel"><div class="section-heading"><div><h2>下载队列 <small class="muted">最多 {{ appModel.settings.parallel_files }} 个文件同时下载</small></h2><p class="muted">{{ appModel.status.queue_paused ? '下载已暂停，新转发仍会进入队列。' : `每个文件最多 ${appModel.settings.download_parallelism} 路，文件数遵守 Telegram 上限；限流统一等待。` }}</p><p v-if="appModel.status.server_download_limits.small || appModel.status.server_download_limits.large" class="muted">同一数据中心上限：小文件 {{ appModel.status.server_download_limits.small || '未下发' }} 个，大文件 {{ appModel.status.server_download_limits.large || '未下发' }} 个。</p></div><button class="secondary" :disabled="appModel.busy" @click="toggleQueue"><Icon :name="appModel.status.queue_paused ? 'play' : 'pause'" :size="16" />{{ appModel.status.queue_paused ? '继续下载' : '暂停下载' }}</button></div>
              <div v-for="task in appModel.status.active_tasks.slice(0, 10)" :key="task.id" class="queue-item" :class="{ focused: workflowTask?.id === task.id }"><div class="queue-file"><button class="queue-filename" @click="appModel.workflowTask = task.id"><Icon :name="task.kind === 'archive' ? 'archive' : 'file'" :size="20" /><strong>{{ task.filename }}</strong></button><span class="badge" :class="task.status">{{ taskLabels[task.status] }}</span></div><progress :value="percent(task)" max="100" :aria-label="task.filename + ' 下载进度'" /><div class="queue-meta"><span>{{ bytes(task.downloaded) }} / {{ bytes(task.size) }}</span><span>{{ bytes(task.speed) }}/s</span><span>{{ task.status === 'waiting' ? duration(waitRemaining(task)) + '后恢复' : task.status === 'downloading' ? '剩余 ' + duration(task.eta) : taskLabels[task.status] }}</span><button class="text-button" @click="openTask(task)">详情</button><TaskActions :task="task" :busy="appModel.busy" @action="taskAction(task, $event)" /></div><p v-if="task.error" class="queue-error">{{ task.error }}</p></div><div v-if="!appModel.status.active_tasks.length" class="empty-list"><Icon name="inbox" :size="28" /><p>等待下一次转发</p></div><button v-if="appModel.status.active_tasks.length > 10" class="text-button" @click="navigate('history')">查看全部任务</button>
            </section>
            <section v-if="!appModel.status.account || !appModel.settings.chat" class="welcome-panel"><div class="welcome-icon"><Icon name="inbox" :size="54" /></div><h2>{{ !appModel.status.account ? '连接 Telegram，开始收集。' : '选一个群，作为收集入口。' }}</h2><p>用小号守候在群里，自动保存你转发的文件。</p><button class="primary" @click="navigate('settings')">{{ !appModel.status.account ? '连接 Telegram' : '选择收集群' }}<Icon name="arrow" :size="18" /></button><div class="welcome-foot"><span><Icon name="check" :size="15" />首次跳过旧消息</span><span><Icon name="check" :size="15" />登录状态持久保存</span></div></section>
            <section v-else-if="!appModel.status.active_tasks.length" class="idle-panel"><div class="idle-symbol"><Icon :name="appModel.settings.enabled ? 'inbox' : 'pause'" :size="36" /></div><div><h2>{{ appModel.settings.enabled ? '一切就绪，等你下一次转发。' : '收集已暂停。' }}</h2><p>{{ appModel.settings.chat_title }}<span class="inline-dot">·</span>{{ appModel.settings.enabled ? '新附件会自动下载到你的设备' : '已保存的文件和登录状态不会受到影响' }}</p></div><span class="badge" :class="running ? 'completed' : ''">{{ phase }}</span></section>
            <section class="summary-strip" aria-label="收集统计"><div><span>已收集文件</span><strong>{{ completed }}<small>个</small></strong></div><div><span>累计下载</span><strong>{{ bytes(appModel.status.total_bytes) }}</strong></div><div><span>收集入口</span><strong class="group-title">{{ appModel.settings.chat_title || '尚未选择' }}</strong></div></section>
            <section class="recent-section"><div class="section-heading"><h2>最近收集</h2><button class="text-button" @click="navigate('history')">全部记录<Icon name="chevron" :size="16" /></button></div><TaskList v-if="recent.length" :tasks="recent" compact @select="openTask" /><div v-else class="empty-list"><Icon name="history" :size="28" /><p>还没有下载记录</p><span>开始收集后，下载进度和处理结果会显示在这里。</span></div></section>
            <section class="rules-summary"><span>当前规则</span><span class="rule-chip" :class="{ enabled: appModel.settings.videos }"><Icon name="video" :size="16" />视频 · {{ appModel.settings.videos ? '最高可用清晰度' : '不下载' }}</span><span class="rule-chip" :class="{ enabled: appModel.settings.photos }"><Icon name="photo" :size="16" />图片 · {{ appModel.settings.photos ? '下载' : '不下载' }}</span><span class="rule-chip" :class="{ enabled: appModel.settings.archives }"><Icon name="archive" :size="16" />压缩包 · {{ appModel.settings.archives ? '下载' : '不下载' }}</span><button class="text-button" @click="navigate('settings')">调整</button></section>
          </template>
          <template v-else-if="appModel.page === 'history'">
            <form class="history-toolbar" @submit.prevent="filterHistory"><div class="search-box"><Icon name="search" :size="18" /><input v-model="historyModel.search" type="search" placeholder="搜索文件名" aria-label="搜索文件名" /><button class="text-button" type="submit">搜索</button></div><select v-model="historyModel.status" aria-label="按处理状态筛选" @change="filterHistory"><option value="">全部状态</option><option v-for="(label, status) in taskLabels" :key="status" :value="status">{{ label }}</option></select><span>{{ historyModel.total }} 条记录</span></form>
            <section class="history-panel"><TaskList v-if="historyModel.items.length" :tasks="historyModel.items" @select="openTask" /><div v-else class="empty-list tall"><Icon name="history" :size="38" /><h2>{{ historyModel.appliedSearch || historyModel.status ? '没有符合条件的记录' : '你的资源旅程，从一次转发开始。' }}</h2><p>{{ historyModel.appliedSearch || historyModel.status ? '试试其他文件名或状态。' : '下载时间、速度、进度和解压结果，都会记录在这里。' }}</p><button v-if="!appModel.status.account" class="secondary" @click="navigate('settings')">先连接 Telegram</button></div></section>
            <div v-if="historyModel.total > 25" class="pagination"><span>第 {{ historyModel.page }} / {{ Math.ceil(historyModel.total / 25) }} 页</span><button class="secondary" :disabled="historyModel.page === 1" @click="pageHistory(-1)">上一页</button><button class="secondary" :disabled="historyModel.page * 25 >= historyModel.total" @click="pageHistory(1)">下一页</button></div>
          </template>
          <FilesPanel v-else-if="appModel.page === 'files'" @message="message" />
          <LogsPanel v-else-if="appModel.page === 'logs'" />
          <SettingsPanel v-else :settings="appModel.settings" :status="appModel.status" @refresh="refresh" @message="message" />
        </template>
        <footer class="page-footer"><span>拾存 · 本地优先的 Telegram 收集工具</span><span><Icon name="lock" :size="13" />设置与会话持久保存</span></footer>
      </main>
    </div>
    <dialog ref="dialog" class="task-dialog" @click="(event: MouseEvent) => { if (event.target === dialog) dialog?.close() }">
      <template v-if="historyModel.selected">
        <div class="section-heading"><h2>文件详情</h2><button class="icon-button" aria-label="关闭详情" @click="dialog?.close()"><Icon name="close" /></button></div>
        <div class="detail-title"><span class="file-icon large"><Icon name="file" :size="30" /></span><h3>{{ historyModel.selected.filename }}</h3></div>
        <span class="badge" :class="historyModel.selected.status">{{ taskLabels[historyModel.selected.status] }}</span>
        <WorkflowSteps :task="historyModel.selected" :settings="appModel.settings || undefined" />
        <TaskActions :task="historyModel.selected" :busy="appModel.busy" @action="taskAction(historyModel.selected!, $event)" />
        <progress :value="percent(historyModel.selected)" max="100" aria-label="文件下载进度" />
        <dl class="detail-grid">
          <div><dt>接收时间</dt><dd>{{ date(historyModel.selected.created_at) }}</dd></div>
          <div><dt>开始下载</dt><dd>{{ date(historyModel.selected.started_at) }}</dd></div>
          <div><dt>完成时间</dt><dd>{{ date(historyModel.selected.completed_at) }}</dd></div>
          <div><dt>下载耗时</dt><dd>{{ duration(historyModel.selected.elapsed) }}</dd></div>
          <div><dt>下载大小</dt><dd>{{ bytes(historyModel.selected.downloaded) }} / {{ bytes(historyModel.selected.size) }}</dd></div>
          <div><dt>下载进度</dt><dd>{{ percent(historyModel.selected).toFixed(1) }}%</dd></div>
          <div><dt>平均速度</dt><dd>{{ bytes(historyModel.selected.average_speed) }}/s</dd></div>
          <div><dt>最近进度更新</dt><dd>{{ date(historyModel.selected.last_progress_at || null) }}</dd></div>
          <div v-if="historyModel.selected.result_files"><dt>整理文件</dt><dd>{{ historyModel.selected.result_files }} 个</dd></div>
          <div v-if="historyModel.selected.deleted_psds"><dt>删除 PSD</dt><dd>{{ historyModel.selected.deleted_psds }} 个</dd></div>
          <div v-if="historyModel.selected.deleted_pdfs"><dt>旧版已删除 PDF</dt><dd>{{ historyModel.selected.deleted_pdfs }} 个</dd></div>
          <div v-if="historyModel.selected.status === 'downloading'"><dt>预计剩余</dt><dd>{{ duration(historyModel.selected.eta) }}</dd></div>
          <div v-if="historyModel.selected.parallelism"><dt>分片并发上限</dt><dd>{{ historyModel.selected.parallelism }} 路</dd></div>
          <div v-if="historyModel.selected.status === 'waiting'"><dt>恢复下载</dt><dd>{{ duration(waitRemaining(historyModel.selected)) }}后</dd></div>
          <div v-if="historyModel.selected.status === 'waiting'"><dt>等待原因</dt><dd>{{ historyModel.selected.wait_reason === 'premium' ? '账号下载限速' : 'Telegram 请求限流' }}</dd></div>
          <div v-if="historyModel.selected.quality"><dt>下载版本</dt><dd>{{ historyModel.selected.quality }}</dd></div>
          <div v-if="historyModel.selected.kind === 'archive'"><dt>原压缩包</dt><dd>{{ historyModel.selected.archive_deleted ? '解压成功后已删除' : '保留' }}</dd></div>
          <div class="full"><dt>下载位置</dt><dd>{{ historyModel.selected.path || '尚未完成' }}</dd></div>
          <div v-if="historyModel.selected.output" class="full"><dt>解压位置</dt><dd>{{ historyModel.selected.output }}</dd></div>
        </dl>
        <p v-if="historyModel.selected.error" class="notice error">{{ historyModel.selected.error }}</p>
        <p v-if="appModel.error" class="notice error" role="alert">{{ appModel.error }}</p>
        <p v-if="historyModel.selected.warning" class="notice">{{ historyModel.selected.warning }}</p>
        <div v-if="historyModel.selected.group_members && historyModel.selected.group_members.length > 1" class="volume-list"><h3>同组分卷</h3><p v-for="part in historyModel.selected.group_members" :key="part.id"><span>{{ part.filename }}</span><span class="badge" :class="part.status">{{ taskLabels[part.status] }}</span></p></div>
        <button v-if="historyModel.selected.kind === 'archive' && historyModel.selected.path && ['completed','interrupted'].includes(historyModel.selected.status) && !historyModel.selected.archive_deleted" class="primary" :disabled="historyModel.busy" @click="retryExtraction">{{ historyModel.busy ? '正在加入队列…' : '尝试解压并整理' }}</button>
      </template>
    </dialog>
  </div>
  <div v-if="appModel.toast" class="toast" role="status"><Icon name="check" :size="18" />{{ appModel.toast }}</div>
</template>
