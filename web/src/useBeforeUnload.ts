import { onMounted, watch } from 'vue'

export function useBeforeUnload(pending: () => boolean) {
  onMounted(() => {
    watch(pending, (warn, _, onCleanup) => {
      if (!warn) return
      const beforeUnload = (event: BeforeUnloadEvent) => {
        event.preventDefault()
        event.returnValue = true
      }
      window.addEventListener('beforeunload', beforeUnload)
      onCleanup(() => window.removeEventListener('beforeunload', beforeUnload))
    }, { immediate: true, flush: 'sync' })
  })
}
