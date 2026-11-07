import assert from 'node:assert/strict'
import { createRenderer, ref } from 'vue'
import { useBeforeUnload } from '../src/useBeforeUnload.ts'

globalThis.window = new EventTarget() as unknown as Window & typeof globalThis
const renderer = createRenderer({
  createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  parentNode: () => null, nextSibling: () => null,
  insert() {}, remove() {}, setText() {}, setElementText() {}, patchProp() {},
})
const organizing = ref(false)
const count = ref(0)
const app = renderer.createApp({
  setup() {
    useBeforeUnload(() => organizing.value && count.value > 0)
    return () => null
  },
})
app.mount({})
const canLeave = () => window.dispatchEvent(new Event('beforeunload', { cancelable: true }))
assert.equal(canLeave(), true)
organizing.value = true
assert.equal(canLeave(), true)
count.value = 1
assert.equal(canLeave(), false)
count.value = 2
assert.equal(canLeave(), false)
count.value = 0
assert.equal(canLeave(), true)
count.value = 1
organizing.value = false
assert.equal(canLeave(), true)
organizing.value = true
assert.equal(canLeave(), false)
app.unmount()
assert.equal(canLeave(), true)
