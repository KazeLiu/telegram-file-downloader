<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { customCommandLimit, customCommandTextLimit, newPlaylist } from './playback'
import type { Playlist } from './playback'
import { playbackSummary } from './playback/summary'
import {
  builtinCommands, commandTypeLabels, difficultyOrder, difficultyProfiles, edgeWindowOptions, endingHints,
  endingLabels, endingOrder, permitStep, propLabels, toneLabels, vibrateLabels, voicePitchLabels, waitPresets,
} from './playback/edge'
import type { CommandType, Tone } from './playback/edge'

const settings = defineModel<Playlist>({ required: true })
const props = defineProps<{ runtime?: boolean }>()
const selected = ref('play')
const search = ref('')
// 分组顺序即契约里的「玩法 / 指令 / 内容 / 声音 / 其他」，关键词覆盖各组字段的中文别名。
const groups = computed(() => [
  { id: 'play', label: '玩法', keywords: '总时长 分钟 难度 简单 普通 困难 地狱 许可率 相位 比例 抽签 结局 加时 许可窗口 忍住 等待 随机 固定 指令时长 节奏' },
  { id: 'command', label: '指令', keywords: '口吻 强硬 挑逗 辱骂 温柔 类型 撸 慢 不许碰 乳头 龟头 惯用手 左右手 道具 飞机杯 前列腺 自定义 口令 启停 禁用' },
  { id: 'content', label: '内容', keywords: '内容类型 混合 仅图片 仅视频 顺序 随机 文件名 每轮 数量 图片间隔 切图 节奏 BPM 循环 喜欢 收藏 去重' },
  { id: 'sound', label: '声音', keywords: '音量 视频 媒体 静音 节拍器 BPM 语音 语速 音高 心跳 振动' },
  { id: 'other', label: '其他', keywords: '隐藏 时间 进度 明暗 亮度 画面' },
])
const visible = computed(() => groups.value.filter(group => search.value.trim()
  ? `${group.label} ${group.keywords}`.toLowerCase().includes(search.value.trim().toLowerCase()) : group.id === selected.value))
const summary = computed(() => playbackSummary(settings.value))
// 「恢复本组」只动当前分组，且要求再点一次确认，避免误触清掉还没记住的设置。
const resetArmed = ref(false)
const canReset = computed(() => !search.value.trim() && visible.value.length === 1)
const resetLabel = computed(() => resetArmed.value ? '确认恢复？' : '恢复本组')
watch([selected, search], () => { resetArmed.value = false })
watch(settings, () => { resetArmed.value = false }, { deep: true })
function selectGroup(id: string) {
  selected.value = id
  search.value = ''
  resetArmed.value = false
}

// 多选项（口吻、类型开关、道具）：就地点选/取消，保持数组引用不变，避免触发父组件整体替换。
function toggleChoice<T extends string>(list: T[], value: T) {
  const at = list.indexOf(value)
  if (at >= 0) list.splice(at, 1)
  else list.push(value)
}
const toneOptions = Object.keys(toneLabels) as Tone[]
const commandTypeOptions = Object.keys(commandTypeLabels) as CommandType[]
const propOptions = Object.keys(propLabels)
const pitchOptions = Object.keys(voicePitchLabels)
const vibrateOptions = Object.keys(vibrateLabels)
// 契约只给了三档指令时长的倍率，没有文案表，标签写在这里。
const paceLabels: Record<'standard' | 'long' | 'veryLong', string> = { standard: '标准', long: '偏长', veryLong: '很长' }
const paceOptions = Object.keys(paceLabels) as (keyof typeof paceLabels)[]
const profile = computed(() => difficultyProfiles[settings.value.difficulty])
const ratioTotal = computed(() => Math.round(settings.value.ratioFast + settings.value.ratioSlow + settings.value.ratioRest))
const beatsImages = computed(() => settings.value.kind === 'image' && settings.value.imageTiming === 'beat')

