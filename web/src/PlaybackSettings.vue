<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { newPlaylist } from './playback'
import type { Playlist } from './playback'
import { settingsSummary } from './playback/summary'
import {
  adjustMix, beatVolumeMax, brightnessMin, categoryHints, categoryLabels, categoryOrder,
  customCommandLimit, customCommandTextLimit, difficultyHints, difficultyLabels, difficultyOrder,
  durationMax, durationMin, finaleHints, finaleLabels, finaleOrder, instructionLengthLabels,
  instructionLengthOrder, mixOf, modeLabels, modeOrder, presets, presetLabels, presetOrder,
  redBeatLabels, redBeatOrder, restFixedChoices, restModeLabels, restModeOrder, restRangeChoices,
  rewardChoices, toneAfterLabels, toneAfterOrder, difficulties, permitRate,
  toneLabels, toneOrder,
  type Difficulty, type EdgeMode,
} from './playback/engine'
import { maleCommands } from './playback/commands'
import { defaultEdgeSettings, readEdgeSettings } from './playback/settings'
import { toneNotes } from './playback/tones'
import type { EdgeSettings } from './playback/settings'

const settings = defineModel<EdgeSettings>({ required: true })
const props = defineProps<{ runtime?: boolean; media?: Playlist }>()

const selected = ref('play')
const search = ref('')
// 分组顺序对齐参考站：玩法 / 指令 / 视频·图片 / 声音 / 其他。
const groups = computed(() => [
  { id: 'play', label: '玩法', keywords: '推荐 第一次 标准 慢慢来 时间 分钟 随机 难度 简单 普通 困难 地狱 许可率 自己调 混合 可以撸 慢慢来 不许碰 结局 抽签 必定 松手 连续 加时 允许射精 秒 等待 随机 固定 指令时长 较长 很长 乳头 龟头' },
  { id: 'command', label: '指令', keywords: '分类 寸止 挑逗 姿势 羞耻 轻度疼痛 惯用手 左右手 自定义 口令 启停 禁用 口吻 强势 挑逗 羞辱 温柔 足控 短句' },
  { id: 'media', label: '视频·图片', keywords: '视频 图片 混合 仅图片 仅视频 顺序 随机 文件名 每轮 数量 间隔 切图 BPM 循环 喜欢 收藏' },
  { id: 'sound', label: '声音', keywords: '节拍 音量 心跳 红 媒体 视频 音量 变暗 混音' },
  { id: 'other', label: '其他', keywords: '隐藏 剩余 时间 进度 画面 亮度 变暗 混音' },
])
const visible = computed(() => groups.value.filter(group => (search.value.trim()
  ? `${group.label} ${group.keywords}`.toLowerCase().includes(search.value.trim().toLowerCase())
  : group.id === selected.value) && !(props.runtime && group.id === 'media')))
const summary = computed(() => settingsSummary(settings.value))
const activeTones = computed(() => toneOrder.filter(key => settings.value.tones[key]))

function selectGroup(id: string) {
  selected.value = id
  search.value = ''
  resetArmed.value = false
}

