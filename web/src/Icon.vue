<script setup lang="ts">
defineProps<{ name: string; size?: number }>()
const paths: Record<string, string> = {
  inbox: 'M4 4h16v16H4z M4 14h5l2 3h2l2-3h5 M12 3v8 M9 8l3 3 3-3',
  overview: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  history: 'M3 11a9 9 0 1 1 2 7 M3 4v7h7 M12 7v5l3 2',
  settings: 'M4 7h16 M4 17h16 M8 4v6 M16 14v6',
  arrow: 'M5 12h14 M14 7l5 5-5 5',
  down: 'M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5',
  folder: 'M3 7V4h6l3 3h9v13H3z',
  file: 'M5 3h9l5 5v13H5z M14 3v6h5 M9 14h6 M9 17h4',
  archive: 'M5 3h14v18H5z M11 3v3h2v3h-2v3h2v3 M10 16h4v3h-4z',
  video: 'M3 5h14v14H3z M17 10l4-3v10l-4-3',
  photo: 'M3 3h18v18H3z M3 17l6-6 4 4 3-3 5 5 M15 7h.01',
  check: 'M5 12l4 4L19 6',
  close: 'M6 6l12 12 M6 18L18 6',
  lock: 'M6 10h12v11H6z M8 10V6a4 4 0 0 1 8 0v4',
  telegram: 'M21 3L3 10l7 3 3 7 8-17 M10 13L21 3',
  pause: 'M8 5v14 M16 5v14',
  play: 'M7 4l13 8-13 8z',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16 M17 17l5 5',
  logout: 'M10 4H4v16h6 M10 12h11 M16 7l5 5-5 5',
  chevron: 'M9 5l7 7-7 7',
  refresh: 'M20 7a9 9 0 1 0 1 9 M20 2v6h-6',
  loader: 'M21 12a9 9 0 1 1-9-9',
  sketch: 'M4 20l4-1 12-12-3-3L5 16z M14 7l3 3 M3 22h18',
  restore: 'M4 10a8 8 0 1 1 1 9 M4 4v6h6 M12 8v5l3 2',
  workflow: 'M3 4h6v6H3z M15 14h6v6h-6z M9 7h6a3 3 0 0 1 3 3v4 M6 10v7h9',
  cloud: 'M6 18h12a4 4 0 0 0 0-8 6 6 0 0 0-11-2 5 5 0 0 0-1 10',
  trash: 'M4 6h16 M9 6V3h6v3 M6 6l1 15h10l1-15 M10 10v7 M14 10v7',
  compare: 'M3 3h12v12H3z M9 15v6h12V9h-6 M3 12l4-4 5 5 M10 6h.01 M14 17l3-3 4 4',
}
</script>
<template><svg :width="size || 20" :height="size || 20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.file" /></svg></template>
