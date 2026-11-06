<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api, bytes } from './api'
import Icon from './Icon.vue'

type Account = { connection: string; label: string }
type Album = { id: string; name: string }
type Media = { id: string; name: string; kind: 'image' | 'video'; size: number | null; taken_at: number | null }

const emit = defineEmits<{ message: [text: string] }>()
const cloud = reactive({ account: null as Account | null, albums: [] as Album[], album: '', items: [] as Media[],
  page: 0, last: true, ready: false, busy: '', error: '', initialized: false, qr: '', verifying: false })
const upload = reactive({ file: null as File | null, name: '', error: '' })
const selected = ref<Media>()
const recycleDialog = ref<HTMLDialogElement>()
const uploadDialog = ref<HTMLDialogElement>()
const fileInput = ref<HTMLInputElement>()
const albumName = computed(() => cloud.albums.find(item => item.id === cloud.album)?.name || '')
let pollTimer: ReturnType<typeof setTimeout>
let disposed = false

function params(values: Record<string, string>) {
  return new URLSearchParams({ connection: cloud.account!.connection, ...values })
}

function takenAt(value: number | null) {
  return value ? new Date(value).toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }) : '时间未知'
}

async function run(label: string, action: () => Promise<void>) {
  cloud.busy = label; cloud.error = ''
  try { await action() }
  catch (error) { cloud.error = (error as Error).message }
  finally { cloud.busy = '' }
}

async function loadMedia(page = 0) {
  const result = await api<{ items: Media[]; last: boolean }>(`/xiaomi/media?${params({ album: cloud.album, page: String(page) })}`)
  cloud.items = result.items; cloud.last = result.last; cloud.page = page; cloud.ready = true
}

async function loadAccount() {
  const previous = cloud.account?.connection
  const result = await api<{ account: Account | null }>('/xiaomi/account')
  cloud.account = result.account; cloud.initialized = true; cloud.ready = false; cloud.items = []
  cloud.albums = []
  if (!cloud.account || cloud.account.connection !== previous) cloud.album = ''
  if (!cloud.account) return
  cloud.albums = (await api<{ items: Album[] }>(`/xiaomi/albums?${params({})}`)).items
  if (!cloud.albums.some(item => item.id === cloud.album)) cloud.album = cloud.albums[0]?.id || ''
  if (cloud.album) await loadMedia()
}

async function pollQr(id: string) {
  if (disposed || cloud.qr !== id) return
  try {
    const result = await api<{ state: string; error: string }>(`/xiaomi/qr/${id}`)
    if (disposed || cloud.qr !== id) return
    cloud.verifying = result.state === 'verifying'
    if (result.state === 'waiting' || result.state === 'verifying') {
      pollTimer = setTimeout(() => void pollQr(id), 2000)
      return
    }
    cloud.qr = ''
    if (result.state === 'connected') {
      await run('正在读取云相册…', loadAccount)
    } else cloud.error = result.error || '二维码已过期，请重新扫码。'
  } catch (error) {
    if (disposed || cloud.qr !== id) return
    cloud.qr = ''; cloud.error = (error as Error).message
  }
}

function startQr() {
  return run('正在生成二维码…', async () => {
    const { id } = await api<{ id: string }>('/xiaomi/qr', {})
    if (disposed) return
    cloud.qr = id; cloud.verifying = false
    void pollQr(id)
  })
}

function cancelQr() {
  const id = cloud.qr
  clearTimeout(pollTimer); cloud.qr = ''
  return run('正在取消扫码…', async () => {
    await api(`/xiaomi/qr/${id}/cancel`, {})
    await loadAccount()
  })
}

function disconnect() {
  return run('正在断开连接…', async () => {
    await api('/xiaomi/disconnect', { connection: cloud.account!.connection })
    await loadAccount()
    emit('message', '已断开小米账号')
  })
}

function changeAlbum() {
  cloud.items = []; cloud.ready = false
  return run('正在读取云相册…', () => loadMedia())
}

async function confirmRecycle(item: Media) {
  selected.value = item
  await nextTick(); recycleDialog.value?.showModal()
}

function recycle() {
  const item = selected.value!
  recycleDialog.value?.close()
  return run('正在移入小米云回收站…', async () => {
    await api('/xiaomi/recycle', { connection: cloud.account!.connection, id: item.id })
    cloud.items = cloud.items.filter(media => media.id !== item.id)
    emit('message', '已移入小米云回收站')
    await loadMedia(cloud.items.length || !cloud.last ? cloud.page : Math.max(0, cloud.page - 1))
  })
}

function openUpload() {
  Object.assign(upload, { file: null, name: '', error: '' })
  if (fileInput.value) fileInput.value.value = ''
  uploadDialog.value?.showModal()
}

function chooseFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] || null
  upload.file = file; upload.name = file?.name || ''; upload.error = ''
}

async function uploadFile() {
  const file = upload.file
  if (!file || cloud.busy) return
  if (!file.size) { upload.error = '不能上传空文件。'; return }
  const name = upload.name.trim()
  const extension = file.name.match(/\.[^.]+$/)?.[0]
  if (!extension || name.length <= extension.length || !name.toLowerCase().endsWith(extension.toLowerCase())) {
    upload.error = '请输入文件名，并保留原扩展名。'; return
  }
  upload.error = ''; cloud.error = ''; cloud.busy = '正在上传到小米云…'
  try {
    const response = await fetch(`/api/xiaomi/upload?${params({ album: cloud.album, name, size: String(file.size) })}`, {
      method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
    })
    if (!response.ok) {
      const result = await response.json().catch(() => null)
      throw new Error(result?.detail || `上传失败（HTTP ${response.status}），请先刷新相册确认结果。`)
    }
    const result = await response.json() as { exists: boolean }
    uploadDialog.value?.close()
    emit('message', result.exists ? '小米云已存在相同内容' : '小米云已确认上传')
  } catch (error) {
    upload.error = error instanceof TypeError ? '上传连接已中断，请先刷新相册确认结果再重试。' : (error as Error).message
    return
  } finally { cloud.busy = '' }
  await run('正在刷新云相册…', () => loadMedia())
}

onMounted(() => void run('正在读取连接…', loadAccount))
onUnmounted(() => { disposed = true; clearTimeout(pollTimer) })
</script>

<template>
  <div class="xiaomi-panel">
    <p v-if="cloud.error" class="notice error" role="alert">{{ cloud.error }}
      <button v-if="!cloud.account" class="text-button" :disabled="!!cloud.busy" @click="run('正在刷新…', loadAccount)">刷新连接</button>
    </p>
    <section v-if="!cloud.account" class="cloud-connect">
      <span class="welcome-icon"><Icon name="cloud" :size="42" /></span>
      <div>
        <h2>{{ cloud.qr ? '扫码连接小米账号' : '连接小米账号' }}</h2>
        <p v-if="!cloud.qr" class="muted">用小米手机扫码确认。首次连接前，可先在小米云网页版打开相册并完成安全验证。</p>
        <p v-else class="muted" role="status">{{ cloud.verifying ? '已扫码，正在验证云相册访问权限…' : '请使用小米手机扫描二维码并确认。' }}</p>
        <img v-if="cloud.qr && !cloud.verifying" class="cloud-qr" :src="`/api/xiaomi/qr/${cloud.qr}/image`" width="200" height="200" alt="小米账号登录二维码" />
        <div class="cloud-actions">
          <button v-if="cloud.qr" class="secondary" :disabled="!!cloud.busy" @click="cancelQr">取消扫码</button>
          <button v-else class="primary" :disabled="!!cloud.busy || !cloud.initialized" @click="startQr">{{ cloud.busy || '生成登录二维码' }}</button>
          <a class="text-button" href="https://i.mi.com/" target="_blank" rel="noopener noreferrer">打开小米云网页版</a>
        </div>
      </div>
    </section>
    <template v-else>
      <div class="cloud-account">
        <div><Icon name="cloud" :size="20" /><strong>小米账号</strong><span class="muted">{{ cloud.account.label }}</span></div>
        <button class="text-button" :disabled="!!cloud.busy" @click="disconnect">断开连接</button>
      </div>
      <section class="cloud-library" aria-label="云端文件">
        <div class="cloud-toolbar">
          <label>云相册<select v-model="cloud.album" :disabled="!!cloud.busy || !cloud.albums.length" @change="changeAlbum">
            <option v-if="!cloud.albums.length" value="">暂无可选相册</option>
            <option v-for="album in cloud.albums" :key="album.id" :value="album.id">{{ album.name }}</option>
          </select></label>
          <div class="cloud-actions">
            <button class="secondary" :disabled="!!cloud.busy" @click="run('正在刷新云相册…', loadAccount)"><Icon name="refresh" :size="17" />刷新</button>
            <button class="primary" :disabled="!!cloud.busy || !albumName || cloud.album === '1000'" @click="openUpload">上传图片或视频</button>
          </div>
        </div>
        <p v-if="cloud.busy" class="cloud-status muted" role="status">{{ cloud.busy }}</p>
        <p v-if="cloud.album === '1000'" class="cloud-status muted">隐私相册请在小米云网页版上传。</p>
        <ul v-if="cloud.items.length" class="cloud-files">
          <li v-for="item in cloud.items" :key="item.id">
            <span class="file-icon"><Icon :name="item.kind === 'video' ? 'video' : 'photo'" /></span>
            <div class="cloud-file"><strong>{{ item.name }}</strong><p class="muted">{{ item.kind === 'video' ? '视频' : '图片' }} · {{ takenAt(item.taken_at) }}<template v-if="item.size"> · {{ bytes(item.size) }}</template></p></div>
            <button class="text-button danger-text" :aria-label="'移入回收站：' + item.name" :disabled="!!cloud.busy" @click="confirmRecycle(item)"><Icon name="trash" :size="16" />移入回收站</button>
          </li>
        </ul>
        <div v-else-if="!cloud.busy && !cloud.error" class="empty-list">
          <Icon name="photo" :size="30" /><p>{{ cloud.album ? '这个相册还没有图片或视频' : '此账号没有可访问的云相册' }}</p>
        </div>
        <div v-if="cloud.ready && (cloud.page > 0 || !cloud.last)" class="pagination">
          <span>第 {{ cloud.page + 1 }} 页</span>
          <button class="secondary" :disabled="!!cloud.busy || cloud.page === 0" @click="run('正在读取…', () => loadMedia(cloud.page - 1))">上一页</button>
          <button class="secondary" :disabled="!!cloud.busy || cloud.last" @click="run('正在读取…', () => loadMedia(cloud.page + 1))">下一页</button>
        </div>
      </section>
    </template>

    <dialog ref="recycleDialog" class="task-dialog recycle-dialog">
      <template v-if="selected">
        <h2>移入小米云回收站？</h2>
        <p><strong>{{ selected.name }}</strong><br /><span class="muted">{{ takenAt(selected.taken_at) }} · 文件编号 {{ selected.id }}</span></p>
        <p>删除会同步到同账号已开启相册同步的设备。需要找回时，请前往小米云回收站。</p>
        <div class="dialog-actions"><button class="secondary" autofocus @click="recycleDialog?.close()">保留</button><button class="danger" @click="recycle">移入回收站</button></div>
      </template>
    </dialog>

    <dialog ref="uploadDialog" class="task-dialog cloud-upload" @cancel="(event) => { if (cloud.busy) event.preventDefault() }">
      <h2>上传到「{{ albumName }}」</h2>
      <form @submit.prevent="uploadFile">
        <label>选择图片或视频<input ref="fileInput" type="file" accept="image/*,video/*,.heic,.heif,.avci" :disabled="!!cloud.busy" required @change="chooseFile" /></label>
        <label v-if="upload.file">上传文件名<input v-model="upload.name" :disabled="!!cloud.busy" maxlength="255" required /></label>
        <p v-if="upload.error" class="form-error" role="alert">{{ upload.error }}</p>
        <p v-else-if="cloud.busy" class="muted" role="status">{{ cloud.busy }}请保持页面打开。</p>
        <div class="dialog-actions"><button type="button" class="secondary" :disabled="!!cloud.busy" @click="uploadDialog?.close()">取消</button><button type="submit" class="primary" :disabled="!!cloud.busy || !upload.file">{{ cloud.busy ? '上传中…' : '上传' }}</button></div>
      </form>
    </dialog>
  </div>