// 「恢复本组」要求再点一次确认，避免误触清掉还没记住的设置。
const resetArmed = ref(false)
const canReset = computed(() => !search.value.trim() && visible.value.length === 1)
const resetLabel = computed(() => resetArmed.value ? '确认恢复？' : '恢复本组')
watch([selected, search], () => { resetArmed.value = false })
watch(settings, () => { resetArmed.value = false }, { deep: true })
function resetGroup() {
  if (!resetArmed.value) { resetArmed.value = true; return }
  resetArmed.value = false
  draftCommand.value = ''
  const item = settings.value
  const base = defaultEdgeSettings
  if (selected.value === 'play') {
    item.minutes = base.minutes
    item.durationRandom = base.durationRandom
    item.difficulty = base.difficulty
    item.instructionLength = base.instructionLength
    item.finale = base.finale
    item.tune = { chance: null, stop: null, mix: null }
    item.allowRuin = base.allowRuin
    item.overtimeRounds = base.overtimeRounds
    item.rewardSeconds = base.rewardSeconds
    item.rest = { ...base.rest }
    item.nipple = { ...base.nipple }
    item.glans = { ...base.glans }
  } else if (selected.value === 'command') {
    item.categories = { ...base.categories }
    item.hand = base.hand
    item.custom.splice(0, item.custom.length)
    item.disabled.splice(0, item.disabled.length)
    item.tones = { ...base.tones }
    item.toneLine = { ...base.toneLine }
  } else if (selected.value === 'media') {
    const defaults = newPlaylist()
    const media = props.media
    if (media) {
      media.order = defaults.order
      media.imageCount = defaults.imageCount
      media.imageTiming = defaults.imageTiming
      media.imageSeconds = defaults.imageSeconds
      media.bpm = defaults.bpm
      media.loop = defaults.loop
      media.favoritesOnly = defaults.favoritesOnly
    }
    item.keepVideoOnStop = base.keepVideoOnStop
    item.switchVideoPerCommand = base.switchVideoPerCommand
  } else if (selected.value === 'sound') {
    item.metronome = base.metronome
    item.beatVolume = base.beatVolume
    item.redBeat = base.redBeat
    item.heartbeat = base.heartbeat
    item.heartbeatVolume = base.heartbeatVolume
    item.mediaVolume = base.mediaVolume
  } else {
    item.hideRemaining = base.hideRemaining
    item.brightness = base.brightness
    item.mixAudio = base.mixAudio
  }
}

// 推荐预设：只覆盖时长/难度/结局与三类开关，微调值（tune）一并归零，与参考站一致。
function applyPreset(key: keyof typeof presets) {
  const preset = presets[key]
  const item = settings.value
  item.minutes = preset.minutes
  item.durationRandom = false
  item.difficulty = preset.difficulty
  item.finale = preset.finale
  Object.assign(item.categories, preset.categories)
  item.tune = { chance: null, stop: null, mix: null }
}

// 自己调：滑杆直接写 tune；「恢复成难度的数值」把三项清空回落到难度预设。
const mix = computed(() => mixOf(settings.value.difficulty, settings.value.tune))
const chancePercent = computed(() => settings.value.tune.chance ?? Math.round(difficulties[settings.value.difficulty].chance * 100))
function setChance(value: number) { settings.value.tune.chance = Math.round(value) }
function setMix(mode: EdgeMode, value: number) {
  settings.value.tune.mix = adjustMix({ ...mix.value }, mode, Math.round(value))
}
function restoreTune() { settings.value.tune = { chance: null, stop: null, mix: null } }
const derivedMix = computed(() => mixOf(settings.value.difficulty, { chance: null, stop: null, mix: null }))

const timeChoices = computed(() => [3, 5, 10, 15, 20, 30])
function setMinutes(value: number) {
  settings.value.minutes = Math.min(durationMax, Math.max(durationMin, Math.round(value)))
  settings.value.durationRandom = false
}
// 等待时长：预设档改写上下限，数字输入在提交时夹取。
function setRestRange(value: [number, number]) {
  settings.value.rest.min = value[0]
  settings.value.rest.max = value[1]
}
function clampRest(raw: number) {
  const value = Number.isFinite(raw) ? Math.round(raw) : 8
  return Math.min(120, Math.max(3, value))
}
function syncRestMin() {
  const value = clampRest(settings.value.rest.min)
  settings.value.rest.min = value
  if (settings.value.rest.max < value) settings.value.rest.max = value
}
function syncRestMax() {
  const value = clampRest(settings.value.rest.max)
  settings.value.rest.max = Math.max(value, settings.value.rest.min)
}
function syncRestFixed() {
  const value = clampRest(settings.value.rest.seconds)
  settings.value.rest.seconds = value
}

// 指令分类：只抽选中的分类（傲气/道具类始终启用）。
function toggleCategory(key: keyof EdgeSettings['categories']) {
  settings.value.categories[key] = !settings.value.categories[key]
}

// 自定义口令：上限 30 条、单条 60 字。
const draftCommand = ref('')
const draftMode = ref<EdgeMode>('go')
const canAddCommand = computed(() => !!draftCommand.value.trim() && settings.value.custom.length < customCommandLimit)
function addCommand() {
  const text = draftCommand.value.trim().slice(0, customCommandTextLimit)
  if (!text || settings.value.custom.length >= customCommandLimit) return
  settings.value.custom.push({ text, mode: draftMode.value })
  draftCommand.value = ''
}
function removeCommand(index: number) {
  settings.value.custom.splice(index, 1)
}

