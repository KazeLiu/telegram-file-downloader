<script setup lang="ts">
// 历史成绩弹窗：最近 30 局的详细记录 + 累计次数 + 集章，对齐参考站的记录面板。
import { computed, nextTick, ref } from 'vue'
import { clockTime } from '../playback'
import { difficultyLabels, formatClock } from './engine'
import {
  emptyTally, readRecords, readTally, recordEyebrows, recordLabels, recordOrder, recordTitles, recordTime, stamps,
  recordsStorageKey, recordsText, tallyFromStats, tallyStorageKey, writeRecords, writeTally,
  type ResultRecord
} from './records'
import { lostStorageKey, readLost, readStats, statsStorageKey } from './history'

const props = defineProps<{
  /** 打开那一刻从 localStorage 读到的记录（由父组件传入，改完写回） */
  open: boolean
}>()

const emit = defineEmits<{ close: [] }>()

const records = ref<ResultRecord[]>(readRecords(typeof localStorage === 'undefined' ? null : localStorage.getItem(recordsStorageKey)))
const tally = ref(readTally(typeof localStorage === 'undefined' ? null : localStorage.getItem(tallyStorageKey)))
reload()

const detail = ref<number | null>(null)
/** 二次确认的按钮组：none / clear / remove */
const asking = ref<'none' | 'clear' | 'remove'>('none')
const closeButton = ref<HTMLButtonElement>()

const current = computed(() => (detail.value === null ? null : records.value.find(item => item.t === detail.value) ?? null))
const breakdown = computed(() => recordOrder.filter(key => tally.value.r[key] > 0))

function reload() {
  if (typeof localStorage === 'undefined') return
  records.value = readRecords(localStorage.getItem(recordsStorageKey))
  tally.value = readTally(localStorage.getItem(tallyStorageKey))
  // 第一次用新结构：把旧版的成绩与「射了」记录折成累计次数，避免显示成 0 局。
  if (!tally.value.seeded && !tally.value.n) {
    const stats = readStats(localStorage.getItem(statsStorageKey))
    const lost = readLost(localStorage.getItem(lostStorageKey))
    const migrated = tallyFromStats(tally.value, stats.sessions, stats.success, stats.ruin, stats.fail, lost.count)
    if (migrated.n > 0) {
      tally.value = migrated
      writeTally(migrated)
    }
  }
}

function openDetail(t: number) {
  detail.value = t
  asking.value = 'none'
}

function backToList() {
  detail.value = null
  asking.value = 'none'
}

function removeOne() {
  const target = current.value
  if (!target) return
  records.value = records.value.filter(item => item.t !== target.t)
  writeRecords(records.value)
  detail.value = null
  asking.value = 'none'
}

function clearAll() {
  records.value = []
  tally.value = { ...emptyTally, r: { ...emptyTally.r }, seeded: true }
  writeRecords(records.value)
  writeTally(tally.value)
  detail.value = null
  asking.value = 'none'
}

function close() {
  emit('close')
}

defineExpose({ reload, closeButton })
</script>