// 等待时长：数字输入框的 v-model 走 input 事件、先于 @change 落值，所以在 @change 里夹取读到的已是新值；
// select 的 v-model 与模板 @change 都挂 change 事件且 v-model 更晚绑定，故预设档改用可写 computed 避免读到旧值。
// 夹取放在提交时（blur/回车）而不是每次按键，免得一边输入一边被改写。
function clampWait(raw: number) {
  const value = Number.isFinite(raw) ? Math.round(raw) : 3
  return Math.min(120, Math.max(3, value))
}
const waitPreset = computed({
  get: () => settings.value.waitPreset,
  set: (id: Playlist['waitPreset']) => {
    settings.value.waitPreset = id
    const preset = waitPresets.find(item => item.id === id)
    if (!preset) return
    settings.value.waitMin = preset.min
    settings.value.waitMax = preset.max
  },
})
function syncWaitMin() {
  const value = clampWait(settings.value.waitMin)
  settings.value.waitMin = value
  if (settings.value.waitMax < value) settings.value.waitMax = value
}
function syncWaitMax() {
  const value = clampWait(settings.value.waitMax)
  settings.value.waitMax = Math.max(value, settings.value.waitMin)
}
function syncWaitFixed() {
  const value = clampWait(settings.value.waitMin)
  settings.value.waitMin = value
  settings.value.waitMax = value
}

// 自定义口令：上限 30 条、单条 60 字（与 playback.ts 的校验共用同一组常量）。
const commandLimit = customCommandLimit
const commandTextLimit = customCommandTextLimit
const draftCommand = ref('')
const draftType = ref<CommandType>('fast')
const canAddCommand = computed(() => !!draftCommand.value.trim() && settings.value.customCommands.length < commandLimit)
function addCommand() {
  const text = draftCommand.value.trim().slice(0, commandTextLimit)
  if (!text || settings.value.customCommands.length >= commandLimit) return
  settings.value.customCommands.push({ text, type: draftType.value })
  draftCommand.value = ''
}
function removeCommand(index: number) {
  settings.value.customCommands.splice(index, 1)
}

// 内置口令按类型分组列出，点一下在启用/停用之间切换（存的是停用名单）。
const commandGroups = computed(() => commandTypeOptions.map(type => ({
  type, label: commandTypeLabels[type], items: builtinCommands.filter(command => command.type === type),
})))
function toggleCommand(id: string) {
  toggleChoice(settings.value.disabledCommands, id)
}
function enableAllCommands() {
  settings.value.disabledCommands.splice(0)
}

function resetGroup() {
  if (!resetArmed.value) { resetArmed.value = true; return }
  resetArmed.value = false
  draftCommand.value = ''
  const defaults = newPlaylist()
  const item = settings.value
  if (selected.value === 'play') {
    item.minutes = defaults.minutes
    item.difficulty = defaults.difficulty
    item.ratioFast = defaults.ratioFast
    item.ratioSlow = defaults.ratioSlow
    item.ratioRest = defaults.ratioRest
    item.permitBase = defaults.permitBase
    item.ending = defaults.ending
    item.edgeWindow = defaults.edgeWindow
    item.waitMode = defaults.waitMode
    item.waitPreset = defaults.waitPreset
    item.waitMin = defaults.waitMin
    item.waitMax = defaults.waitMax
    item.instructionPace = defaults.instructionPace
  } else if (selected.value === 'command') {
    item.tones.splice(0, item.tones.length, ...defaults.tones)
    item.commandTypes.splice(0, item.commandTypes.length, ...defaults.commandTypes)
    item.hand = defaults.hand
    item.props.splice(0, item.props.length, ...defaults.props)
    item.customCommands.splice(0, item.customCommands.length)
    item.disabledCommands.splice(0, item.disabledCommands.length)
  } else if (selected.value === 'content') {
    item.kind = defaults.kind
    item.order = defaults.order
    item.imageCount = defaults.imageCount
    item.imageSeconds = defaults.imageSeconds
    item.imageTiming = defaults.imageTiming
    item.bpm = defaults.bpm
    item.loop = defaults.loop
    item.favoritesOnly = defaults.favoritesOnly
  } else if (selected.value === 'sound') {
    item.metronome = defaults.metronome
    item.beatVolume = defaults.beatVolume
    item.heartbeat = defaults.heartbeat
    item.heartbeatVolume = defaults.heartbeatVolume
    item.speech = defaults.speech
    item.speechVolume = defaults.speechVolume
    item.speechRate = defaults.speechRate
    item.voicePitch = defaults.voicePitch
    item.mediaVolume = defaults.mediaVolume
    item.vibrate = defaults.vibrate
  } else {
    item.hideTime = defaults.hideTime
    item.brightness = defaults.brightness
  }
}
</script>

