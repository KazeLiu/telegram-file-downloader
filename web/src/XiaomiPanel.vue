<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api, bytes } from './api'
import Icon from './Icon.vue'
import XiaomiBatchUpload from './XiaomiBatchUpload.vue'
import XiaomiNameRecycle from './XiaomiNameRecycle.vue'
import XiaomiThumbnail from './XiaomiThumbnail.vue'
import { takenAt, type CloudMedia as Media } from './xiaomiMedia'

type Account = { connection: string; label: string }
type Album = { id: string; name: string }
const props = defineProps<{ lastLocalRecycle: string[] }>()
const emit = defineEmits<{ message: [text: string] }>()
const cloud = reactive({ account: null as Account | null, albums: [] as Album[], album: '', items: [] as Media[],
  wall: false, page: 0, last: true, ready: false, busy: '', error: '', initialized: false, qr: '', verifying: false })
const upload = reactive({ file: null as File | null, name: '', error: '' })
const selected = ref<Media>()
const recycleDialog = ref<HTMLDialogElement>()
const uploadDialog = ref<HTMLDialogElement>()
const fileInput = ref<HTMLInputElement>()
const albumHeading = ref<HTMLHeadingElement>()
const albumName = computed(() => cloud.albums.find(item => item.id === cloud.album)?.name || '')
let pollTimer: ReturnType<typeof setTimeout>
let disposed = false

function params(values: Record<string, string>) {
  return new URLSearchParams({ connection: cloud.account!.connection, ...values })
}

async function run(label: string, action: () => Promise<void>) {
  cloud.busy = label; cloud.error = ''
  try { await action() }
  catch (error) { cloud.error = (error as Error).message }
  finally { cloud.busy = '' }
}

async function loadMedia(page = 0, append = false) {
  const result = await api<{ items: Media[]; last: boolean }>(`/xiaomi/media?${params({ album: cloud.album, page: String(page), wall: String(cloud.wall) })}`)
  if (append) {
    const existing = new Set(cloud.items.map(item => item.id))
    cloud.items.push(...result.items.filter(item => !existing.has(item.id)))
  } else cloud.items = result.items
  cloud.last = result.last; cloud.page = page; cloud.ready = true
}

function resetMedia() {
  cloud.items = []; cloud.page = 0; cloud.last = true; cloud.ready = false
}

async function loadAccount() {
  const previous = cloud.account?.connection
  const result = await api<{ account: Account | null }>('/xiaomi/account')
  cloud.account = result.account; cloud.initialized = true
  if (!cloud.account || cloud.account.connection !== previous) {
    cloud.albums = []; cloud.album = ''; resetMedia()
  }
  if (!cloud.account) return
  cloud.albums = (await api<{ items: Album[] }>(`/xiaomi/albums?${params({})}`)).items
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

async function openAlbum(album: string) {
  cloud.album = album; cloud.wall = false; resetMedia()
  void run('正在读取相册内容…', () => loadMedia())
  await nextTick(); albumHeading.value?.focus()
}

function toggleWall(event: Event) {
  cloud.wall = (event.target as HTMLInputElement).checked
  resetMedia()
  return run('正在读取相册内容…', () => loadMedia())
}

async function backToAlbums() {
  const previous = cloud.album
  cloud.album = ''; cloud.error = ''; resetMedia()
  await nextTick(); document.getElementById(`xiaomi-album-${previous}`)?.focus()
}

function batchFinished(album: string) {
  if (album === cloud.album && !cloud.busy) void run('正在刷新云相册…', () => loadMedia())
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
    await loadMedia(cloud.wall ? 0 : cloud.items.length || !cloud.last ? cloud.page : Math.max(0, cloud.page - 1))
  })
}

