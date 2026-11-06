<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api, bytes } from './api'
import Icon from './Icon.vue'
interface Entry { name: string; path: string; directory: boolean; size: number | null; modified: number }
const filesModel = reactive({ path: '', root: '', items: [] as Entry[], total: 0, page: 1, search: '', appliedSearch: '', busy: false, error: '',
  preview: null as null | { token: string; total: number; items: { source: string; target: string }[] },
  job: { status: '', total: 0, done: 0, error: '' } })
const emit = defineEmits<{ message: [value: string] }>()
const previewDialog = ref<HTMLDialogElement>()
const crumbs = computed(() => filesModel.path.split('/').filter(p => p && p !== '.').map((name, index, all) => ({ name, path: all.slice(0, index + 1).join('/') })))
let timer: ReturnType<typeof setInterval>
async function load(path = filesModel.path, page = filesModel.page) {
  filesModel.busy = true; filesModel.error = ''
  try {
    const result = await api(`/files?path=${encodeURIComponent(path)}&page=${page}&search=${encodeURIComponent(filesModel.appliedSearch)}`)
    Object.assign(filesModel, result)
  } catch (error) { filesModel.error = (error as Error).message }
  finally { filesModel.busy = false }
}
async function open(path: string) { filesModel.search = filesModel.appliedSearch = ''; await load(path, 1) }
async function preview() {
  filesModel.busy = true; filesModel.error = ''
  try { filesModel.preview = await api('/files/preview', { path: filesModel.path === '.' ? '' : filesModel.path }); await nextTick(); previewDialog.value?.showModal() }
  catch (error) { filesModel.error = (error as Error).message }
  finally { filesModel.busy = false }
}
async function organize(token = '') {
  filesModel.busy = true; filesModel.error = ''
  try { await api('/files/organize', { token }); previewDialog.value?.close(); await poll(); emit('message', '整理已开始，可在这里查看进度') }
  catch (error) { filesModel.error = (error as Error).message }
  finally { filesModel.busy = false }
}
async function poll() {
  try {
    const previous = filesModel.job.status
    filesModel.job = await api('/files/job')
    if (previous === 'running' && filesModel.job.status === 'completed') { await load('', 1); emit('message', '文件已整理到下载根目录') }
  } catch (error) { filesModel.error = (error as Error).message }
}
onMounted(() => { void load(); void poll(); timer = setInterval(() => { if (!document.hidden) void poll() }, 2000) })
onUnmounted(() => clearInterval(timer))
</script>
<template>
  <section class="file-manager">
    <p v-if="filesModel.error" class="notice error" role="alert">{{ filesModel.error }}</p>
    <div v-if="filesModel.job.status" class="manual-job" :class="filesModel.job.status"><div><strong>{{ filesModel.job.status === 'completed' ? '整理完成' : filesModel.job.status === 'running' ? '正在整理' : '上次整理需要继续' }}</strong><p>{{ filesModel.job.done }} / {{ filesModel.job.total }} 个文件</p><p v-if="filesModel.job.error" class="danger-text">{{ filesModel.job.error }}</p></div><button v-if="['failed', 'interrupted'].includes(filesModel.job.status)" class="secondary" :disabled="filesModel.busy" @click="organize()">继续上次整理</button></div>
    <div class="files-heading"><div><h2>下载目录</h2><p class="muted">{{ filesModel.root }}</p></div><button class="primary" :disabled="filesModel.busy || filesModel.job.status === 'running'" @click="preview"><Icon name="workflow" :size="17" />预览整理此文件夹</button></div>
    <p class="muted files-help">把文件夹层级用“-”连接，移到绑定的下载根目录。手动整理保留 PSD 和 PDF，不覆盖已有文件。</p>
    <div class="files-toolbar"><nav class="breadcrumbs" aria-label="目录导航"><button @click="open('')"><Icon name="folder" :size="16" />根目录</button><template v-for="crumb in crumbs" :key="crumb.path"><span>/</span><button @click="open(crumb.path)">{{ crumb.name }}</button></template></nav><form class="search-box" @submit.prevent="filesModel.appliedSearch = filesModel.search; load(filesModel.path, 1)"><input v-model="filesModel.search" placeholder="搜索当前目录" aria-label="搜索文件" /><button class="text-button">搜索</button></form></div>
    <div class="files-list"><div class="files-list-head"><span>名称</span><span>大小</span><span>修改时间</span></div><div v-for="entry in filesModel.items" :key="entry.path" class="files-row"><button :disabled="!entry.directory" @click="open(entry.path)"><Icon :name="entry.directory ? 'folder' : 'file'" /><span>{{ entry.name }}</span><Icon v-if="entry.directory" name="chevron" :size="15" /></button><span>{{ entry.directory ? '文件夹' : bytes(entry.size || 0) }}</span><span>{{ new Date(entry.modified * 1000).toLocaleString('zh-CN') }}</span></div><div v-if="!filesModel.items.length" class="empty-list"><Icon name="folder" :size="32" /><p>{{ filesModel.busy ? '正在读取文件…' : '这个目录暂时没有文件' }}</p></div></div>
    <div class="pagination"><span>{{ filesModel.total }} 项</span><button class="secondary" :disabled="filesModel.page === 1 || filesModel.busy" @click="load(filesModel.path, filesModel.page - 1)">上一页</button><button class="secondary" :disabled="filesModel.page * 100 >= filesModel.total || filesModel.busy" @click="load(filesModel.path, filesModel.page + 1)">下一页</button></div>
    <dialog ref="previewDialog" class="task-dialog organize-dialog"><div class="section-heading"><h2>确认文件整理</h2><button class="icon-button" aria-label="关闭预览" @click="previewDialog?.close()"><Icon name="close" /></button></div><template v-if="filesModel.preview"><p class="muted">{{ filesModel.preview.total }} 个文件将移动到下载根目录。以下展示前 200 项，空目录会在移动成功后清理。</p><div class="rename-preview"><div v-for="item in filesModel.preview.items" :key="item.source"><span>{{ item.source }}</span><Icon name="arrow" :size="16" /><strong>{{ item.target }}</strong></div></div><p v-if="!filesModel.preview.total" class="notice">没有需要整理的文件。</p><p v-if="filesModel.error" class="notice error">{{ filesModel.error }}</p><div class="dialog-actions"><button class="secondary" @click="previewDialog?.close()">取消</button><button class="primary" :disabled="filesModel.busy || !filesModel.preview.total" @click="organize(filesModel.preview.token)">确认整理 {{ filesModel.preview.total }} 个文件</button></div></template></dialog>
  </section>
</template>