<template>
  <div class="settings-card" :class="{ runtime }">
    <header class="card-head">
      <div class="card-heading">
        <h3 class="card-title">播放设置</h3>
        <p class="card-summary">{{ summary }}</p>
      </div>
      <button v-if="canReset" type="button" class="text-button card-reset" :title="resetArmed ? '再点一次把本组恢复为默认值' : '只把本组恢复为默认值，其他分组不变'" @click="resetGroup">{{ resetLabel }}</button>
    </header>
    <label class="settings-search">查找设置<input v-model="search" type="search" placeholder="例如：难度、许可率、结局、口令" /></label>
    <div class="settings-tabs" role="group" aria-label="设置分类">
      <button v-for="group in groups" :key="group.id" type="button" :aria-pressed="!search && selected === group.id" @click="selectGroup(group.id)">{{ group.label }}</button>
    </div>
    <p v-if="!visible.length" class="muted" role="status">没有匹配的设置，请换个关键词。</p>
    <section v-for="group in visible" :key="group.id" class="settings-section" :aria-label="`${group.label}设置`">
      <h4 v-if="search" class="section-title">{{ group.label }}</h4>

      <template v-if="group.id === 'play'">
        <div class="settings-grid">
          <label>总时长（分钟，0 为不限）<input v-model.number="settings.minutes" type="number" min="0" max="180" required /></label>
          <label>难度<select v-model="settings.difficulty">
            <option v-for="key in difficultyOrder" :key="key" :value="key">{{ difficultyProfiles[key].label }}</option>
          </select></label>
          <label>结局<select v-model="settings.ending">
            <option v-for="key in endingOrder" :key="key" :value="key">{{ endingLabels[key] }}</option>
          </select></label>
          <label>许可窗口（秒）<select v-model="settings.edgeWindow">
            <option v-for="value in edgeWindowOptions" :key="value" :value="value">{{ value }} 秒</option>
          </select></label>
          <label>指令时长<select v-model="settings.instructionPace">
            <option v-for="key in paceOptions" :key="key" :value="key">{{ paceLabels[key] }}</option>
          </select></label>
          <label>忍住后等待<select v-model="settings.waitMode">
            <option value="random">随机时长</option>
            <option value="fixed">固定时长</option>
          </select></label>
        </div>
        <p class="muted">{{ endingHints[settings.ending] }}；难度预设 {{ profile.label }}：比例 {{ profile.fast }} / {{ profile.slow }} / {{ profile.rest }}，基础许可率 {{ profile.permit }}%。</p>

        <div v-if="settings.waitMode === 'random'" class="settings-grid">
          <label>等待区间<select v-model="waitPreset">
            <option v-for="preset in waitPresets" :key="preset.id" :value="preset.id">{{ preset.label }}</option>
          </select></label>
          <span class="hint-cell muted">选预设会同时改写下面两个数字，也可以直接改。</span>
          <label>最短等待（秒）<input v-model.number="settings.waitMin" type="number" min="3" max="120" required @change="syncWaitMin" /></label>
          <label>最长等待（秒）<input v-model.number="settings.waitMax" type="number" min="3" max="120" required @change="syncWaitMax" /></label>
        </div>
        <div v-else class="settings-grid">
          <label>固定等待（秒）<input v-model.number="settings.waitMin" type="number" min="3" max="120" required @change="syncWaitFixed" /></label>
        </div>
        <p class="muted">按下「忍住了」之后进入红色相位，等这段时长过去再回到循环。</p>

        <details class="fold">
          <summary>自己调三比例与基础许可率（当前合计 {{ ratioTotal }}%）</summary>
          <div class="settings-grid">
            <label>绿·可以撸 {{ settings.ratioFast }}%<input v-model.number="settings.ratioFast" type="range" min="0" max="100" step="5" /></label>
            <label>黄·慢慢来 {{ settings.ratioSlow }}%<input v-model.number="settings.ratioSlow" type="range" min="0" max="100" step="5" /></label>
            <label>红·不许碰 {{ settings.ratioRest }}%<input v-model.number="settings.ratioRest" type="range" min="0" max="100" step="5" /></label>
            <label>基础许可率 {{ settings.permitBase }}%<input v-model.number="settings.permitBase" type="range" min="30" :max="95" :step="permitStep" /></label>
          </div>
          <p class="muted">三者合计需为 100%，当前 {{ ratioTotal }}%；不相等时运行时会按比例归一化。</p>
        </details>
      </template>

      <template v-else-if="group.id === 'command'">
        <h5 class="field-label">口吻（可多选）</h5>
        <div class="chips">
          <button v-for="key in toneOptions" :key="key" type="button" class="chip" :aria-pressed="settings.tones.includes(key)" @click="toggleChoice(settings.tones, key)">{{ toneLabels[key] }}</button>
        </div>
        <p class="muted">只影响指令的叫法，不影响节奏。</p>

        <h5 class="field-label">类型开关（只抽选中的类型）</h5>
        <div class="chips">
          <button v-for="key in commandTypeOptions" :key="key" type="button" class="chip" :aria-pressed="settings.commandTypes.includes(key)" @click="toggleChoice(settings.commandTypes, key)">{{ commandTypeLabels[key] }}</button>
        </div>

        <div class="settings-grid">
          <label>惯用手<select v-model="settings.hand">
            <option value="right">右手</option>
            <option value="left">左手</option>
          </select></label>
        </div>

        <h5 class="field-label">道具（可多选）</h5>
        <div class="chips">
          <button v-for="key in propOptions" :key="key" type="button" class="chip" :aria-pressed="settings.props.includes(key)" @click="toggleChoice(settings.props, key)">{{ propLabels[key] }}</button>
        </div>
        <p class="muted">不选则指令里不出现道具。</p>

        <h5 class="field-label">自定义口令（{{ settings.customCommands.length }}/{{ commandLimit }}）</h5>
        <div class="command-form">
          <label>口令内容<input v-model="draftCommand" type="text" :maxlength="commandTextLimit" placeholder="例如：停三秒再继续" @keydown.enter.prevent="addCommand" /></label>
          <label>类型<select v-model="draftType">
            <option v-for="key in commandTypeOptions" :key="key" :value="key">{{ commandTypeLabels[key] }}</option>
          </select></label>
          <button type="button" class="secondary" :disabled="!canAddCommand" @click="addCommand">添加</button>
        </div>
        <p v-if="settings.customCommands.length >= commandLimit" class="muted">已到 30 条上限，删掉一条再添加。</p>
        <p v-else class="muted">单条最多 60 字，写短句；要改就删掉重新添加。</p>
        <ul v-if="settings.customCommands.length" class="command-list">
          <li v-for="(item, index) in settings.customCommands" :key="`${item.text}-${index}`">
            <small class="badge">{{ commandTypeLabels[item.type] }}</small>
            <span>{{ item.text }}</span>
            <button type="button" class="text-button" @click="removeCommand(index)">删除</button>
          </li>
        </ul>

        <details class="fold">
          <summary>逐条启停内置口令（已停用 {{ settings.disabledCommands.length }} 条）</summary>
          <p class="muted">亮着表示启用，点一下停用；停用的口令不会再被抽到。</p>
          <div v-for="commandGroup in commandGroups" :key="commandGroup.type" class="command-group">
            <h6 class="command-group-title">{{ commandGroup.label }}</h6>
            <div class="chips">
              <button v-for="command in commandGroup.items" :key="command.id" type="button" class="chip" :aria-pressed="!settings.disabledCommands.includes(command.id)" @click="toggleCommand(command.id)">{{ command.text }}</button>
            </div>
          </div>
          <button v-if="settings.disabledCommands.length" type="button" class="text-button" @click="enableAllCommands">全部启用</button>
        </details>
      </template>

      <template v-else-if="group.id === 'content'">
        <div class="settings-grid">
          <label v-if="!runtime">内容类型<select v-model="settings.kind">
            <option value="mixed">混合内容</option>
            <option value="image">仅图片</option>
            <option value="video">仅视频</option>
          </select></label>
          <label v-if="!runtime">播放顺序<select v-model="settings.order">
            <option value="shuffle">随机</option>
            <option value="sequential">文件名顺序</option>
          </select></label>
          <label v-if="!runtime && settings.kind !== 'video'">每轮图片数（0 为全部）<input v-model.number="settings.imageCount" type="number" min="0" max="100000" required /></label>
          <label v-if="settings.kind === 'image'">图片切换<select v-model="settings.imageTiming">
            <option value="time">按时间</option>
            <option value="beat">按 BPM · 每拍一张</option>
          </select></label>
          <label v-if="settings.kind !== 'video' && (settings.kind !== 'image' || settings.imageTiming === 'time')">图片间隔（秒）<input v-model.number="settings.imageSeconds" type="number" min="1" max="300" required /></label>
          <label>快速节拍（BPM）<input v-model.number="settings.bpm" type="number" min="30" max="180" required /></label>
        </div>
        <p v-if="beatsImages" class="muted">每拍发声并切一张，慢速为快速的 60%；休息时不发声、不自动切图。</p>
        <label class="toggle"><input v-model="settings.loop" type="checkbox" />循环列表</label>
        <label v-if="!runtime" class="toggle"><input v-model="settings.favoritesOnly" type="checkbox" />仅播放喜欢</label>
        <p v-if="!runtime && settings.kind !== 'video'" class="muted">已展示图片不再入选；未展示的不足一轮时，所选图库中的图片重新参与。视频不计入图片数量。</p>
      </template>

      <template v-else-if="group.id === 'sound'">
        <p v-if="beatsImages" class="muted">BPM 切图自动启用节拍器，音量为 0 时仍按拍切图。</p>
        <label v-else class="toggle"><input v-model="settings.metronome" type="checkbox" />节拍器</label>
        <div class="settings-grid">
          <label>节拍音量 · {{ settings.beatVolume }}%<input v-model.number="settings.beatVolume" type="range" min="0" max="100" /></label>
          <label v-if="settings.kind !== 'image'">媒体音量 · {{ settings.mediaVolume }}%<input v-model.number="settings.mediaVolume" type="range" min="0" max="100" /></label>
        </div>
        <label class="toggle"><input v-model="settings.heartbeat" type="checkbox" />心跳声</label>
        <div v-if="settings.heartbeat" class="settings-grid">
          <label>心跳音量 · {{ settings.heartbeatVolume }}%<input v-model.number="settings.heartbeatVolume" type="range" min="0" max="100" /></label>
        </div>
        <label class="toggle"><input v-model="settings.speech" type="checkbox" />语音提示阶段名称</label>
        <div v-if="settings.speech" class="settings-grid">
          <label>语音音量 · {{ settings.speechVolume }}%<input v-model.number="settings.speechVolume" type="range" min="0" max="100" /></label>
          <label>语速<select v-model.number="settings.speechRate"><option :value=".8">0.8×</option><option :value="1">1.0×</option><option :value="1.2">1.2×</option></select></label>
          <label>音高<select v-model="settings.voicePitch">
            <option v-for="key in pitchOptions" :key="key" :value="key">{{ voicePitchLabels[key] }}</option>
          </select></label>
        </div>
        <div class="settings-grid">
          <label>振动<select v-model="settings.vibrate">
            <option v-for="key in vibrateOptions" :key="key" :value="key">{{ vibrateLabels[key] }}</option>
          </select></label>
        </div>
      </template>

      <template v-else>
        <label class="toggle"><input v-model="settings.hideTime" type="checkbox" />隐藏时间与进度条</label>
        <label>画面亮度 · {{ settings.brightness }}%<input v-model.number="settings.brightness" type="range" min="20" max="100" /></label>
        <p class="muted">只影响播放器中的画面，不修改原文件，也不改变结束时间。</p>
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
.field-label { margin: 16px 0 10px; font-size: 14px; font-weight: 600; color: var(--color-supporting); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-block: 4px 0; }
.chip { min-height: 38px; padding: 6px 14px; border-radius: 999px; border: 1px solid var(--color-hairline); background: var(--color-pearl); font-size: 14px; line-height: 1.4; }
.chip[aria-pressed="true"] { background: var(--color-selection); border-color: var(--color-primary); color: var(--color-primary); font-weight: 600; }
.fold { margin-block: 16px; padding: 0 14px; border: 1px solid var(--color-hairline); border-radius: 12px; background: var(--color-pearl); }
.fold > summary { display: flex; align-items: center; min-height: 44px; font-size: 14px; color: var(--color-muted); cursor: pointer; }
.fold > :last-child { margin-bottom: 14px; }
.command-group + .command-group { margin-top: 12px; }
.command-group-title { margin: 0 0 8px; font-size: 13px; font-weight: 400; color: var(--color-muted); }
.command-form { display: grid; grid-template-columns: minmax(0, 1fr) 140px auto; gap: 10px; align-items: end; margin-block: 4px 0; }
.command-form button { margin-bottom: 2px; }
.command-list { display: grid; gap: 8px; margin: 12px 0 0; padding: 0; list-style: none; }
.command-list li { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid var(--color-hairline); border-radius: 10px; background: var(--color-pearl); font-size: 14px; }
.command-list li span { flex: 1; min-width: 0; overflow-wrap: anywhere; }
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
