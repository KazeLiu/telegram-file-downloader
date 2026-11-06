<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch, watchEffect } from 'vue'
import { useRoute, useRouter } from '#imports'
import { queryPage } from './routeState'
import { api, bytes } from './api'
import Icon from './Icon.vue'
import XiaomiBatchUpload from './XiaomiBatchUpload.vue'
import XiaomiNameRecycle from './XiaomiNameRecycle.vue'
import XiaomiRecycleDialog from './XiaomiRecycleDialog.vue'
import XiaomiThumbnail from './XiaomiThumbnail.vue'
import XiaomiLocalBinding from './XiaomiLocalBinding.vue'
import XiaomiLocalIndicator from './XiaomiLocalIndicator.vue'
import { photoDay, takenAt, type CloudMedia as Media, type LocalFileState } from './xiaomiMedia'

type Account = { connection: string; label: string }
type Album = { id: string; name: string; cover?: string }
const route = useRoute()
const router = useRouter()
const props = defineProps<{ lastLocalRecycle: string[] }>()
const emit = defineEmits<{ message: [text: string] }>()
const cloud = reactive({ account: null as Account | null, albums: [] as Album[], album: '', items: [] as Media[],
  wall: false, page: 0, last: true, ready: false, busy: '', error: '', initialized: false, qr: '', verifying: false,
  coverErrors: new Set<string>(), bound: false, localStates: {} as Record<string, LocalFileState>,
  organizing: false, selected: new Map<string, Media>() })
const upload = reactive({ file: null as File | null, name: '', error: '' })
const recycleDialog = ref<InstanceType<typeof XiaomiRecycleDialog>>()
const uploadDialog = ref<HTMLDialogElement>()
const fileInput = ref<HTMLInputElement>()
const albumHeading = ref<HTMLHeadingElement>()
const wallEnd = ref<HTMLDivElement>()
const albumName = computed(() => cloud.albums.find(item => item.id === cloud.album)?.name || '')
const selectedCount = computed(() => cloud.selected.size)
const allSelected = computed(() => cloud.items.length > 0 && cloud.items.every(item => cloud.selected.has(item.id)))
let pollTimer: ReturnType<typeof setTimeout>
let disposed = false
let wallObserver: IntersectionObserver | undefined
let loadedRoute = ''

function albumRoute(album = cloud.album, wall = cloud.wall, page = 0) {
  return router.push({ path: album ? `/xiaomi/albums/${encodeURIComponent(album)}` : '/xiaomi', query: album ? { wall: wall ? '1' : undefined, page: !wall && page ? String(page + 1) : undefined } : {} })
}
watch(() => [route.fullPath, cloud.account?.connection, cloud.busy], () => {
  if (!cloud.account || cloud.busy || disposed || !route.path.startsWith('/xiaomi')) return
  const key = `${cloud.account.connection}:${route.fullPath}`
  if (key === loadedRoute) return
  loadedRoute = key
  const album = /^\/xiaomi\/albums\/([^/]+)$/.exec(route.path)?.[1] || ''
  if (cloud.album !== album) { cloud.organizing = false; cloud.bound = false }
  cloud.album = album; cloud.wall = route.query.wall === '1'; resetMedia()
  if (album) void run('正在读取相册内容…', () => loadMedia(cloud.wall ? 0 : queryPage(route.query.page) - 1))
})

function params(values: Record<string, string>) {
  return new URLSearchParams({ connection: cloud.account!.connection, ...values })
}

async function run(label: string, action: () => Promise<void>) {
  if (cloud.busy) return
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
  } else { cloud.items = result.items; cloud.selected.clear() }
  cloud.last = result.last; cloud.page = page; cloud.ready = true
}

function resetMedia() {
  cloud.items = []; cloud.page = 0; cloud.last = true; cloud.ready = false
  cloud.localStates = {}
  cloud.selected.clear()
}

function select(item: Media) {
  if (cloud.selected.has(item.id)) cloud.selected.delete(item.id)
  else cloud.selected.set(item.id, item)
}

function selectLoaded() {
  const selecting = !allSelected.value
  for (const item of cloud.items) {
    if (selecting) cloud.selected.set(item.id, item)
    else cloud.selected.delete(item.id)
  }
}

function toggleOrganizing() {
  cloud.organizing = !cloud.organizing
  cloud.selected.clear()
  if (cloud.organizing && !cloud.wall) {
    return albumRoute(cloud.album, true)
  }
}

