<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, watch } from 'vue'
import { api, type Settings, type Status } from './api'
import Icon from './Icon.vue'

const props = defineProps<{ settings: Settings; status: Status }>()
const emit = defineEmits<{ refresh: []; message: [value: string] }>()
const settingsModel = reactive({ section: 'telegram', busy: '', error: '', dirty: false,
  form: {} as Record<string, any>, api_hash: '', proxy_password: '', archive_passwords: '', replace_passwords: false,
  dialogs: [] as { id: string; title: string }[], chat: '', phone: '', code: '', password: '',
  current_password: '', new_password: '', confirm_logout: false,
  clear_proxy_password: false,
})
const sections = [{ id: 'telegram', title: 'Telegram' }, { id: 'rules', title: '下载规则' }, { id: 'processing', title: '解压与回执' }, { id: 'security', title: '安全' }]
const configured = computed(() => !!props.settings.api_id && props.settings.api_hash_saved)

function resetForm() {
  const { api_hash_saved, proxy_password_saved, archive_passwords_count, chat, chat_title, enabled, ...form } = props.settings
  settingsModel.form = { ...form }; settingsModel.chat = chat
  settingsModel.api_hash = ''; settingsModel.proxy_password = ''; settingsModel.archive_passwords = ''
  settingsModel.replace_passwords = false; settingsModel.dirty = false
  settingsModel.clear_proxy_password = false
}
watch(() => props.settings, () => { if (!settingsModel.dirty) resetForm() }, { immediate: true })
async function action(key: string, run: () => Promise<unknown>, message = '') {
  settingsModel.busy = key; settingsModel.error = ''
  try { await run(); if (message) emit('message', message); emit('refresh') }
  catch (error) { settingsModel.error = (error as Error).message }
  finally { settingsModel.busy = '' }
}
async function save() {
  await action('save', async () => {
    const payload = { ...settingsModel.form, api_hash: settingsModel.api_hash || undefined,
      proxy_password: settingsModel.proxy_password || undefined,
      clear_proxy_password: settingsModel.clear_proxy_password,
      archive_passwords: settingsModel.replace_passwords ? settingsModel.archive_passwords.split('\n').filter(Boolean) : undefined }
    await api('/settings', payload, 'PUT')
    settingsModel.dirty = false
    settingsModel.api_hash = settingsModel.proxy_password = settingsModel.archive_passwords = ''
    settingsModel.replace_passwords = false
  }, props.status.active ? '已保存，当前任务结束后应用' : '设置已保存')
}
function loadDialogs() { return action('dialogs', async () => { settingsModel.dialogs = await api('/telegram/dialogs') }) }
const noBusy = computed(() => !settingsModel.busy && !props.status.pending)
function clearSecrets() { settingsModel.api_hash = settingsModel.proxy_password = settingsModel.password = settingsModel.code = settingsModel.archive_passwords = '' }
onBeforeUnmount(clearSecrets)
</script>
<template>
  <div class="settings-layout">
    <nav class="section-nav" aria-label="设置分类"><button v-for="section in sections" :key="section.id" :class="{ selected: settingsModel.section === section.id }" @click="settingsModel.section = section.id">{{ section.title }}</button></nav>
    <div class="settings-content">
      <p v-if="settingsModel.error" class="notice error" role="alert">{{ settingsModel.error }}</p>
      <form @submit.prevent="save" @input="settingsModel.dirty = true" @change="settingsModel.dirty = true">
        <template v-if="settingsModel.section === 'telegram'">
          <section class="settings-section"><div class="section-heading"><h2>连接 Telegram</h2><span class="badge" :class="status.account ? 'completed' : ''">{{ status.account ? '已登录' : '未登录' }}</span></div>
            <p class="muted">使用小号的 API 信息登录，大号只负责转发资源。</p>
            <div class="form-grid"><label>API ID<input v-model="settingsModel.form.api_id" inputmode="numeric" autocomplete="off" placeholder="数字 ID" :disabled="!!status.account" /></label><label>API Hash<input v-model="settingsModel.api_hash" type="password" autocomplete="new-password" :placeholder="settings.api_hash_saved ? '已保存，留空保持不变' : '填写 API Hash'" :disabled="!!status.account" /></label></div>
          </section>
          <section class="settings-section"><h2>网络代理</h2><p class="muted">容器访问宿主机代理用 host.docker.internal，Windows 直接运行用 127.0.0.1。</p>
            <div class="form-grid"><label>代理类型<select v-model="settingsModel.form.proxy_type"><option value="socks5">SOCKS5</option><option value="http">HTTP / Mixed</option><option value="direct">直连（不使用代理）</option></select></label><span></span></div>
            <template v-if="settingsModel.form.proxy_type !== 'direct'"><div class="form-grid host-port"><label>代理地址<input v-model="settingsModel.form.proxy_host" placeholder="host.docker.internal" autocomplete="off" /></label><label>端口<input v-model="settingsModel.form.proxy_port" inputmode="numeric" placeholder="7890" /></label></div><div class="form-grid"><label>用户名（可选）<input v-model="settingsModel.form.proxy_username" autocomplete="off" /></label><label>密码（可选）<input v-model="settingsModel.proxy_password" type="password" autocomplete="new-password" :placeholder="settings.proxy_password_saved ? '已保存，留空保持不变' : '无认证时留空'" :disabled="settingsModel.clear_proxy_password" /></label></div><label v-if="settings.proxy_password_saved" class="clear-password"><input v-model="settingsModel.clear_proxy_password" type="checkbox" />清除已保存的代理密码</label></template>
          </section>
        </template>
        <template v-if="settingsModel.section === 'rules'">
          <section class="settings-section"><h2>收集哪些文件</h2><p class="muted">修改后只影响之后处理的消息，不会重新扫描已跳过的内容。</p>
            <label class="toggle-row"><span class="setting-icon"><Icon name="video" /></span><span><strong>视频</strong><small>选择 Telegram 提供的最高可用清晰度，不转码</small></span><input v-model="settingsModel.form.videos" type="checkbox" role="switch" /></label>
            <label class="toggle-row"><span class="setting-icon"><Icon name="photo" /></span><span><strong>图片</strong><small>保存最高可用尺寸；文档方式发送的图片保留原文件</small></span><input v-model="settingsModel.form.photos" type="checkbox" role="switch" /></label>
            <label class="toggle-row"><span class="setting-icon"><Icon name="archive" /></span><span><strong>ZIP / RAR 压缩包</strong><small>保留原文件名，同名文件自动编号</small></span><input v-model="settingsModel.form.archives" type="checkbox" role="switch" /></label>
          </section>
          <section class="settings-section"><h2>文件保存位置</h2><div class="path-box"><Icon name="folder" /><code>{{ status.download_dir }}</code></div><p class="muted">这是程序内部的下载目录。Docker 的实际存放位置由 Compose 下载挂载决定。</p></section>
        </template>
        <template v-if="settingsModel.section === 'processing'">
          <section class="settings-section"><h2>解压与清理</h2><label class="toggle-row"><span><strong>自动解压 ZIP / RAR</strong><small>先尝试无密码，再依次尝试已保存的密码</small></span><input v-model="settingsModel.form.extract" type="checkbox" role="switch" /></label>
            <label class="toggle-row"><span><strong>解压成功后删除原包</strong><small>只有完整解压成功才删除；失败和分卷压缩包保留</small></span><input v-model="settingsModel.form.delete_archive" type="checkbox" role="switch" :disabled="!settingsModel.form.extract" /></label>
            <p v-if="!status.extractor_available" class="notice">未找到 7-Zip，当前只下载、不解压。Windows 安装 7-Zip 后重新连接即可。</p>
            <div class="password-heading"><span>解压密码 <small class="muted">已保存 {{ settings.archive_passwords_count }} 个</small></span><button type="button" class="text-button" @click="settingsModel.replace_passwords = !settingsModel.replace_passwords">{{ settingsModel.replace_passwords ? '取消替换' : '替换密码列表' }}</button></div>
            <label v-if="settingsModel.replace_passwords">每行一个密码，留空保存会清除列表<textarea v-model="settingsModel.archive_passwords" rows="4" autocomplete="off" spellcheck="false" class="secret-text" placeholder="输入固定的几个密码" /></label>
            <p class="muted">密码只保存在服务器，不会在页面回显。分卷文件请收齐后手动解压。</p>
          </section>
          <section class="settings-section"><h2>群内反馈</h2><label class="toggle-row"><span><strong>下载与解压回执</strong><small>回复原消息，约每 10 秒更新进度、速度和剩余时间</small></span><input v-model="settingsModel.form.receipts" type="checkbox" role="switch" /></label><label class="toggle-row"><span><strong>接收任务后标记已读</strong><small>已读代表收到任务；完成状态以回执为准</small></span><input v-model="settingsModel.form.mark_read" type="checkbox" role="switch" /></label></section>
        </template>
        <div v-if="settingsModel.section !== 'security'" class="save-bar"><span>{{ settingsModel.dirty ? '有未保存的更改' : status.pending ? '等待当前任务结束后应用' : '设置保存在服务器，重启后保留' }}</span><button class="primary" :disabled="!!settingsModel.busy" type="submit">{{ settingsModel.busy === 'save' ? '保存中…' : '保存设置' }}</button></div>
      </form>
      <section v-if="settingsModel.section === 'telegram'" class="settings-section login-section">
        <h2>{{ status.account ? '收集账号与群' : '登录小号' }}</h2>
        <template v-if="status.account"><div class="account-line"><div class="avatar">{{ status.account.name.slice(0, 1) }}</div><div><strong>{{ status.account.name }}</strong><small>{{ status.account.username ? '@' + status.account.username : 'Telegram 已登录' }}</small></div><button class="text-button danger-text" :disabled="!noBusy || !!status.active" @click="settingsModel.confirm_logout = true">退出 Telegram</button></div>
          <div v-if="settingsModel.confirm_logout" class="notice"><p>退出后停止收集。文件和历史保留，可以重新登录。</p><button class="secondary" @click="settingsModel.confirm_logout = false">取消</button> <button class="danger" :disabled="!noBusy" @click="action('logout', async () => { await api('/telegram/logout', {}); settingsModel.confirm_logout = false })">确认退出</button></div>
          <div class="group-picker"><label>收集群<select v-model="settingsModel.chat" :disabled="!settingsModel.dialogs.length"><option :value="settings.chat">{{ settings.chat_title || '先加载群列表' }}</option><option v-for="dialog in settingsModel.dialogs.filter(d => d.id !== settings.chat)" :key="dialog.id" :value="dialog.id">{{ dialog.title }}</option></select></label><button class="secondary" :disabled="!noBusy" @click="loadDialogs">{{ settingsModel.busy === 'dialogs' ? '加载中…' : '加载群列表' }}</button><button v-if="settingsModel.chat && settingsModel.chat !== settings.chat" class="primary" :disabled="!noBusy" @click="action('chat', () => api('/telegram/chat', { id: settingsModel.chat }), '收集群已保存')">选用此群</button></div>
        </template>
        <template v-else-if="configured && !status.pending && status.phase !== 'connection_error'">
          <form v-if="!['code', 'password'].includes(status.phase)" class="inline-form" @submit.prevent="action('code', () => api('/telegram/code', { phone: settingsModel.phone }), '验证码已发送，请在 Telegram 客户端查看')"><label>手机号（含国家区号）<input v-model="settingsModel.phone" type="tel" autocomplete="tel" placeholder="+86 …" required /></label><button class="primary" :disabled="!noBusy">发送验证码</button></form>
          <form v-else-if="status.phase === 'code'" class="inline-form" @submit.prevent="action('login', async () => { await api('/telegram/login', { code: settingsModel.code }); settingsModel.code = '' })"><label>登录验证码<input v-model="settingsModel.code" inputmode="numeric" autocomplete="one-time-code" placeholder="在 Telegram 客户端查看" required /></label><button class="primary" :disabled="!noBusy">验证并继续</button><button type="button" class="text-button" :disabled="!noBusy" @click="action('reset', () => api('/telegram/reconnect', {}))">重新输入手机号</button></form>
          <form v-else class="inline-form" @submit.prevent="action('login', async () => { await api('/telegram/login', { password: settingsModel.password }); settingsModel.password = '' })"><label>Telegram 两步验证密码<input v-model="settingsModel.password" type="password" autocomplete="current-password" required /></label><button class="primary" :disabled="!noBusy">完成登录</button></form>
        </template>
        <p v-else class="muted">{{ status.pending ? '正在应用连接设置…' : '先保存上方 API 和代理设置，再完成登录。' }}</p>
        <button v-if="configured" class="text-button reconnect" :disabled="!noBusy" @click="action('reconnect', () => api('/telegram/reconnect', {}))"><Icon name="refresh" :size="16" />重新连接</button>
      </section>
      <section v-if="settingsModel.section === 'security'" class="settings-section"><h2>管理页面密码</h2><p class="muted">只用于登录这个工作台，与 Telegram 密码无关。</p><form class="security-form" @submit.prevent="action('password', async () => { await api('/auth/password', { current_password: settingsModel.current_password, password: settingsModel.new_password }); settingsModel.current_password = settingsModel.new_password = '' }, '管理密码已更新')"><label>原管理密码<input v-model="settingsModel.current_password" type="password" autocomplete="current-password" required /></label><label>新管理密码<input v-model="settingsModel.new_password" type="password" minlength="10" maxlength="256" autocomplete="new-password" required placeholder="至少 10 个字符" /></label><button class="primary" :disabled="!!settingsModel.busy">更新密码</button></form><div class="security-note"><Icon name="lock" /><p>请仅通过本机、局域网或 Tailscale 访问。数据目录包含 Telegram 登录会话，备份时请妥善保管。</p></div></section>
    </div>
  </div>
</template>
