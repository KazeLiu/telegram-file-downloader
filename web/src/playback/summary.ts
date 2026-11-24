// 设置摘要：一行话描述当前这套玩法，显示在设置卡与首页。
// 句式对齐参考站：`10 分钟 · 普通 · 抽签 · 指令 81 种 · 语音播报 指令`。
import { maleCommands } from './commands.ts'
import {
  difficultyLabels, finaleLabels, instructionLengthLabels, modeLabels, permitRate, restModeLabels,
} from './engine.ts'
import type { EdgeSettings } from './settings.ts'

/** 当前会进入抽选池的口令条数（含自定义，减去逐条停用的）。 */
export function enabledCommandCount(settings: EdgeSettings) {
  return Math.max(0, maleCommands.length + settings.custom.length - settings.disabled.length)
}

export function settingsSummary(settings: EdgeSettings) {
  const parts: string[] = []
  parts.push(settings.durationRandom ? '随机时长' : `${settings.minutes} 分钟`)
  parts.push(difficultyLabels[settings.difficulty])
  parts.push(finaleLabels[settings.finale])
  parts.push(`指令 ${enabledCommandCount(settings)} 种`)
  parts.push(`许可率 ${Math.round(permitRate(settings.difficulty, 0, settings.tune.chance) * 100)}%`)
  if (settings.instructionLength !== 'standard') parts.push(instructionLengthLabels[settings.instructionLength])
  const rest = settings.rest.mode === 'fixed'
    ? `${modeLabels.stop} ${settings.rest.seconds} 秒`
    : `${modeLabels.stop} ${settings.rest.min}–${settings.rest.max} 秒`
  parts.push(restModeLabels[settings.rest.mode] === '随机' ? rest : rest)
  if (settings.nipple.on) parts.push('只玩乳头')
  if (settings.glans.on) parts.push('只玩龟头')
  if (settings.hand === 'left') parts.push('左撇子')
  parts.push(settings.metronome ? '节拍声开' : '节拍声关')
  return parts.filter(Boolean).join(' · ')
}