function afterNameRecycle(ids: string[]) {
  const moved = new Set(ids)
  cloud.items = cloud.items.filter(item => !moved.has(item.id))
  if (!cloud.busy) void run('正在刷新相册内容…', () => loadMedia())
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
      <span class="welcome-icon"><Icon name="cloud" :size="28" /></span>
      <div>
        <h2>{{ cloud.qr ? '扫码连接小米账号' : '连接小米账号' }}</h2>
        <p v-if="!cloud.qr" class="muted">遇到安全验证时，先在小米云网页版打开相册。</p>
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
        <div>
          <button v-if="!cloud.album" class="text-button" :disabled="!!cloud.busy" @click="run('正在刷新相册列表…', loadAccount)"><Icon name="refresh" :size="16" />刷新</button>
          <button class="text-button" :disabled="!!cloud.busy" @click="disconnect">断开连接</button>
        </div>
      </div>
      <p v-if="cloud.busy" class="cloud-status muted" role="status">{{ cloud.busy }}</p>
      <template v-if="!cloud.album">
        <section v-if="cloud.albums.length" class="cloud-albums" aria-label="相册列表">
          <button v-for="album in cloud.albums" :id="`xiaomi-album-${album.id}`" :key="album.id" type="button" class="cloud-album" :disabled="!!cloud.busy" @click="openAlbum(album.id)">
            <span class="album-cover" :class="{ 'album-private': album.id === '1000' }"><Icon :name="album.id === '1000' ? 'lock' : album.id === '1' || album.id === '2' ? 'photo' : 'folder'" :size="32" /></span>
            <span class="album-label"><strong>{{ album.name }}</strong><Icon name="chevron" :size="15" /></span>
          </button>
        </section>
        <div v-else-if="!cloud.busy && !cloud.error" class="empty-list"><Icon name="folder" :size="30" /><p>此账号没有可访问的相册</p></div>
      </template>
      <section v-else class="cloud-library" aria-labelledby="xiaomi-album-heading">
        <div class="cloud-toolbar">
          <div class="cloud-detail-heading">
            <button class="text-button" :disabled="!!cloud.busy" @click="backToAlbums"><Icon name="chevron" class="rotate-180" :size="16" />返回相册</button>
            <h2 id="xiaomi-album-heading" ref="albumHeading" tabindex="-1">{{ albumName }}</h2>
          </div>
          <div class="cloud-actions">
            <label class="flex flex-row items-center gap-2"><input type="checkbox" role="switch" :checked="cloud.wall" :disabled="!!cloud.busy" @change="toggleWall" />图片墙</label>
            <button class="secondary" :disabled="!!cloud.busy" @click="run('正在刷新相册内容…', () => loadMedia(cloud.wall ? 0 : cloud.page))"><Icon name="refresh" :size="17" />刷新</button>
            <XiaomiNameRecycle :key="`${cloud.account.connection}:${cloud.album}`" :connection="cloud.account.connection" :album="cloud.album" :album-name="albumName"
              :last-local-recycle="props.lastLocalRecycle" :disabled="!!cloud.busy" @recycled="afterNameRecycle" @message="emit('message', $event)" />
            <button class="secondary" :disabled="!!cloud.busy || !albumName || cloud.album === '1000'" @click="openUpload">从此设备上传</button>
            <XiaomiBatchUpload :key="cloud.account.connection" :connection="cloud.account.connection" :album="cloud.album" :albums="cloud.albums" :disabled="!!cloud.busy || !albumName"
              @message="emit('message', $event)" @finished="batchFinished" />
          </div>
        </div>
        <p v-if="cloud.album === '1000'" class="cloud-status muted">隐私相册请在小米云网页版上传。</p>
        <ul v-if="cloud.wall && cloud.items.length" class="cloud-wall">
          <li v-for="item in cloud.items" :key="item.id" class="relative min-w-0">
            <XiaomiThumbnail :item="item" />
            <button class="wall-recycle" :aria-label="'移入回收站：' + item.name" :disabled="!!cloud.busy" @click="confirmRecycle(item)"><Icon name="trash" :size="15" /></button>
            <p class="truncate text-xs text-muted" :title="item.name">{{ item.name }}</p>
          </li>
        </ul>
        <ul v-else-if="cloud.items.length" class="cloud-files">
          <li v-for="item in cloud.items" :key="item.id">
            <span class="file-icon"><Icon :name="item.kind === 'video' ? 'video' : 'photo'" /></span>
            <div class="cloud-file"><strong>{{ item.name }}</strong><p class="muted"><span class="sr-only">{{ item.kind === 'video' ? '视频' : '图片' }}，</span>{{ takenAt(item.taken_at) }}<template v-if="item.size"> · {{ bytes(item.size) }}</template></p></div>
            <button class="text-button danger-text" :aria-label="'移入回收站：' + item.name" :disabled="!!cloud.busy" @click="confirmRecycle(item)"><Icon name="trash" :size="16" />移入回收站</button>
          </li>
        </ul>
        <div v-else-if="!cloud.busy && !cloud.error && cloud.last" class="empty-list">
          <Icon name="photo" :size="30" /><p>这个相册还没有图片或视频</p>
        </div>
        <div v-if="cloud.wall && cloud.ready && !cloud.last" class="mt-4 text-center">
          <button class="secondary" :disabled="!!cloud.busy" @click="run('正在加载下一批图片…', () => loadMedia(cloud.page + 1, true))">加载下 20 张</button>
        </div>
        <div v-if="!cloud.wall && cloud.ready && (cloud.page > 0 || !cloud.last)" class="pagination">
          <span>第 {{ cloud.page + 1 }} 页</span>
          <button class="secondary" :disabled="!!cloud.busy || cloud.page === 0" @click="run('正在读取…', () => loadMedia(cloud.page - 1))">上一页</button>
          <button class="secondary" :disabled="!!cloud.busy || cloud.last" @click="run('正在读取…', () => loadMedia(cloud.page + 1))">下一页</button>
        </div>
      </section>
    </template>

    <dialog ref="recycleDialog" class="task-dialog recycle-dialog">
      <template v-if="selected">
        <h2>移入小米云回收站？</h2>
        <div v-if="selected.thumbnail" class="mt-4 max-w-40"><XiaomiThumbnail :item="selected" /></div>
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

<style scoped>
@reference '../app/assets/main.css';

.cloud-connect, .cloud-library { @apply rounded-panel bg-canvas; }
.cloud-connect { @apply flex items-start gap-5 p-6; }
.cloud-connect p { @apply mt-2; }
.cloud-connect .cloud-actions { @apply mt-4; }
.cloud-qr { @apply mt-3.5 block h-auto w-[200px] max-w-full; }
.cloud-account, .cloud-toolbar, .cloud-actions { @apply flex flex-wrap items-center gap-3; }
.cloud-account, .cloud-toolbar { @apply justify-between; }
.cloud-account { @apply mb-2; }
.cloud-account > div { @apply flex items-center gap-2.5; }
.cloud-account svg { @apply text-blue; }
.cloud-albums { @apply grid grid-cols-2 gap-3 min-[760px]:grid-cols-3 xl:grid-cols-4; }
.cloud-album { @apply flex min-w-0 flex-col overflow-hidden rounded-xl border border-solid border-hairline bg-canvas p-0 text-left; }
.album-cover { @apply grid aspect-[2/1] w-full place-items-center bg-blue/10 text-blue; }
.album-cover.album-private { @apply bg-soft text-muted; }
.album-label { @apply flex min-h-12 w-full items-center justify-between gap-2 px-3 py-2; }
.album-label strong { @apply min-w-0; overflow-wrap: anywhere; }
.album-label svg { @apply text-muted; }
.cloud-library { @apply px-6 py-5; }
.cloud-toolbar { @apply pb-4; }
.cloud-detail-heading { @apply flex min-w-0 flex-wrap items-center gap-x-4; }
.cloud-detail-heading h2 { overflow-wrap: anywhere; }
.cloud-status { @apply mb-2.5; }
.cloud-files { @apply m-0 list-none p-0; }
.cloud-wall { @apply m-0 grid list-none grid-cols-3 gap-2 p-0 sm:grid-cols-5 lg:grid-cols-8 xl:grid-cols-10; }
.wall-recycle { @apply absolute top-1 right-1 grid size-8 min-h-0 place-items-center rounded-full bg-canvas p-0 text-danger; }
.cloud-files li { @apply flex items-center gap-3 py-3; border-top: 1px solid var(--color-soft); }
.cloud-file { @apply min-w-0 flex-1; overflow-wrap: anywhere; }
.cloud-file p { @apply mt-1 text-[13px]; }
.cloud-upload { width: min(560px, calc(100% - 32px)); }
.cloud-upload form { @apply mt-4 grid gap-4; }
.recycle-dialog p { overflow-wrap: anywhere; }
@media (max-width: 560px) {
  .cloud-connect, .cloud-library { @apply p-4; }
  .cloud-connect .welcome-icon { @apply hidden; }
  .cloud-files .file-icon { @apply size-8; }
  .cloud-toolbar { @apply items-stretch; }
}
</style>