// 逐条启停内置口令：存的是停用下标，点一处在启用/停用间切换。
const commandGroups = computed(() => modeOrder.map(mode => ({
  mode,
  label: modeLabels[mode],
  items: maleCommands.map((command, index) => ({ index, command })).filter(item => item.command.mode === mode),
})))
function toggleCommand(index: number) {
  const at = settings.value.disabled.indexOf(index)
  if (at >= 0) settings.value.disabled.splice(at, 1)
  else settings.value.disabled.push(index)
}
function enableAllCommands() { settings.value.disabled.splice(0) }

// 视频·图片组只在不播放时出现：播放中改图库/顺序需要重新取队列，必须回列表。
const media = computed(() => props.media)
const beatsImages = computed(() => !!media.value && media.value.kind === 'image' && media.value.imageTiming === 'beat')
const secondsLabel = computed(() => readEdgeSettings(null) ? '' : '')
void secondsLabel
</script>

<template>
  <div class="settings-card" :class="{ runtime }">
    <header class="card-head">
      <div class="card-heading">
        <h3 class="card-title">玩法设置</h3>
        <p class="card-summary">{{ summary }}</p>
      </div>
      <button v-if="canReset" type="button" class="text-button card-reset" :title="resetArmed ? '再点一次把本组恢复为默认值' : '只把本组恢复为默认值，其他分组不变'" @click="resetGroup">{{ resetLabel }}</button>
    </header>
    <label class="settings-search">查找设置<input v-model="search" type="search" placeholder="例如：乳头、左手、速度、视频" /></label>
    <div class="settings-tabs" role="group" aria-label="设置分类">
      <button v-for="group in groups" :key="group.id" type="button" :aria-pressed="!search && selected === group.id" @click="selectGroup(group.id)">{{ group.label }}</button>
    </div>
    <p v-if="!visible.length" class="muted" role="status">没有匹配的设置，请换个关键词。</p>
    <section v-for="group in visible" :key="group.id" class="settings-section" :aria-label="`${group.label}设置`">
      <h4 v-if="search" class="section-title">{{ group.label }}</h4>

      <template v-if="group.id === 'play'">
        <h5 class="field-label">推荐</h5>
        <div class="chips">
          <button v-for="key in presetOrder" :key="key" type="button" class="chip" :aria-pressed="settings.minutes === presets[key].minutes && settings.difficulty === presets[key].difficulty && settings.finale === presets[key].finale" @click="applyPreset(key)">{{ presetLabels[key] }}</button>
        </div>
        <p class="muted">点一下换一套推荐组合：{{ presetLabels.first }} = 5 分钟·简单·必定允许；{{ presetLabels.standard }} = 10 分钟·普通·抽签；{{ presetLabels.long }} = 20 分钟·困难·抽签。</p>

        <h5 class="field-label">只玩乳头 / 只玩龟头</h5>
        <div class="settings-grid">
          <label class="toggle"><input :checked="settings.nipple.on" type="checkbox" @change="settings.nipple.on = ($event.target as HTMLInputElement).checked" />只玩乳头</label>
          <label v-if="settings.nipple.on">插入段数<input :value="settings.nipple.times" type="number" min="1" max="4" @change="settings.nipple.times = Math.min(4, Math.max(1, Math.round(Number(($event.target as HTMLInputElement).value) || 1)))" /></label>
          <label class="toggle"><input :checked="settings.glans.on" type="checkbox" @change="settings.glans.on = ($event.target as HTMLInputElement).checked" />只玩龟头</label>
          <label v-if="settings.glans.on">插入段数<input :value="settings.glans.times" type="number" min="1" max="4" @change="settings.glans.times = Math.min(4, Math.max(1, Math.round(Number(($event.target as HTMLInputElement).value) || 1)))" /></label>
        </div>

        <h5 class="field-label">时间</h5>
        <div class="chips">
          <button v-for="value in timeChoices" :key="value" type="button" class="chip" :aria-pressed="!settings.durationRandom && settings.minutes === value" @click="setMinutes(value)">{{ value }} 分钟</button>
          <button type="button" class="chip" :aria-pressed="settings.durationRandom" @click="settings.durationRandom = true; settings.minutes = 5 + Math.floor(Math.random() * 16)">随机</button>
        </div>
        <div class="settings-grid">
          <label>自定义时长（分钟，{{ durationMin }}–{{ durationMax }}）<input :value="settings.minutes" type="number" :min="durationMin" :max="durationMax" @change="setMinutes(Number(($event.target as HTMLInputElement).value))" /></label>
          <span class="hint-cell muted">随机时长在 5～20 分钟之间，且播放时不显示剩余时间。</span>
        </div>

        <h5 class="field-label">难度</h5>
        <div class="chips">
          <button v-for="key in difficultyOrder" :key="key" type="button" class="chip" :aria-pressed="settings.difficulty === key" @click="settings.difficulty = key as Difficulty">{{ difficultyLabels[key] }}</button>
        </div>
        <p class="muted">{{ difficultyHints[settings.difficulty] }}</p>

        <details class="fold">
          <summary>自己调（许可概率 {{ chancePercent }}% · 可以撸 {{ mix.go }}% · 慢慢来 {{ mix.slow }}% · 不许碰 {{ mix.stop }}%）</summary>
          <div class="settings-grid">
            <label>许可概率 {{ chancePercent }}%<input :value="chancePercent" type="range" min="10" max="100" step="5" @input="setChance(Number(($event.target as HTMLInputElement).value))" /></label>
            <label>可以撸 {{ mix.go }}%<input :value="mix.go" type="range" min="0" max="100" step="5" @input="setMix('go', Number(($event.target as HTMLInputElement).value))" /></label>
            <label>慢慢来 {{ mix.slow }}%<input :value="mix.slow" type="range" min="0" max="100" step="5" @input="setMix('slow', Number(($event.target as HTMLInputElement).value))" /></label>
            <label>不许碰 {{ mix.stop }}%<input :value="mix.stop" type="range" min="0" max="60" step="5" @input="setMix('stop', Number(($event.target as HTMLInputElement).value))" /></label>
          </div>
          <p class="muted">三项合计 100%；难度默认是 {{ derivedMix.go }} / {{ derivedMix.slow }} / {{ derivedMix.stop }}。不许碰占比超过 45% 时会允许「不许碰」连续出现。</p>
          <button type="button" class="text-button" @click="restoreTune">恢复成难度的数值</button>
        </details>

        <h5 class="field-label">结局</h5>
        <div class="chips">
          <button v-for="key in finaleOrder" :key="key" type="button" class="chip" :aria-pressed="settings.finale === key" @click="settings.finale = key">{{ finaleLabels[key] }}</button>
        </div>
        <p class="muted">{{ finaleHints[settings.finale] }}</p>
        <label class="toggle"><input :checked="settings.allowRuin" type="checkbox" @change="settings.allowRuin = ($event.target as HTMLInputElement).checked" />落选时以「松手射精」结束</label>

        <h5 class="field-label">允许射精的时间 / 忍住后等待</h5>
        <div class="settings-grid">
          <label>允许射精的时间（秒）<select :value="settings.rewardSeconds" @change="settings.rewardSeconds = Number(($event.target as HTMLSelectElement).value)">
            <option v-for="value in rewardChoices" :key="value" :value="value">{{ value }} 秒</option>
          </select></label>
          <label>等待模式<select :value="settings.rest.mode" @change="settings.rest.mode = ($event.target as HTMLSelectElement).value as 'random'">
            <option v-for="key in restModeOrder" :key="key" :value="key">{{ restModeLabels[key] }}</option>
          </select></label>
        </div>
        <div v-if="settings.rest.mode === 'random'" class="settings-grid">
          <label>等待区间<select :value="`${settings.rest.min}-${settings.rest.max}`" @change="setRestRange(restRangeChoices.find(item => `${item[0]}-${item[1]}` === ($event.target as HTMLSelectElement).value) ?? [8, 16])">
            <option v-for="item in restRangeChoices" :key="item.join('-')" :value="`${item[0]}-${item[1]}`">{{ item[0] }}～{{ item[1] }} 秒</option>
          </select></label>
          <span class="hint-cell muted">选预设会同时改写下面两个数字，也可以直接改。</span>
          <label>最短等待（秒）<input :value="settings.rest.min" type="number" min="3" max="120" @change="settings.rest.min = Number(($event.target as HTMLInputElement).value); syncRestMin()" /></label>
          <label>最长等待（秒）<input :value="settings.rest.max" type="number" min="3" max="120" @change="settings.rest.max = Number(($event.target as HTMLInputElement).value); syncRestMax()" /></label>
        </div>
        <div v-else class="settings-grid">
          <label>固定等待（秒）<select :value="settings.rest.seconds" @change="settings.rest.seconds = Number(($event.target as HTMLSelectElement).value); syncRestFixed()">
            <option v-for="value in restFixedChoices" :key="value" :value="value">{{ value }} 秒</option>
          </select></label>
        </div>
        <p class="muted">按下「忍住了」之后进入红色，等这段时长过去再回到循环。</p>

        <label>指令时长<select :value="settings.instructionLength" @change="settings.instructionLength = ($event.target as HTMLSelectElement).value as 'standard'">
          <option v-for="key in instructionLengthOrder" :key="key" :value="key">{{ instructionLengthLabels[key] }}</option>
        </select></label>
        <p class="muted">撸的指令会持续更久。红色（不许碰）、写明秒数的指令和整局结束时间不会改变。</p>

        <ul class="play-legend">
          <li><span class="legend-dot" style="background: #5ee3a1" />屏幕是绿色时可以撸。手跟着光和声音的节拍</li>
          <li><span class="legend-dot" style="background: #f0c35a" />黄色是放慢、挑逗</li>
          <li><span class="legend-dot" style="background: #ff6b7d" />变红就松手。结束前不许碰</li>
          <li v-if="settings.nipple.on"><span class="legend-dot" style="background: #ff6b7d" />只玩乳头</li>
          <li v-if="settings.glans.on"><span class="legend-dot" style="background: #f0c35a" />只玩龟头</li>
        </ul>
        <p class="play-rules">
          时间到之前射了就输。忍住了就按「忍住了」（每次最后的许可率 +5%）。拿到许可后要在
          {{ settings.rewardSeconds }} 秒内射出来。当前设置的许可率从
          {{ Math.round(permitRate(settings.difficulty, 0, settings.tune.chance) * 100) }}% 起。
        </p>
      </template>

      <template v-else-if="group.id === 'command'">
        <h5 class="field-label">指令类型（可多选）</h5>
        <div class="chips">
          <button v-for="key in categoryOrder" :key="key" type="button" class="chip" :aria-pressed="settings.categories[key]" @click="toggleCategory(key)">{{ categoryLabels[key] }}</button>
        </div>
        <p class="muted">{{ categoryHints.edge }}；{{ categoryHints.tease }}；{{ categoryHints.pose }}；{{ categoryHints.pain }}。关掉的类型不会再被抽到。</p>

        <div class="settings-grid">
          <label>惯用手<select :value="settings.hand" @change="settings.hand = ($event.target as HTMLSelectElement).value as 'right'">
            <option value="right">右手</option>
            <option value="left">左手</option>
          </select></label>
        </div>
        <p class="muted">选左手时，指令里的左右手会自动对调。</p>

        <h5 class="field-label">口吻</h5>
        <p class="muted">开启后会在指令前后各加一句同口吻的短句；“强势”是命令式，“挑逗”是一边调侃一边撩你，“羞辱”会出现很重的话，“温柔”像恋人在旁边陪着，“足控”只有话语、指令不变。同时开两种以上时，每条指令轮流使用。</p>
        <div class="chips">
          <button v-for="key in toneOrder" :key="key" type="button" class="chip" :aria-pressed="settings.tones[key]" @click="settings.tones[key] = !settings.tones[key]">{{ toneLabels[key] }}</button>
        </div>
        <div v-if="activeTones.length" class="tone-tuning">
          <p class="muted">{{ activeTones.map(key => `${toneLabels[key]}：${toneNotes[key]}`).join('　') }}</p>
          <label class="toggle"><input :checked="settings.toneLine.show" type="checkbox" @change="settings.toneLine.show = ($event.target as HTMLInputElement).checked" />显示在屏幕上</label>
          <label class="toggle"><input :checked="settings.toneLine.before" type="checkbox" @change="settings.toneLine.before = ($event.target as HTMLInputElement).checked" />放在指令前</label>
          <div class="settings-grid">
            <label>放在指令后<select :value="settings.toneLine.after" @change="settings.toneLine.after = ($event.target as HTMLSelectElement).value as 'never'">
              <option v-for="key in toneAfterOrder" :key="key" :value="key">{{ toneAfterLabels[key] }}</option>
            </select></label>
          </div>
          <p class="muted">指令类型是「寸止指令」时不会加后置短句，避免把“松手”冲淡。</p>
        </div>

        <h5 class="field-label">自定义口令（{{ settings.custom.length }}/{{ customCommandLimit }}）</h5>
        <div class="command-form">
          <label>口令内容<input v-model="draftCommand" type="text" :maxlength="customCommandTextLimit" placeholder="例如：停三秒再继续" @keydown.enter.prevent="addCommand" /></label>
          <label>类型<select v-model="draftMode">
            <option v-for="key in modeOrder" :key="key" :value="key">{{ modeLabels[key] }}</option>
          </select></label>
          <button type="button" class="secondary" :disabled="!canAddCommand" @click="addCommand">添加</button>
        </div>
        <p v-if="settings.custom.length >= customCommandLimit" class="muted">已到 {{ customCommandLimit }} 条上限，删掉一条再添加。</p>
        <p v-else class="muted">单条最多 {{ customCommandTextLimit }} 字；要改就删掉重新添加。</p>
        <ul v-if="settings.custom.length" class="command-list">
          <li v-for="(item, index) in settings.custom" :key="`${item.text}-${index}`">
            <small class="badge">{{ modeLabels[item.mode] }}</small>
            <span>{{ item.text }}</span>
            <button type="button" class="text-button" @click="removeCommand(index)">删除</button>
          </li>
        </ul>

        <details class="fold">
          <summary>逐条启停内置口令（已停用 {{ settings.disabled.length }} 条）</summary>
          <p class="muted">亮着表示启用，点一下停用；停用的口令不会再被抽到。</p>
          <div v-for="commandGroup in commandGroups" :key="commandGroup.mode" class="command-group">
            <h6 class="command-group-title">{{ commandGroup.label }}（{{ commandGroup.items.length }} 条）</h6>
            <div class="chips">
              <button v-for="item in commandGroup.items" :key="item.index" type="button" class="chip" :aria-pressed="!settings.disabled.includes(item.index)" @click="toggleCommand(item.index)">{{ item.command.text }}</button>
            </div>
          </div>
          <button v-if="settings.disabled.length" type="button" class="text-button" @click="enableAllCommands">全部启用</button>
        </details>
      </template>

      <template v-else-if="group.id === 'media'">
        <template v-if="media">
          <div class="settings-grid">
            <label>内容类型<select v-model="media.kind">
              <option value="mixed">混合内容</option>
              <option value="image">仅图片</option>
              <option value="video">仅视频</option>
            </select></label>
            <label>播放顺序<select v-model="media.order">
              <option value="shuffle">随机</option>
              <option value="sequential">文件名顺序</option>
            </select></label>
            <label v-if="media.kind !== 'video'">每轮图片数（0 为全部）<input v-model.number="media.imageCount" type="number" min="0" max="100000" required /></label>
            <label v-if="media.kind === 'image'">图片切换<select v-model="media.imageTiming">
              <option value="time">按时间</option>
              <option value="beat">按 BPM · 每拍一张</option>
            </select></label>
            <label v-if="media.kind !== 'video' && (media.kind !== 'image' || media.imageTiming === 'time')">图片间隔（秒）<input v-model.number="media.imageSeconds" type="number" min="1" max="300" required /></label>
            <label>节拍上限（BPM）<input v-model.number="media.bpm" type="number" min="20" max="300" required /></label>
          </div>
          <p v-if="beatsImages" class="muted">每拍发声并切一张；慢速为快速的 60%，红色时不发声、不自动切图。</p>
          <label class="toggle"><input v-model="media.loop" type="checkbox" />循环列表</label>
          <label class="toggle"><input v-model="media.favoritesOnly" type="checkbox" />仅播放喜欢</label>
          <label class="toggle"><input :checked="settings.keepVideoOnStop" type="checkbox" @change="settings.keepVideoOnStop = ($event.target as HTMLInputElement).checked" />红色（不许碰）时也继续播放视频</label>
          <p class="muted">开＝红色指令时视频不暂停、不变暗。关＝红色时暂停并变暗（和以前一样）。</p>
          <label class="toggle"><input :checked="settings.switchVideoPerCommand" type="checkbox" @change="settings.switchVideoPerCommand = ($event.target as HTMLInputElement).checked" />每换一条指令就换一个视频</label>
          <p class="muted">开＝每换一条指令就切到下一个视频。关＝一个视频播完再换（和以前一样）。</p>
          <p class="muted">指令自带的手速（BPM）优先，这里只是上限与切图节拍。已展示图片不再入选。</p>
        </template>
        <p v-else class="muted">先选一个播放列表。</p>
      </template>

      <template v-else-if="group.id === 'sound'">
        <label class="toggle"><input :checked="settings.metronome" type="checkbox" @change="settings.metronome = ($event.target as HTMLInputElement).checked" />节拍声</label>
        <div class="settings-grid">
          <label>节拍音量 · {{ settings.beatVolume }}%<input :value="settings.beatVolume" type="range" min="0" :max="beatVolumeMax" step="5" @input="settings.beatVolume = Number(($event.target as HTMLInputElement).value)" /></label>
          <label v-if="media?.kind !== 'image'">视频音量 · {{ settings.mediaVolume }}%<input :value="settings.mediaVolume" type="range" min="0" max="100" step="5" @input="settings.mediaVolume = Number(($event.target as HTMLInputElement).value)" /></label>
        </div>
        <p class="muted">节拍音量最高 {{ beatVolumeMax }}%，比默认响得多；觉得吵就往下拉。</p>
        <label class="toggle"><input :checked="settings.heartbeat" type="checkbox" @change="settings.heartbeat = ($event.target as HTMLInputElement).checked" />心跳声</label>
        <div v-if="settings.heartbeat" class="settings-grid">
          <label>心跳音量 · {{ settings.heartbeatVolume }}%<input :value="settings.heartbeatVolume" type="range" min="0" :max="beatVolumeMax" step="5" @input="settings.heartbeatVolume = Number(($event.target as HTMLInputElement).value)" /></label>
          <label>红色时<select :value="settings.redBeat" @change="settings.redBeat = ($event.target as HTMLSelectElement).value as 'heartbeat'">
            <option v-for="key in redBeatOrder" :key="key" :value="key">{{ redBeatLabels[key] }}</option>
          </select></label>
        </div>
        <p class="muted">全部是浏览器实时合成的音，不加载任何音频文件。</p>
      </template>

      <template v-else>
        <label class="toggle"><input :checked="settings.hideRemaining" type="checkbox" @change="settings.hideRemaining = ($event.target as HTMLInputElement).checked" />隐藏剩余时间与进度</label>
        <label>视频变暗 · {{ settings.brightness }}%<input :value="settings.brightness" type="range" :min="brightnessMin" max="100" step="5" @input="settings.brightness = Number(($event.target as HTMLInputElement).value)" /></label>
        <p class="muted">{{ brightnessMin }}% 最暗，100% ＝ 完全透明不变暗；只影响播放器画面，不改原文件。</p>
        <label class="toggle"><input :checked="settings.mixAudio" type="checkbox" @change="settings.mixAudio = ($event.target as HTMLInputElement).checked" />边听音乐边玩</label>
        <p class="muted">打开后播放器不会抢占系统的音频焦点。</p>
      </template>
    </section>
  </div>