</template>

<style scoped lang="scss">
.cloud-connect, .cloud-account, .cloud-library { background: var(--canvas); border-radius: var(--radius); }
.cloud-connect { display: flex; align-items: flex-start; gap: 24px; padding: 32px; }
.cloud-connect p { margin-top: 8px; }
.cloud-connect .cloud-actions { margin-top: 16px; }
.cloud-qr { display: block; width: 200px; max-width: 100%; height: auto; margin-top: 14px; }
.cloud-account, .cloud-toolbar, .cloud-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.cloud-account, .cloud-toolbar { justify-content: space-between; }
.cloud-account { margin-bottom: 16px; padding: 8px 24px; }
.cloud-account > div { display: flex; align-items: center; gap: 10px; }
.cloud-account svg { color: var(--blue); }
.cloud-library { padding: 20px 24px; }
.cloud-toolbar { align-items: flex-end; padding-bottom: 16px; }
.cloud-toolbar label { width: min(300px, 100%); }
.cloud-status { margin-bottom: 10px; }
.cloud-files { margin: 0; padding: 0; list-style: none; }
.cloud-files li { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-top: 1px solid var(--soft); }
.cloud-file { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.cloud-file p { margin-top: 3px; font-size: 13px; }
.cloud-upload { width: min(560px, calc(100% - 32px)); }
.cloud-upload form { display: grid; gap: 16px; margin-top: 16px; }
.recycle-dialog p { overflow-wrap: anywhere; }
@media (max-width: 560px) {
  .cloud-connect, .cloud-account, .cloud-library { padding: 16px; }
  .cloud-connect .welcome-icon { display: none; }
  .cloud-toolbar { align-items: stretch; }
  .cloud-files .file-icon { display: none; }
}
</style>
