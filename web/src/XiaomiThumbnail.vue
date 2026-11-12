<script setup lang="ts">
import { ref, watch } from 'vue'
import Icon from './Icon.vue'
import type { CloudMedia } from './xiaomiMedia'

const props = defineProps<{ item: CloudMedia; broken?: boolean }>()
const emit = defineEmits<{ error: [] }>()
const broken = ref(false)
watch(() => props.item, () => { broken.value = false })
</script>

<template>
  <span class="cloud-thumbnail" :title="broken || props.broken ? '缩略图加载失败，刷新相册后重试' : !item.thumbnail ? '小米未提供可显示的缩略图' : undefined">
    <img v-if="item.thumbnail && !broken && !props.broken" :src="item.thumbnail" alt="" loading="lazy" decoding="async" @error="broken = true; emit('error')" />
    <Icon v-else :name="item.kind === 'video' ? 'video' : 'photo'" :size="22" />
    <span v-if="item.kind === 'video' && item.thumbnail && !broken && !props.broken" class="absolute right-1 bottom-1 rounded bg-ink/70 p-1 text-white"><Icon name="video" :size="13" /></span>
  </span>
</template>

<style scoped>
@reference '../app/assets/main.css';
.cloud-thumbnail { @apply relative grid aspect-square w-full place-items-center overflow-hidden rounded-lg bg-media text-muted; }
.cloud-thumbnail > img { @apply absolute inset-0 size-full object-cover; }
</style>
