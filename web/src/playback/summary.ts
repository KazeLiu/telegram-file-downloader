import type { Playlist } from '../playback'
import { difficultyProfiles, endingLabels } from './edge'

const kindLabels: Record<Playlist['kind'], string> = { mixed: '混合内容', image: '仅图片', video: '仅视频' }

/**
 * 把播放设置压成一行中文摘要，供设置卡片头实时展示。
 *
 * 拼接顺序（空段自动省略，段落之间用「 · 」连接）：
 * 1. 时长：`minutes` 不是正数或不小于 999 视为不限时，写「不限时」，否则「N 分钟」。
 * 2. 难度：取 `difficultyProfiles` 的标签（简单/普通/困难/地狱）。
 * 3. 结局：取 `endingLabels` 的标签（抽签/必定允许/必定禁止/松手射精/连续/加时赛）。
 * 4. 许可率：`permitBase` 落在 30–95 时写「许可率 N%」，不是数字则省略。
 * 5. 内容：「混合内容」/「仅图片」/「仅视频」。
 * 6. 切图节奏：仅当内容含图片时出现；按 BPM 切图写「每拍一张」，按时间写「每张 N 秒」。
 * 7. 图片范围：仅当内容含图片时出现；`imageCount` 为 0 写「全部未展示图片」，否则「每轮 N 张」。
 * 8. 只看喜欢：`favoritesOnly` 为真时追加「只看喜欢」。
 * 9. 节拍器：实际启用时写「节拍器开」（仅图片 + 按 BPM 切图会自动启用），否则「节拍器关」。
 * 10. 语音：`speech` 为真写「语音开」，否则「语音关」。
 * 11. 节拍：按 BPM 切图时追加「快速 N BPM」（播放器的快速档即 `bpm`）。
 *
 * 纯函数：只读入参，不读写全局状态、不依赖时间与随机数，可直接断言。
 */
export function playbackSummary(item: Playlist): string {
  if (!item) return ''
  // 播放器里只有「仅图片 + 按 BPM」才会自动启用节拍器；混合内容即使存着 beat 也按时间切图。
  const beatsImages = item.kind === 'image' && item.imageTiming === 'beat'
  const hasImages = item.kind !== 'video'
  const seconds = Number.isFinite(item.imageSeconds) ? Math.max(1, Math.round(item.imageSeconds)) : 1
  const count = Number.isFinite(item.imageCount) ? Math.max(0, Math.round(item.imageCount)) : 0
  const minutes = item.minutes
  const duration = !Number.isFinite(minutes) || minutes <= 0 || minutes >= 999 ? '不限时' : `${minutes} 分钟`
  const difficulty = difficultyProfiles[item.difficulty]?.label ?? ''
  const ending = endingLabels[item.ending] ?? ''
  const base = Number.isFinite(item.permitBase) ? Math.min(95, Math.max(30, Math.round(item.permitBase))) : 0
  return [
    duration,
    difficulty,
    ending,
    base ? `许可率 ${base}%` : '',
    kindLabels[item.kind],
    hasImages ? (beatsImages ? '每拍一张' : `每张 ${seconds} 秒`) : '',
    hasImages ? (count ? `每轮 ${count} 张` : '全部未展示图片') : '',
    item.favoritesOnly ? '只看喜欢' : '',
    item.metronome || beatsImages ? '节拍器开' : '节拍器关',
    item.speech ? '语音开' : '语音关',
    beatsImages ? `快速 ${item.bpm} BPM` : '',
  ].filter(Boolean).join(' · ')
}
