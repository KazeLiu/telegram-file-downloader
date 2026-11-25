// 设置摘要：一行话描述当前这套玩法，显示在设置卡与首页。
// 句式对齐参考站：`10 分钟 · 普通 · 抽签 · 指令 81 种 · 语音播报 指令`。
import { focusGlansCommands, focusNippleCommands, maleCommands } from './commands.ts'
import { focusLabels } from './focus.ts'
import {
  difficultyLabels, extendLengthLabels, finaleLabels, instructionLengthLabels, modeLabels, permitRate, restModeLabels, toneLabels, toneOrder,
} from './engine.ts'
import type { EdgeSettings } from './settings.ts'

/** 当前会进入抽选池的口令条数（含自定义，减去逐条停用的）。 */
export function enabledCommandCount(settings: EdgeSettings) {
  // 单部位模式下整局换成该部位的专属池（条数与主池不同）。
  if (settings.focus === 'nipple') return focusNippleCommands.length
  if (settings.focus === 'glans') return focusGlansCommands.length
  return Math.max(0, maleCommands.length + settings.custom.length - settings.disabled.length)
}

/** 指令池为空时的提示：与参考站的 `OWN_ONLY_TEXT` 同口径（只关掉部分时不提示）。 */
export function commandPoolNotice(settings: EdgeSettings) {
  // 单部位模式用的是专属池，不受「逐条停用」影响。
  if (settings.focus !== 'none') return ''
  const builtinOff = settings.disabled.length >= maleCommands.length
  if (!builtinOff) return ''
  if (!settings.custom.length) {
    return '默认指令已全部关闭，而且还没有自己的指令。请在「添加自己的指令」里添加，或在「指令类型」里重新打开'
  }
  return '默认指令已全部关闭。只会出现你自己的指令'
}

export function settingsSummary(settings: EdgeSettings) {
  const parts: string[] = []
  parts.push(settings.durationRandom ? '随机时长' : `${settings.minutes} 分钟`)
  parts.push(difficultyLabels[settings.difficulty])
  parts.push(finaleLabels[settings.finale])
  if (settings.finale === 'overtime') parts.push(extendLengthLabels[settings.extendLen])
  parts.push(`指令 ${enabledCommandCount(settings)} 种`)
  parts.push(`许可率 ${Math.round(permitRate(settings.difficulty, 0, settings.tune.chance) * 100)}%`)
  if (settings.instructionLength !== 'standard') parts.push(instructionLengthLabels[settings.instructionLength])
  const rest = settings.rest.mode === 'fixed'
    ? `${modeLabels.stop} ${settings.rest.seconds} 秒`
    : `${modeLabels.stop} ${settings.rest.min}–${settings.rest.max} 秒`
  parts.push(restModeLabels[settings.rest.mode] === '随机' ? rest : rest)
  if (settings.focus !== 'none') parts.push(focusLabels[settings.focus])
  if (settings.focus === 'none' && settings.nipple.on) parts.push('只玩乳头')
  if (settings.focus === 'none' && settings.glans.on) parts.push('只玩龟头')
  if (settings.toy) parts.push('飞机杯')
  if (settings.aneros) parts.push('按摩器')
  const tones = toneOrder.filter(key => settings.tones[key])
  if (tones.length) parts.push(`口吻 ${tones.map(key => toneLabels[key]).join('+')}`)
  if (settings.bpmRandom.on) parts.push(`每次变换节奏 ${settings.bpmRandom.min}–${settings.bpmRandom.max}`)
  if (settings.hand === 'left') parts.push('左撇子')
  if (settings.mirror.on) parts.push('镜子')
  parts.push(settings.metronome ? '节拍声开' : '节拍声关')
  return parts.filter(Boolean).join(' · ')
}