<template>
  <div v-if="open" class="history-mask" data-sundome-history @click.self="close">
    <div class="history-sheet" role="dialog" aria-modal="true" aria-label="历史成绩">
      <div class="history-head">
        <button v-if="current" type="button" class="history-back" data-sundome-history-back @click="backToList">← {{ recordsText.back }}</button>
        <h2 v-else class="history-title">{{ recordsText.title }}</h2>
        <button ref="closeButton" type="button" class="history-close" data-sundome-history-close :aria-label="recordsText.close" @click="close">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true">
            <line x1="6" y1="6" x2="18" y2="18" />
            <line x1="18" y1="6" x2="6" y2="18" />
          </svg>
        </button>
      </div>

      <!-- 单条详情 -->
      <section v-if="current" class="history-detail" :data-sundome-history-detail="current.o">
        <p class="history-when" data-sundome-history-when>{{ recordTime(current.t) }}</p>
        <p class="history-eyebrow">{{ recordEyebrows[current.o] }}</p>
        <h3 class="history-detail-title">{{ recordTitles[current.o] }}</h3>
        <div class="history-stamps" :data-sundome-nth="current.n">
          <span class="history-nth">累计第 {{ current.n }} 次</span>
          <span class="history-stamp-dots" role="img" :aria-label="`集章 10 个中的第 ${stamps(current.n).index} 个`" :data-sundome-stamps="stamps(current.n).index">
            <span v-for="dot in 10" :key="dot" class="history-stamp" :class="{ 'history-stamp-on': dot <= stamps(current.n).index }" />
            <span v-if="stamps(current.n).sheets" class="history-stamp-more">+{{ stamps(current.n).sheets * 10 }}</span>
          </span>
          <span class="history-stamp-note">{{ recordsText.stampNote }}</span>
        </div>
        <dl class="history-grid">
          <div>
            <dt>{{ current.o === 'lost' ? '坚持时间' : '时间' }}</dt>
            <dd>{{ current.o === 'lost' ? formatClock(current.ms ?? 0) : `${current.m} 分钟` }}</dd>
          </div>
          <div>
            <dt>指令</dt>
            <dd>{{ current.c }} 次</dd>
          </div>
          <div>
            <dt>忍住</dt>
            <dd>{{ current.e }} 次</dd>
          </div>
          <div>
            <dt>难度</dt>
            <dd>{{ difficultyLabels[current.d] }}</dd>
          </div>
        </dl>
        <p v-if="current.x" class="history-extend" data-sundome-history-extend>加时 {{ current.x }} 次</p>
        <div class="history-remove-area">
          <div v-if="asking === 'remove'" class="history-ask" data-sundome-history-remove-ask>
            <span>{{ recordsText.removeAsk }}</span>
            <button type="button" class="history-danger" data-sundome-history-remove-yes @click="removeOne">{{ recordsText.removeYes }}</button>
            <button type="button" class="history-ghost" @click="asking = 'none'">{{ recordsText.cancel }}</button>
          </div>
          <button v-else type="button" class="history-link" data-sundome-history-remove @click="asking = 'remove'">{{ recordsText.remove }}</button>
        </div>
      </section>

      <!-- 列表 -->
      <template v-else>
        <div class="history-total" :data-sundome-history-total="tally.n">
          <p class="history-total-number">{{ recordsText.total }} {{ tally.n }} 次</p>
          <p v-if="breakdown.length" class="history-breakdown" data-sundome-history-breakdown>
            <span v-for="key in breakdown" :key="key" class="history-chip">{{ recordLabels[key] }} <b>{{ tally.r[key] }}</b></span>
          </p>
        </div>
        <p class="history-note">{{ recordsText.note }}</p>
        <p v-if="!records.length" class="history-empty" data-sundome-history-empty>{{ recordsText.empty }}</p>
        <ul v-else class="history-list" :data-sundome-history-list="records.length">
          <li v-for="item in records" :key="item.t">
            <button type="button" class="history-item" :data-sundome-history-item="item.o" :class="{ 'history-item-weak': item.o === 'lost' || item.o === 'fail' }" @click="openDetail(item.t)">
              <span class="history-item-main">
                <span class="history-item-when">{{ recordTime(item.t) }}<span v-if="item.n" class="history-item-nth">#{{ item.n }}</span></span>
                <span class="history-item-title">{{ recordTitles[item.o] }}</span>
                <span class="history-item-meta">
                  {{ item.o === 'lost' ? `${formatClock(item.ms ?? 0)} / ${item.m}分钟` : `${item.m}分钟` }}
                  · 忍住 {{ item.e }}次 · {{ difficultyLabels[item.d] }}<template v-if="item.x"> · 加时{{ item.x }}次</template>
                </span>
              </span>
              <span class="history-arrow" aria-hidden="true">→</span>
            </button>
          </li>
        </ul>
        <div class="history-clear-area">
          <div v-if="asking === 'clear'" class="history-ask" data-sundome-history-clear-ask>
            <span>{{ recordsText.clearAsk }}</span>
            <button type="button" class="history-danger" data-sundome-history-clear-yes @click="clearAll">
              {{ recordsText.clearYes }}
            </button>
            <button type="button" class="history-ghost" @click="asking = 'none'">{{ recordsText.cancel }}</button>
          </div>
          <button v-else type="button" class="history-link" data-sundome-history-clear @click="asking = 'clear'">
            {{ recordsText.clear }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.history-mask {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: flex;
  justify-content: center;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0;
  background: rgb(0 0 0 / 0.55);
}
.history-sheet {
  position: relative;
  width: 100%;
  max-width: 34rem;
  margin: 0;
  padding: 16px 16px 40px;
  background: var(--color-canvas);
  color: var(--color-ink);
}
.history-head {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  background: var(--color-canvas);
}
.history-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.history-back {
  padding: 0;
  min-height: 0;
  border: 0;
  background: none;
  color: var(--color-supporting);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}
.history-back:hover { color: var(--color-primary); }
.history-close {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  min-height: 0;
  padding: 0;
  border: 1px solid var(--color-hairline);
  border-radius: 999px;
  background: none;
  color: var(--color-supporting);
  cursor: pointer;
}
.history-close:hover { color: var(--color-ink); }
.history-total {
  margin: 8px 0 0;
  padding: 16px;
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-panel);
  background: var(--color-parchment);
}
.history-total-number {
  margin: 0;
  font-size: 26px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.history-breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--color-supporting);
}
.history-chip b { color: var(--color-ink); font-variant-numeric: tabular-nums; }
.history-note {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-muted);
}
.history-empty {
  margin: 16px 0 0;
  font-size: 14px;
  color: var(--color-supporting);
}
.history-list {
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}
.history-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-width: 0;
  min-height: 0;
  padding: 12px;
  border: 1px solid var(--color-selection);
  border-radius: 12px;
  background: var(--color-pearl);
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.history-item-weak { border-color: var(--color-hairline); }
.history-item:hover { border-color: var(--color-primary); }
.history-item-main { min-width: 0; flex: 1; display: grid; gap: 2px; }
.history-item-when {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}
.history-item-nth { color: var(--color-primary); }
.history-item-title { font-size: 14px; font-weight: 700; }
.history-item-meta {
  overflow: hidden;
  font-size: 12px;
  color: var(--color-supporting);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-arrow { flex: 0 0 auto; color: var(--color-primary); }
.history-detail {
  margin: 8px 0 0;
  padding: 20px;
  border: 1px solid var(--color-selection);
  border-radius: var(--radius-panel);
  background: var(--color-pearl);
}
.history-when {
  margin: 0;
  font-size: 12px;
  color: var(--color-supporting);
  font-variant-numeric: tabular-nums;
}
.history-eyebrow {
  margin: 8px 0 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: var(--color-primary);
}
.history-detail-title {
  margin: 4px 0 0;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.history-stamps {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  margin: 12px 0 0;
}
.history-nth { font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; }
.history-stamp-dots { display: flex; align-items: center; gap: 4px; }
.history-stamp {
  display: block;
  width: 12px;
  height: 12px;
  border: 1px solid var(--color-hairline);
  border-radius: 999px;
  background: var(--color-soft);
}
.history-stamp-on { border-color: var(--color-primary); background: var(--color-primary); }
.history-stamp-more { margin-left: 4px; font-size: 12px; font-weight: 700; color: var(--color-muted); font-variant-numeric: tabular-nums; }
.history-stamp-note { flex-basis: 100%; font-size: 12px; color: var(--color-muted); }
.history-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 16px 0 0;
  text-align: center;
}
.history-grid > div {
  padding: 10px 4px;
  border-radius: 12px;
  background: var(--color-soft);
}
.history-grid dt {
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--color-muted);
}
.history-grid dd {
  margin: 4px 0 0;
  font-size: 18px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.history-extend { margin: 12px 0 0; font-size: 12px; color: var(--color-primary); }
.history-remove-area,
.history-clear-area {
  margin: 16px 0 0;
  padding-top: 12px;
  border-top: 1px solid var(--color-hairline);
}
.history-ask {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
.history-ask > span { flex-basis: 100%; }
.history-danger {
  min-height: 0;
  padding: 8px 16px;
  border: 0;
  border-radius: 12px;
  background: var(--color-danger);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}
.history-ghost {
  min-height: 0;
  padding: 8px 16px;
  border: 1px solid var(--color-hairline);
  border-radius: 12px;
  background: none;
  color: var(--color-supporting);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}
.history-link {
  min-height: 0;
  padding: 0;
  border: 0;
  background: none;
  color: var(--color-muted);
  font-size: 12px;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}
.history-link:hover { color: var(--color-primary); }

@media (min-width: 640px) {
  .history-mask { padding: 32px 0; }
  .history-sheet { padding: 16px 24px 40px; border-radius: 16px; }
}
</style>