function confirmSelected() {
  if (!cloud.busy && selectedCount.value) return recycleDialog.value?.open([...cloud.selected.values()])
}

function localStatus(states: Record<string, LocalFileState>, bound: boolean) {
  cloud.localStates = states; cloud.bound = bound
}

function loadMore() {
  if (!cloud.wall || !cloud.ready || cloud.last || cloud.busy || cloud.error || disposed) return
  void run('正在加载下一批图片…', () => loadMedia(cloud.page + 1, true))
}

watchEffect(() => {
  wallObserver?.disconnect()
  if (wallEnd.value && cloud.wall && cloud.ready && !cloud.last && !cloud.busy && !cloud.error) wallObserver?.observe(wallEnd.value)
}, { flush: 'post' })

async function loadAccount() {
  const previous = cloud.account?.connection
  const result = await api<{ account: Account | null }>('/xiaomi/account')
  cloud.account = result.account; cloud.initialized = true
  if (!cloud.account || cloud.account.connection !== previous) {
    loadedRoute = ''
    cloud.organizing = false
    cloud.albums = []; cloud.album = ''; resetMedia()
  }
  if (!cloud.account) return
  cloud.albums = (await api<{ items: Album[] }>(`/xiaomi/albums?${params({})}`)).items
  cloud.coverErrors.clear()
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
  await albumRoute(album, false)
  await nextTick(); albumHeading.value?.focus()
}

function toggleWall(event: Event) {
  return albumRoute(cloud.album, (event.target as HTMLInputElement).checked)
}

async function backToAlbums() {
  const previous = cloud.album
  cloud.error = ''; await albumRoute('')
  await nextTick(); document.getElementById(`xiaomi-album-${previous}`)?.focus()
}

function batchFinished(album: string) {
  if (album === cloud.album && !cloud.busy) void run('正在刷新云相册…', () => loadMedia())
}

async function confirmRecycle(item: Media) {
  await recycleDialog.value?.open([item])
}

function afterNameRecycle(ids: string[]) {
  const moved = new Set(ids)
  ids.forEach(id => cloud.selected.delete(id))
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

onMounted(() => {
  wallObserver = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) loadMore() }, { rootMargin: '0px 0px 160px' })
  void run('正在读取连接…', loadAccount)
})
onUnmounted(() => { disposed = true; clearTimeout(pollTimer); wallObserver?.disconnect() })
</script>