</template>

<style scoped>
.settings-card { padding: 20px 22px; border: 1px solid var(--color-hairline); border-radius: var(--radius-panel); background: var(--color-canvas); }
.settings-card.runtime { background: var(--color-parchment); }
.card-head { display: flex; align-items: start; justify-content: space-between; gap: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--color-hairline); }
.card-heading { display: grid; gap: 6px; min-width: 0; }
.card-title { margin: 0; font-size: 20px; line-height: 1.4; }
.card-summary { margin: 0; font-size: 14px; line-height: 1.6; color: var(--color-muted); overflow-wrap: anywhere; }
.card-reset { flex-shrink: 0; min-height: 44px; font-size: 14px; }
.settings-search { max-width: 440px; margin-top: 18px; font-size: 14px; }
.settings-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 20px; }
.settings-tabs button { min-height: 44px; padding: 8px 20px; border-radius: 999px; border: 1px solid var(--color-hairline); background: var(--color-pearl); }
.settings-tabs button[aria-pressed="true"] { background: var(--color-selection); border-color: var(--color-primary); color: var(--color-primary); font-weight: 600; }
.settings-section + .settings-section { margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--color-hairline); }
.section-title { margin: 0 0 16px; font-size: 16px; color: var(--color-muted); }
.settings-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.toggle { display: flex; flex-direction: row; align-items: center; gap: 10px; min-height: 44px; margin-block: 12px; }
.settings-section p { margin-top: 12px; font-size: 14px; line-height: 1.6; }
input[type="range"] { padding: 0; min-height: 44px; accent-color: var(--color-primary); }
.tone-tuning { margin-top: 4px; }
.field-label { margin: 16px 0 10px; font-size: 14px; font-weight: 600; color: var(--color-supporting); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-block: 4px 0; }
.chip { min-height: 38px; padding: 6px 14px; border-radius: 999px; border: 1px solid var(--color-hairline); background: var(--color-pearl); font-size: 14px; line-height: 1.4; }
.chip[aria-pressed="true"] { background: var(--color-selection); border-color: var(--color-primary); color: var(--color-primary); font-weight: 600; }
.fold { margin-block: 16px; padding: 0 14px; border: 1px solid var(--color-hairline); border-radius: 12px; background: var(--color-pearl); }
.fold > summary { display: flex; align-items: center; min-height: 44px; font-size: 14px; color: var(--color-muted); cursor: pointer; }
.fold > :last-child { margin-bottom: 14px; }
.command-group + .command-group { margin-top: 12px; }
.command-group-title { margin: 8px 0; font-size: 13px; font-weight: 400; color: var(--color-muted); }
.command-form { display: grid; grid-template-columns: minmax(0, 1fr) 140px auto; gap: 10px; align-items: end; margin-block: 4px 0; }
.command-form button { margin-bottom: 2px; }
.command-list { display: grid; gap: 8px; margin: 12px 0 0; padding: 0; list-style: none; }
.command-list li { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid var(--color-hairline); border-radius: 10px; background: var(--color-pearl); font-size: 14px; }
.command-list li span { flex: 1; min-width: 0; overflow-wrap: anywhere; }
/* 玩法页底部的三色图例与规则句，文案照抄参考站。 */
.play-legend { display: grid; gap: 6px; margin: 20px 0 0; padding: 0; list-style: none; }
.play-legend li { display: flex; align-items: center; gap: 8px; font-size: 13px; line-height: 1.5; color: var(--color-muted); }
.legend-dot { flex: none; width: 8px; height: 8px; border-radius: 999px; }
.play-rules { margin-top: 12px; font-size: 13px; line-height: 1.7; color: var(--color-muted); }
.hint-cell { align-self: end; padding-bottom: 12px; }
@media (max-width: 600px) {
  .settings-grid { grid-template-columns: 1fr; gap: 16px; }
  .settings-tabs { gap: 6px; }
  .settings-tabs button { flex: 1 1 auto; padding-inline: 12px; }
  .command-form { grid-template-columns: 1fr; }
}
@media (max-width: 560px) {
  .settings-card { padding: 16px; border-radius: 12px; }
  .card-head { flex-wrap: wrap; gap: 8px; }
  .card-heading { flex: 1 1 100%; }
  .card-title { font-size: 18px; }
  .card-reset { align-self: flex-start; }
  .settings-search { max-width: none; }
}
</style>
