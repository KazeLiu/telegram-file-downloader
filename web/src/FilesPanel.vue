<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api, bytes } from './api'
import Icon from './Icon.vue'
interface Entry { name: string; path: string; directory: boolean; size: number | null; modified: number }
const filesModel = reactive({ path: '', root: '', items: [] as Entry[], total: 0, page: 1, search: '', appliedSearch: '', loading: false, previewing: false, organizing: false, polling: false, error: '', delete_psd: false,
  preview: null as null | { token: string; total: number; items: { source: string; target: string }[]; delete_total: number; delete_items: string[] },
  job: { status: '', total: 0, done: 0, error: '', moved_files: 0, cleanup_total: 0, cleanup_done: 0 } })
const emit = defineEmits<{ message: [value: string] }>()
const previewDialog = ref<HTMLDialogElement>()
const crumbs = computed(() => filesModel.path.split('/').filter(p => p && p !== '.').map((name, index, all) => ({ name, path: all.slice(0, index + 1).join('/') })))
const unfinishedJob = computed(() => ['running', 'interrupted', 'failed'].includes(filesModel.job.status))
const busy = computed(() => filesModel.loading || filesModel.previewing || filesModel.organizing)
let timer: ReturnType<typeof setInterval>
async function load(path = filesModel.path, page = filesModel.page) {
  filesModel.loading = true; filesModel.error = ''
  try {
    const result = await api(`/files?path=${encodeURIComponent(path)}&page=${page}&search=${encodeURIComponent(filesModel.appliedSearch)}`)
    Object.assign(filesModel, result)
  } catch (error) { filesModel.error = (error as Error).message }
  finally { filesModel.loading = false }
}
async function open(path: string) { if (busy.value) return; filesModel.search = filesModel.appliedSearch = ''; filesModel.delete_psd = false; filesModel.preview = null; await load(path, 1) }
async function search() { if (busy.value) return; filesModel.appliedSearch = filesModel.search; await load(filesModel.path, 1) }
async function preview() {
  if (busy.value) return
  filesModel.previewing = true; filesModel.error = ''
  try { filesModel.preview = await api('/files/preview', { path: filesModel.path === '.' ? '' : filesModel.path, delete_psd: filesModel.delete_psd }); await nextTick(); previewDialog.value?.showModal() }
  catch (error) { filesModel.error = (error as Error).message }
  finally { filesModel.previewing = false }
}
async function organize(token = '') {
  filesModel.organizing = true; filesModel.error = ''
  try { await api('/files/organize', { token }); Object.assign(filesModel.job, { status: 'running' }); previewDialog.value?.close(); await poll(); if (filesModel.job.status !== 'completed') emit('message', '整理已开始，可在这里查看进度') }
  catch (error) { filesModel.error = (error as Error).message }
  finally { filesModel.organizing = false }
}
async function poll() {
  if (filesModel.polling) return
  filesModel.polling = true
  try {
    const previous = filesModel.job.status
    filesModel.job = await api('/files/job')
    if (previous === 'running' && filesModel.job.status === 'completed') { await load('', 1); emit('message', `整理完成，移动 ${filesModel.job.moved_files} 个文件，删除 ${filesModel.job.cleanup_done} 个 PSD/TXT 文件`) }
  } catch (error) { filesModel.error = (error as Error).message }
  finally { filesModel.polling = false }
}
onMounted(() => { void load(); void poll(); timer = setInterval(() => { if (!document.hidden) void poll() }, 2000) })
onUnmounted(() => clearInterval(timer))
</script>
<template>
  <section class="file-manager">
    <p v-if="filesModel.error" class="notice error" role="alert">{{ filesModel.error }}</p>
    <div v-if="filesModel.job.status" class="manual-job" :class="filesModel.job.status"><div><strong>{{ filesModel.job.status === 'completed' ? '整理完成' : filesModel.job.status === 'running' ? '正在整理' : '上次整理需要继续' }}</strong><p>{{ filesModel.job.done }} / {{ filesModel.job.total }} 个文件</p><p v-if="filesModel.job.cleanup_total">PSD/TXT 清理 {{ filesModel.job.cleanup_done }} / {{ filesModel.job.cleanup_total }} 个{{ unfinishedJob ? '，继续任务沿用上次确认的删除清单' : '' }}</p><p v-if="filesModel.job.error" class="danger-text">{{ filesModel.job.error }}</p></div><button v-if="['failed', 'interrupted'].includes(filesModel.job.status)" class="secondary" :disabled="busy" @click="organize()">继续上次整理</button></div>
    <div class="files-heading"><div><h2>下载目录</h2><p class="muted">{{ filesModel.root }}</p></div><button class="primary preview-button" :disabled="busy || unfinishedJob" :aria-busy="filesModel.previewing" :aria-label="filesModel.previewing ? '正在生成预览' : '预览整理此文件夹'" @click="preview"><Icon :name="filesModel.previewing ? 'loader' : 'workflow'" :class="{ 'loading-icon': filesModel.previewing }" :size="17" /><span role="status">{{ filesModel.previewing ? '正在生成预览…' : '预览整理此文件夹' }}</span></button></div>
    <p class="muted files-help">把文件夹层级用“-”连接，移到绑定的下载根目录。不覆盖已有文件，PDF 始终保留。</p>
    <label class="organize-option"><input v-model="filesModel.delete_psd" type="checkbox" :disabled="busy || unfinishedJob" @change="filesModel.preview = null" /><span>同时删除 PSD 和 TXT<small>同一规则清理当前文件夹及其子目录的 .psd、.txt 文件，确认后执行。</small></span></label>
    <div class="files-toolbar"><nav class="breadcrumbs" aria-label="目录导航"><button :disabled="busy" @click="open('')"><Icon name="folder" :size="16" />根目录</button><template v-for="crumb in crumbs" :key="crumb.path"><span>/</span><button :disabled="busy" @click="open(crumb.path)">{{ crumb.name }}</button></template></nav><form class="search-box" @submit.prevent="search"><input v-model="filesModel.search" :disabled="busy" placeholder="搜索当前目录" aria-label="搜索文件" /><button class="text-button" :disabled="busy">搜索</button></form></div>
    <div class="files-list" :aria-busy="filesModel.loading"><div class="files-list-head"><span>名称</span><span>大小</span><span>修改时间</span></div><div v-for="entry in filesModel.items" :key="entry.path" class="files-row"><button :disabled="!entry.directory || busy" @click="open(entry.path)"><Icon :name="entry.directory ? 'folder' : 'file'" /><span>{{ entry.name }}</span><Icon v-if="entry.directory" name="chevron" :size="15" /></button><span>{{ entry.directory ? '文件夹' : bytes(entry.size || 0) }}</span><span>{{ new Date(entry.modified * 1000).toLocaleString('zh-CN') }}</span></div><div v-if="!filesModel.items.length" class="empty-list"><Icon name="folder" :size="32" /><p>{{ filesModel.loading ? '正在读取文件…' : '这个目录暂时没有文件' }}</p></div></div>
    <div class="pagination"><span>{{ filesModel.total }} 项</span><button class="secondary" :disabled="filesModel.page === 1 || busy" @click="load(filesModel.path, filesModel.page - 1)">上一页</button><button class="secondary" :disabled="filesModel.page * 100 >= filesModel.total || busy" @click="load(filesModel.path, filesModel.page + 1)">下一页</button></div>
    <dialog ref="previewDialog" class="task-dialog organize-dialog">
      <div class="section-heading"><h2>确认文件整理</h2><button class="icon-button" aria-label="关闭预览" @click="previewDialog?.close()"><Icon name="close" /></button></div>
      <template v-if="filesModel.preview">
        <p class="muted">移动 {{ filesModel.preview.total }} 个文件到下载根目录，删除 {{ filesModel.preview.delete_total }} 个 PSD/TXT 文件。各列表最多展示前 200 项，空目录会在处理成功后清理。</p>
        <div v-if="filesModel.preview.total" class="rename-preview"><div v-for="item in filesModel.preview.items" :key="item.source"><span>{{ item.source }}</span><Icon name="arrow" :size="16" /><strong>{{ item.target }}</strong></div></div>
        <template v-if="filesModel.preview.delete_total"><p class="notice error">以下 {{ filesModel.preview.delete_total }} 个 PSD/TXT 文件将永久删除，无法撤销。PDF 保留。</p><div class="delete-preview"><div v-for="name in filesModel.preview.delete_items" :key="name"><Icon name="trash" :size="16" /><span>{{ name }}</span><span class="badge failed">删除</span></div></div></template>
        <p v-if="!filesModel.preview.total && !filesModel.preview.delete_total" class="notice">没有需要移动或清理的文件。</p>
        <p v-if="filesModel.error" class="notice error">{{ filesModel.error }}</p>
        <div class="dialog-actions"><button class="secondary" @click="previewDialog?.close()">取消</button><button :class="filesModel.preview.delete_total ? 'danger' : 'primary'" :disabled="busy || (!filesModel.preview.total && !filesModel.preview.delete_total)" @click="organize(filesModel.preview.token)">{{ filesModel.preview.delete_total ? `确认${filesModel.preview.total ? '整理并' : ''}删除 ${filesModel.preview.delete_total} 个文件` : `确认移动 ${filesModel.preview.total} 个文件` }}</button></div>
      </template>
    </dialog>
  </section>
</template>