<template>
  <div class="xiaomi-panel" :class="{ 'has-selection': cloud.organizing && selectedCount }">
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
            <span class="album-cover" :class="{ 'album-private': album.id === '1000' }">
              <img v-if="album.cover && !cloud.coverErrors.has(album.id)" :src="album.cover" alt="" loading="lazy" decoding="async" @error="cloud.coverErrors.add(album.id)" />
              <Icon v-else :name="album.id === '1000' ? 'lock' : 'folder'" :size="22" />
            </span>
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
            <label class="wall-toggle"><input type="checkbox" role="switch" :checked="cloud.wall" :disabled="!!cloud.busy" @change="toggleWall" />图片墙</label>
            <button class="secondary" :disabled="!!cloud.busy" @click="run('正在刷新相册内容…', () => loadMedia(cloud.wall ? 0 : cloud.page))"><Icon name="refresh" :size="17" />刷新</button>
            <button :class="cloud.organizing ? 'primary' : 'secondary'" :disabled="!!cloud.busy || !cloud.ready" @click="toggleOrganizing">{{ cloud.organizing ? '完成' : '管理' }}</button>
            <XiaomiNameRecycle :key="`${cloud.account.connection}:${cloud.album}`" :connection="cloud.account.connection" :album="cloud.album" :album-name="albumName"
              :last-local-recycle="props.lastLocalRecycle" :disabled="!!cloud.busy || cloud.organizing" @confirm="recycleDialog?.open($event)" />
            <button class="secondary" :disabled="!!cloud.busy || cloud.organizing || !albumName || cloud.album === '1000'" @click="openUpload">从此设备上传</button>
            <XiaomiBatchUpload :key="cloud.account.connection" :connection="cloud.account.connection" :album="cloud.album" :albums="cloud.albums" :disabled="!!cloud.busy || cloud.organizing || !albumName"
              @message="emit('message', $event)" @finished="batchFinished" />
          </div>
        </div>
        <XiaomiLocalBinding :key="`${cloud.account.connection}:${cloud.album}`" :connection="cloud.account.connection" :album="cloud.album" :items="cloud.items" @status="localStatus" />
        <XiaomiRecycleDialog :key="`recycle:${cloud.account.connection}:${cloud.album}`" ref="recycleDialog" :connection="cloud.account.connection" :album="cloud.album" @recycled="afterNameRecycle" @message="emit('message', $event)" />
        <p v-if="cloud.album === '1000'" class="cloud-status muted">隐私相册请在小米云网页版上传。</p>
        <div v-if="cloud.organizing" class="cloud-selection-actions">
          <span role="status">已选 {{ selectedCount }} 项</span>
          <button class="text-button" :disabled="!!cloud.busy || !cloud.items.length" @click="selectLoaded">{{ allSelected ? '取消已加载选择' : '全选已加载' }}</button>
        </div>
        <ul v-if="cloud.wall && cloud.items.length" class="cloud-wall">
          <template v-for="(item, index) in cloud.items" :key="item.id">
          <li v-if="index === 0 || photoDay(item.sort_time) !== photoDay(cloud.items[index - 1]!.sort_time)" class="col-span-full pt-3 pb-1"><h3 class="text-sm font-medium">{{ photoDay(item.sort_time) }}</h3></li>
          <li class="relative min-w-0">
            <div class="relative">
              <button v-if="cloud.organizing" type="button" class="image-preview rounded-lg" :aria-label="'选择 ' + item.name" :aria-pressed="cloud.selected.has(item.id)" :disabled="!!cloud.busy" @click="select(item)"><span class="image-thumb"><XiaomiThumbnail :item="item" /></span></button>
              <XiaomiThumbnail v-else :item="item" />
              <XiaomiLocalIndicator v-if="cloud.bound" :state="cloud.localStates[item.id] || 'unknown'" dot />
            </div>
            <button v-if="!cloud.organizing" class="wall-recycle" :aria-label="'移入回收站：' + item.name" :disabled="!!cloud.busy" @click="confirmRecycle(item)"><Icon name="trash" :size="15" /></button>
            <p class="truncate text-xs text-muted" :title="item.name">{{ item.name }}</p>
          </li>
          </template>
        </ul>
        <ul v-else-if="cloud.items.length" class="cloud-files">
          <li v-for="item in cloud.items" :key="item.id" :class="{ 'is-selected': cloud.organizing && cloud.selected.has(item.id) }">
            <component :is="cloud.organizing ? 'button' : 'div'" class="cloud-file" :class="{ 'cloud-file-select': cloud.organizing }" :type="cloud.organizing ? 'button' : undefined"
              :aria-label="cloud.organizing ? '选择 ' + item.name : undefined" :aria-pressed="cloud.organizing ? cloud.selected.has(item.id) : undefined" :disabled="cloud.organizing ? !!cloud.busy : undefined" @click="cloud.organizing && select(item)">
              <strong class="cloud-file-name" :title="item.name"><Icon :name="item.kind === 'video' ? 'video' : 'photo'" :size="15" /><span class="truncate">{{ item.name }}</span></strong>
              <p class="cloud-file-meta"><time class="min-w-0 flex-1 truncate" :title="takenAt(item.sort_time)">{{ takenAt(item.sort_time) }}</time><span class="shrink-0">{{ item.size === null ? '大小未知' : bytes(item.size) }}</span><XiaomiLocalIndicator v-if="cloud.bound" :state="cloud.localStates[item.id] || 'unknown'" /></p>
            </component>
            <Icon v-if="cloud.organizing && cloud.selected.has(item.id)" name="check" class="cloud-file-check" :size="17" />
            <button v-if="!cloud.organizing" class="cloud-file-delete" :aria-label="'移入回收站：' + item.name" :title="'移入回收站：' + item.name" :disabled="!!cloud.busy" @click="confirmRecycle(item)"><Icon name="trash" :size="15" /></button>
          </li>
        </ul>
        <div v-else-if="!cloud.busy && !cloud.error && cloud.last" class="empty-list">
          <Icon name="photo" :size="30" /><p>这个相册还没有图片或视频</p>
        </div>
        <div v-if="cloud.wall && cloud.ready && !cloud.last" ref="wallEnd" class="wall-end" role="status">
          <template v-if="cloud.busy">正在加载…</template>
          <button v-else-if="cloud.error" class="text-button" @click="cloud.error = ''; loadMore()">重试加载</button>
        </div>
        <div v-if="!cloud.wall && cloud.ready && (cloud.page > 0 || !cloud.last)" class="pagination">
          <span>第 {{ cloud.page + 1 }} 页</span>
          <button class="secondary" :disabled="!!cloud.busy || cloud.page === 0" @click="albumRoute(cloud.album, false, cloud.page - 1)">上一页</button>
          <button class="secondary" :disabled="!!cloud.busy || cloud.last" @click="albumRoute(cloud.album, false, cloud.page + 1)">下一页</button>
        </div>
        <button v-if="cloud.organizing && selectedCount" class="danger recycle-selection" :disabled="!!cloud.busy" @click="confirmSelected"><Icon name="trash" :size="16" />回收所选云端文件 · {{ selectedCount }} 项</button>
      </section>
    </template>

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
.cloud-albums { @apply grid grid-cols-2 gap-2 min-[760px]:grid-cols-3 xl:grid-cols-5; }
.cloud-album { @apply flex min-h-16 min-w-0 items-center gap-2 rounded-lg border border-solid border-hairline bg-canvas px-3 py-2 text-left; }
.album-cover { @apply grid size-9 shrink-0 place-items-center overflow-hidden rounded-lg bg-blue/10 text-blue; }
.album-cover img { @apply size-full object-cover; }
.album-cover.album-private { @apply bg-soft text-muted; }
.album-label { @apply flex min-w-0 flex-1 items-center justify-between gap-2; }
.album-label strong { @apply min-w-0; overflow-wrap: anywhere; }
.album-label svg { @apply text-muted; }
.cloud-library { @apply px-6 py-5; }
.xiaomi-panel.has-selection { padding-bottom: calc(64px + env(safe-area-inset-bottom)); }
.cloud-selection-actions { @apply mb-4 flex flex-wrap items-center gap-4 text-sm; }
.cloud-toolbar { @apply pb-4; }
.cloud-detail-heading { @apply flex min-w-0 flex-wrap items-center gap-x-4; }
.cloud-detail-heading h2 { overflow-wrap: anywhere; }
.cloud-status { @apply mb-2.5; }
.wall-toggle { @apply flex flex-row items-center gap-2; }
.wall-end { @apply grid min-h-14 place-items-center text-sm text-muted; }
.cloud-files {
  --file-gap: 10px;
  @apply m-0 grid list-none p-0;
  gap: var(--file-gap);
  grid-template-columns: repeat(auto-fill, minmax(clamp(calc((100% - 11 * var(--file-gap)) / 12), 260px, calc((100% - 2 * var(--file-gap)) / 3)), 1fr));
}
.cloud-wall { @apply m-0 grid list-none grid-cols-3 gap-2 p-0 sm:grid-cols-5 lg:grid-cols-8 xl:grid-cols-10; }
.wall-recycle { @apply absolute top-1 right-1 grid size-8 min-h-0 place-items-center rounded-full bg-canvas p-0 text-danger; }
.cloud-files li { @apply relative min-w-0 rounded-lg border border-solid border-hairline py-2 pr-1 pl-2; }
.cloud-file { @apply min-w-0; }
.cloud-file-select { @apply min-h-11 w-full border-0 bg-transparent p-0 text-left; }
.cloud-files li.is-selected { @apply border-blue bg-blue/5; }
.cloud-file-check { @apply pointer-events-none absolute top-2 right-2 text-blue; }
.cloud-file-name { @apply mr-7 flex min-w-0 items-center gap-1.5 text-sm font-normal; }
.cloud-file-name svg { @apply text-muted; }
.cloud-file-meta { @apply mt-2 flex items-center gap-1.5 text-xs text-muted; }
.cloud-file-delete { @apply absolute top-0.5 right-0.5 grid min-h-8 w-7 place-items-center rounded-md p-0 text-danger; }
.cloud-upload { width: min(560px, calc(100% - 32px)); }
.cloud-upload form { @apply mt-4 grid gap-4; }
.recycle-dialog p { overflow-wrap: anywhere; }
@media (max-width: 560px) {
  .cloud-connect, .cloud-library { @apply p-4; }
  .cloud-connect .welcome-icon { @apply hidden; }
  .cloud-files { --file-gap: 5px; }
  .cloud-file-name svg, .cloud-file-meta time { @apply hidden; }
  .cloud-file-meta { @apply flex-wrap; }
  .cloud-toolbar { @apply items-stretch; }
}
</style>
