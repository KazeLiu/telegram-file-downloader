<script setup lang="ts">
import { ref, watch } from 'vue'
import Icon from './Icon.vue'
import type { CloudMedia } from './xiaomiMedia'

const props = defineProps<{ item: CloudMedia }>()
const broken = ref(false)
watch(() => props.item, () => { broken.value = false })
</script>

<template>
  <span class="relative grid aspect-square w-full place-items-center overflow-hidden rounded-lg bg-soft text-muted">
    <img v-if="item.thumbnail && !broken" :src="item.thumbnail" alt="" loading="lazy" decoding="async" class="absolute inset-0 size-full object-cover" @error="broken = true" />
    <Icon v-else :name="item.kind === 'video' ? 'video' : 'photo'" :size="22" />
    <span v-if="item.kind === 'video' && item.thumbnail && !broken" class="absolute right-1 bottom-1 rounded bg-ink/70 p-1 text-white"><Icon name="video" :size="13" /></span>
  </span>
</template>
