// 寸止引擎的回归检查：难度表、相位抽取、许可率、结局判定、时间线与会话推进。
// 这批断言对应参考实现的精确口径（share/seconds/chance/stopAfterStop），改引擎时必须同步这里。
import assert from 'node:assert/strict'

// 浮点相加会带来 0.8999999999999999 这类尾差，概率一律按 1e-9 容差比较。
const assertClose = (actual: number, expected: number, message?: string) => assert.ok(Math.abs(actual - expected) < 1e-9, message ?? `${actual} 应当接近 ${expected}`)
import {
  varyBpm,
  adjustMix, beatVolumeMax, bindCommands, buildTimeline, categoryOrder, commandPool, customCommandLimit,
  customCommandTextLimit, decideFinale, difficulties, difficultyOrder, durationChoices, durationMax, durationMin,
  extendChance, extendLengthOrder, extendLineSeconds, extendLines, extendMs,
  multiDoneBody, multiEndText, multiLines, multiRoundLabel, multiRoundSeconds, multiRounds, multiTitle, multiWindowSeconds,
  filterByCategories, finaleOrder, finalHoldMs, formatClock, instructionLengthOrder, mixOf, modeColors, modeColorsDark, modeLabels,
  modeOrder, mulberry32, permitMaxGain, permitRate, permitStep, pickCommandAt, pickIndex, pickMode, planFocus,
  presets, presetNone, presetNotes, presetOrder, randomBpm, randomSeed, redBeatOrder, restFixedChoices, restMax, restMin, restRangeChoices,
  restSeconds, rewardChoices, shareOf, swapHands, taskAt, taskSeconds, textOpacityMin, textScaleMin, timeShareOf, toneAfterOrder,
  toneAfterForCommand, toneForTask, pickToneLine, toneLabels, toneOrder, type EdgeMode
} from '../src/playback/engine.ts'
import { abuseLines, feetLines, strongLines, sweetLines, teaseLines, toneNotes } from '../src/playback/tones.ts'
import { anerosCommands, focusGlansCommands, focusNippleCommands, maleCommands, toyCommands } from '../src/playback/commands.ts'
import { addDay, dayKey, daysBetween, daysStorageKey, daysSummary, daysText, daysView, emptyDays, hoursLeftToday, nextMilestone, normalizeDays, readDays, writeDays } from '../src/playback/days.ts'
import {
  countResult, emptyTally, parseRecords, pushRecord, readRecords, readTally, recordOutcome, recordOrder, recordTime,
  recordsStorageKey, recordsText, stamps, tallyFromStats, tallyStorageKey, writeRecords, writeTally
} from '../src/playback/records.ts'
import { focusAllowBelow, focusAreas, focusLabels } from '../src/playback/focus.ts'
import { defaultEdgeSettings, edgeSchemaVersion, edgeStorageKey, normalizeEdgeSettings, readEdgeSettings, writeEdgeSettings } from '../src/playback/settings.ts'
import { EdgeSession } from '../src/playback/session.ts'
import {
  MIRROR_CONSTRAINTS, classifyMirrorError, mirrorPlaceFor, mirrorPlaces, mirrorPlaceLabels, mirrorText, stopStream
} from '../src/playback/mirror.ts'
import { addLost, addSession, emptyLost, emptyStats, lostPct, normalizeLost, normalizeStats, readLost, readStats, statsSummary } from '../src/playback/history.ts'

// —— 常量口径 ——
assert.deepEqual(difficultyOrder, ['easy', 'normal', 'hard', 'hell'])
assert.deepEqual(modeOrder, ['go', 'slow', 'stop'])
assert.deepEqual(modeLabels, { go: '可以撸', slow: '慢慢来', stop: '不许碰' })
assert.deepEqual(modeColors, { go: '#5ee3a1', slow: '#f0c35a', stop: '#ff6b7d' })
// 镜子铺满背景叠的是模式色的暗色变体，不是亮色。
assert.deepEqual(modeColorsDark, { go: '#0c3f2c', slow: '#4d3400', stop: '#5c0d16' })
assert.deepEqual(finaleOrder, ['draw', 'always', 'never', 'ruin', 'continuous', 'overtime'])
assert.deepEqual(durationChoices, [3, 5, 10, 15, 20, 30])
assert.equal(durationMin, 1)
assert.equal(durationMax, 180)
assert.equal(restMin, 3)
assert.equal(restMax, 120)
assert.deepEqual(restRangeChoices, [[8, 16], [10, 40], [20, 60]])
assert.deepEqual(restFixedChoices, [5, 10, 12, 20, 30, 60])
assert.deepEqual(rewardChoices, [5, 10, 20, 30, 45, 60])
assert.equal(beatVolumeMax, 300)
assert.equal(textOpacityMin, 30)
assert.equal(textScaleMin, 60)
assert.equal(customCommandLimit, 30)
assert.equal(customCommandTextLimit, 60)
assert.equal(finalHoldMs, 5000)
assert.equal(permitStep, 0.05)
assert.equal(permitMaxGain, 0.2)
assert.deepEqual(categoryOrder, ['edge', 'tease', 'pose', 'pain'])
assert.deepEqual(instructionLengthOrder, ['standard', 'long', 'veryLong'])
assert.deepEqual(toneOrder, ['strong', 'tease', 'abuse', 'sweet', 'feet'])
assert.deepEqual(toneAfterOrder, ['never', 'half', 'always'])
assert.deepEqual(redBeatOrder, ['heartbeat', 'both', 'metronome'])
assert.deepEqual(presetOrder, ['first', 'standard', 'long'])
assert.equal(presets.first.difficulty, 'easy')
assert.equal(presets.standard.difficulty, 'normal')
assert.equal(presets.long.difficulty, 'hard')

// —— 难度表：与参考实现逐字段一致 ——
assert.deepEqual(difficulties.easy, { chance: 0.85, share: { go: 0.56, slow: 0.2, stop: 0.24 }, seconds: { go: [15, 30], slow: [8, 16], stop: [4, 8] }, stopAfterStop: false })
assert.deepEqual(difficulties.normal, { chance: 0.7, share: { go: 0.38, slow: 0.2, stop: 0.42 }, seconds: { go: [12, 25], slow: [8, 16], stop: [5, 10] }, stopAfterStop: false })
assert.deepEqual(difficulties.hard, { chance: 0.5, share: { go: 0.39, slow: 0.25, stop: 0.36 }, seconds: { go: [8, 18], slow: [6, 14], stop: [6, 14] }, stopAfterStop: true })
assert.deepEqual(difficulties.hell, { chance: 0.3, share: { go: 0.35, slow: 0.22, stop: 0.43 }, seconds: { go: [6, 14], slow: [6, 12], stop: [8, 18] }, stopAfterStop: true })

// —— mulberry32：同种子必然同序列，且落在 [0,1) ——
const first = mulberry32(42)
const second = mulberry32(42)
for (let index = 0; index < 8; index += 1) {
  const value = first()
  assert.equal(value, second(), '同种子必须复现')
  assert.ok(value >= 0 && value < 1, '随机数必须落在 [0,1)')
}
assert.equal(mulberry32(1)(), 0.6270739405881613)
assert.notEqual(mulberry32(1)(), mulberry32(2)(), '不同种子应给出不同序列')
assert.ok(Number.isInteger(randomSeed()) && randomSeed() >= 0)

// —— 相位占比：难度默认、手调 stop、手调 mix 三条路径 ——
assert.deepEqual(shareOf('normal', null), { go: 0.38, slow: 0.2, stop: 0.42 })
// 手调 stop=50% 时按 go/slow 原比例分摊剩余 50%。
const tunedStop = shareOf('normal', { chance: null, stop: 50, mix: null })
assert.equal(tunedStop.stop, 0.5)
assert.ok(Math.abs(tunedStop.go - 0.5 * 0.38 / 0.58) < 1e-9)
assert.ok(Math.abs(tunedStop.slow - 0.5 * 0.2 / 0.58) < 1e-9)
// 手调 mix 时按各相位平均秒数反归一化。
const tunedMix = shareOf('normal', { chance: null, stop: null, mix: { go: 60, slow: 20, stop: 20 } })
const mixTotal = tunedMix.go + tunedMix.slow + tunedMix.stop
assert.ok(Math.abs(mixTotal - 1) < 1e-9, 'mix 占比必须归一化到 1')
assert.ok(tunedMix.go > tunedMix.slow && tunedMix.go > tunedMix.stop)
// mix 是时间比例，timeShareOf 原样返回；非 mix 时时间加权后 go 占比会变大。
assert.deepEqual(timeShareOf('normal', { chance: null, stop: null, mix: { go: 60, slow: 20, stop: 20 } }), { go: 0.6, slow: 0.2, stop: 0.2 })
const normalTime = timeShareOf('normal', null)
assert.ok(normalTime.go > 0.38, '时间加权后可以撸占比应高于份额')
assert.ok(Math.abs(normalTime.go + normalTime.slow + normalTime.stop - 1) < 1e-9)
// mixOf 输出 5% 步进整数，三项和 100。
for (const difficulty of difficultyOrder) {
  const mix = mixOf(difficulty, null)
  assert.equal(mix.go + mix.slow + mix.stop, 100, `${difficulty} 的三项和必须是 100`)
  for (const value of [mix.go, mix.slow, mix.stop]) assert.equal(value % 5, 0, 'mix 必须是 5 的倍数')
  assert.ok(mix.stop <= 60, '不许碰上限 60%')
}

// —— adjustMix：调一项，差额从另两项扣 ——
const baseMix = { go: 60, slow: 20, stop: 20 }
const moreStop = adjustMix(baseMix, 'stop', 30)
assert.equal(moreStop.stop, 30)
assert.equal(moreStop.go, 50)
assert.equal(moreStop.slow, 20)
assert.equal(moreStop.go + moreStop.slow + moreStop.stop, 100)
const lessStop = adjustMix(baseMix, 'stop', 10)
assert.equal(lessStop.stop, 10)
assert.equal(lessStop.go + lessStop.slow + lessStop.stop, 100)
assert.equal(adjustMix(baseMix, 'stop', 999).stop, 60, 'stop 上限 60')
assert.equal(adjustMix(baseMix, 'go', 999).go, 100, '其余上限 100')
assert.equal(adjustMix(baseMix, 'slow', 33).slow, 35, '按 5% 步进取整')

// —— taskSeconds：stop 不吃 long/veryLong ——
const zeros = () => 0
const nines = () => 0.999999
assert.equal(taskSeconds('normal', 'go', zeros), 12)
assert.equal(taskSeconds('normal', 'go', nines), 25)
assert.equal(taskSeconds('normal', 'stop', zeros), 5)
assert.equal(taskSeconds('normal', 'stop', nines), 10)
assert.equal(taskSeconds('normal', 'go', zeros, 'long'), 60)
assert.equal(taskSeconds('normal', 'go', nines, 'long'), 120)
assert.equal(taskSeconds('normal', 'go', zeros, 'veryLong'), 120)
assert.equal(taskSeconds('normal', 'go', nines, 'veryLong'), 300)
assert.equal(taskSeconds('normal', 'slow', zeros, 'long'), 60, '慢速也吃长档')
assert.equal(taskSeconds('normal', 'stop', zeros, 'long'), 5, '不许碰不吃长档')
assert.equal(taskSeconds('normal', 'stop', nines, 'veryLong'), 10, '不许碰不吃很长档')

// —— permitRate：基础值 + 每次忍住 5%，累计最多 +20% ——
assert.equal(permitRate('normal', 0), 0.7)
assertClose(permitRate('normal', 1), 0.75)
assertClose(permitRate('normal', 4), 0.9)
assertClose(permitRate('normal', 5), 0.9, '累计最多 +20%')
assertClose(permitRate('normal', 99), 0.9, '继续忍住不再涨')
assert.equal(permitRate('easy', 0), 0.85)
assert.equal(permitRate('hell', 0), 0.3)
assertClose(permitRate('hell', 4), 0.5)
assert.equal(permitRate('normal', 0, 50), 0.5, '手调值优先于难度基础值')
assert.equal(permitRate('normal', 4, 100), 1, '封顶 100%')
assert.equal(permitRate('normal', 0, 95), 0.95)

// —— decideFinale：结局五路 ——
const fixed = (value: number) => () => value
assert.equal(decideFinale('always', 'normal', 0, fixed(0.99)), 'success')
assert.equal(decideFinale('continuous', 'hell', 0, fixed(0.99)), 'success')
assert.equal(decideFinale('never', 'easy', 4, fixed(0)), 'fail')
assert.equal(decideFinale('ruin', 'easy', 4, fixed(0.99)), 'ruin')
assert.equal(decideFinale('draw', 'normal', 0, fixed(0.69)), 'success')
assert.equal(decideFinale('draw', 'normal', 0, fixed(0.71)), 'fail')
assert.equal(decideFinale('draw', 'normal', 4, fixed(0.89)), 'success', '忍住 4 次后 70%→90%')
assert.equal(decideFinale('draw', 'normal', 4, fixed(0.91)), 'fail')
assert.equal(decideFinale('overtime', 'normal', 0, fixed(0.5)), 'success')
assert.equal(decideFinale('overtime', 'normal', 0, fixed(0.5), null, true), 'ruin', '加时赛允许松手')
assert.equal(decideFinale('overtime', 'normal', 0, fixed(0.9)), 'fail')

// —— 加时赛：许可率每次 +15%、第 5 次必中；时长按第几次决定 ——
assert.deepEqual(extendLengthOrder, ['short', 'normal', 'shrink'])
assert.equal(extendLineSeconds, 6)
assert.equal(extendLines.length, 4)
assertClose(extendChance(0.7, 0), 0.7)
assertClose(extendChance(0.7, 1), 0.85)
assertClose(extendChance(0.7, 2), 1)
assertClose(extendChance(0.3, 1), 0.45)
assert.equal(extendChance(0.3, 5), 1, '第 5 次加时必中')
assert.equal(extendChance(0.3, 9), 1)
assert.equal(extendMs('short', 1, zeros), 60_000)
assert.equal(extendMs('short', 4, nines), 180_000)
assert.equal(extendMs('normal', 1, zeros), 120_000, '普通加时 2～5 分钟')
assert.equal(extendMs('normal', 4, nines), 300_000)
assert.equal(extendMs('shrink', 1, zeros), 300_000, '越来越短：第一次 5～10 分钟')
assert.equal(extendMs('shrink', 1, nines), 600_000)
assert.equal(extendMs('shrink', 2, zeros), 180_000)
assert.equal(extendMs('shrink', 3, zeros), 120_000)
assert.equal(extendMs('shrink', 4, zeros), 60_000)

// 连续（多少次都行）：许可窗口固定 100 秒，每 25 秒换一条「再来一次」，最多 4 条。
assert.equal(multiRounds, 4)
assert.equal(multiRoundSeconds, 25)
assert.equal(multiWindowSeconds, 100)
assert.equal(multiLines.length, 4)
assert.equal(multiTitle, '可以射。多少次都行')
assert.equal(multiEndText, '结束')
assert.equal(multiDoneBody, '如果一直到最后都没停手，就算成功。')
assert.equal(multiRoundLabel(1), '第1次 / 4')
assert.equal(multiRoundLabel(4, 4), '第4次 / 4')

// —— restSeconds / randomBpm / planFocus / pickIndex ——
assert.equal(restSeconds({ mode: 'fixed', seconds: 12, min: 8, max: 16 }, zeros), 12)
assert.equal(restSeconds({ mode: 'random', seconds: 12, min: 8, max: 16 }, zeros), 8)
assert.equal(restSeconds({ mode: 'random', seconds: 12, min: 8, max: 16 }, nines), 16)
assert.equal(restSeconds({ mode: 'random', seconds: 12, min: 16, max: 8 }, zeros), 8, '上下限颠倒也能自动纠正')
const slowBpm = randomBpm({ min: 60, max: 160 }, 'slow', zeros)
const goBpm = randomBpm({ min: 60, max: 160 }, 'go', nines)
assert.equal(slowBpm, 60, '慢慢来取区间下半段')
assert.equal(goBpm, 160, '可以撸取区间上半段')
assert.equal(randomBpm({ min: 60, max: 160 }, 'go', zeros), 110, '起点是区间中点')
assert.equal(randomBpm({ min: 20, max: 300 }, 'go', zeros) % 5, 0, '结果是 5 的倍数')
// 触发点 = 总时长 × (比率 + 抖动)，抖动为 (random()-0.5)×0.16(乳头)/0.12(龟头)。
assert.deepEqual(planFocus(1, 600000, zeros, 'nipple'), [222000])
assert.deepEqual(planFocus(1, 600000, zeros, 'glans'), [336000])
assert.deepEqual(planFocus(2, 600000, zeros, 'nipple'), [132000, 342000])
assert.equal(planFocus(4, 600000, zeros, 'glans').length, 4)
assert.equal(planFocus(3, 600000, zeros, 'nipple').length, 3)
assert.deepEqual([...planFocus(3, 600000, nines, 'nipple')], [...planFocus(3, 600000, nines, 'nipple')].sort((a, b) => a - b), '触发点必须升序')
assert.equal(pickIndex([], zeros), null)
assert.equal(pickIndex(['a', 'b', 'c'], zeros), 'a')
assert.equal(pickIndex(['a', 'b', 'c'], nines), 'c')

// —— pickMode：首段强制 go、默认禁 stop 连出、mix 时高 stop 放开 ——
const modes: EdgeMode[] = ['go', 'slow', 'stop']
let seenFirst = ''
for (let index = 0; index < 40; index += 1) seenFirst = pickMode({ previous: null, isFirst: true, difficulty: 'normal', tune: null, modes, random: mulberry32(index) }) ?? ''
assert.equal(seenFirst, 'go', '首段必须是可以撸')
for (let index = 0; index < 40; index += 1) {
  const mode = pickMode({ previous: 'stop', isFirst: false, difficulty: 'normal', tune: null, modes, random: mulberry32(index) })
  assert.notEqual(mode, 'stop', '普通难度不允许不许碰连出')
}
assert.equal(pickMode({ previous: 'stop', isFirst: false, difficulty: 'normal', tune: null, modes: ['stop'], random: fixed(0) }), null, '没有可选相位时返回 null')
// 手调 mix 到 stop 50% 时应当放开连出。
const heavyStop = pickMode({ previous: 'stop', isFirst: false, difficulty: 'normal', tune: { chance: null, stop: null, mix: { go: 25, slow: 25, stop: 50 } }, modes: ['stop'], random: fixed(0) })
assert.equal(heavyStop, 'stop', '不许碰占比 >45% 时允许连出')

// —— pickCommandAt：只抽同相位、不重复上一条 ——
const pool = maleCommands
for (const mode of modeOrder) {
  const picked = pickCommandAt(mode, fixed(0), null, pool)
  assert.ok(picked && picked.mode === mode, `${mode} 抽到的口令相位必须一致`)
}
const goFirst = pickCommandAt('go', fixed(0), null, pool)
assert.ok(goFirst)
const goSecond = pickCommandAt('go', fixed(0), goFirst, pool)
assert.notEqual(goSecond?.text, goFirst.text, '不能连续抽到同一条口令')

// —— swapHands / commandPool / filterByCategories ——
assert.equal(swapHands('用右手撸'), '用左手撸')
assert.equal(swapHands('左手包住'), '右手包住')
assert.equal(swapHands('没有手字'), '没有手字')
const full = commandPool([], [], 'right')
assert.equal(full.length, maleCommands.length, '关掉清单为空时就是全量')
assert.equal(commandPool([0, 1], [], 'right').length, maleCommands.length - 2)
assert.equal(commandPool([], [], 'right')[0]!.text, maleCommands[0]!.text)
assert.equal(commandPool([], [], 'left')[0]!.text, swapHands(maleCommands[0]!.text), '左手要整体对调')
assert.equal(commandPool([], [{ text: '  自定义  ', mode: 'go' }], 'right').at(-1)!.text, '自定义', '自定义口令要去空白')
assert.equal(commandPool([], [{ text: '   ', mode: 'go' }], 'right').length, maleCommands.length, '空自定义口令被丢弃')
// —— 道具模式：飞机杯剔除只能用手/必须握柱身的指令，按摩器追加红色段 ——
const toyPool = commandPool([], [], 'right', maleCommands, { toy: true })
assert.equal(toyPool.some(item => item.bareHand), false, '开飞机杯后不能留只能用手的指令')
assert.equal(toyPool.some(item => item.shaft), false, '开飞机杯后不能留必须握柱身的指令')
assert.equal(toyPool.length, maleCommands.length - 10 + toyCommands.length, '飞机杯把 10 条手用指令换成 20 条专属指令')
assert.equal(commandPool([], [], 'right', maleCommands, { toy: true })[maleCommands.length - 10]!.text, toyCommands[0]!.text)
const anerosPool = commandPool([], [], 'right', maleCommands, { aneros: true })
assert.equal(anerosPool.length, maleCommands.length + anerosCommands.length)
assert.equal(anerosPool.at(-1)!.text, anerosCommands.at(-1)!.text)
assert.equal(commandPool([1000], [], 'right', maleCommands, { toy: true }).some(item => item.text === toyCommands[0]!.text), false, '道具指令也要能逐条停用')
assert.equal(toyCommands.length, 20)
assert.equal(anerosCommands.length, 6)
assert.equal(anerosCommands.every(item => item.mode === 'stop'), true, '按摩器指令全是红色段')
assert.equal(toyCommands.filter(item => item.edge).length, 3, '飞机杯有 3 条寸止指令')
const filtered = filterByCategories(full, { edge: true, tease: false, pose: false, pain: false })
assert.ok(filtered.every(item => item.category === 'basic' || item.category === 'edge'), '关掉的分类必须被过滤')
assert.equal(filterByCategories(full, { edge: true, tease: true, pose: true, pain: true }).length, full.length, '全开时不过滤')

// —— 指令池本身 ——
assert.equal(maleCommands.length, 88)
assert.equal(maleCommands.filter(item => item.mode === 'go').length + maleCommands.filter(item => item.mode === 'slow').length + maleCommands.filter(item => item.mode === 'stop').length, 88)
for (const command of maleCommands) {
  assert.ok(command.text.length > 0, '每条口令都要有文本')
  assert.ok(modeOrder.includes(command.mode), '相位必须是 go/slow/stop')
  // bpm 是逐条可选字段：没有的就沿用播放器的节拍；有就必须落在合法区间。
  if (command.bpm !== undefined) assert.ok(command.bpm >= 20 && command.bpm <= 300, 'bpm 必须落在 20–300')
  if (command.seconds !== undefined) assert.ok(command.seconds >= 1 && command.seconds <= 300, 'seconds 必须落在 1–300')
}
assert.equal(maleCommands.filter(item => item.bpm !== undefined).length >= 60, true, '多数口令自带 bpm')
assert.equal(maleCommands.filter(item => item.mode === 'go').length > 20, true, '可以撸的口令应占多数')
assert.equal(maleCommands.filter(item => item.edge).length, 3, '带 edge 标记的寸止口令有 3 条')
assert.equal(maleCommands[0]!.text, '用平常的速度撸。')
assert.equal(maleCommands[0]!.bpm, 90)

// —— buildTimeline：铺满整段时间、末尾并段、相位合法 ——
const timeline = buildTimeline({ seed: 7, totalMs: 600000, difficulty: 'normal', tune: null, length: 'standard' })
assert.ok(timeline.length > 10, '10 分钟应当切出足够多的段')
assert.equal(timeline[0]!.index, 0)
assert.equal(timeline[0]!.at, 0)
assert.equal(timeline[0]!.mode, 'go', '首段必须是可以撸')
for (let index = 1; index < timeline.length; index += 1) {
  const previous = timeline[index - 1]!
  const current = timeline[index]!
  assert.equal(current.index, index)
  assert.ok(current.at > previous.at, '时间点必须递增')
  assert.ok(modeOrder.includes(current.mode))
  if (previous.mode === 'stop' && current.mode === 'stop') {
    assert.equal(difficulties.normal.stopAfterStop, false, '普通难度不该出现不许碰连出')
  }
}
const last = timeline.at(-1)!
assert.ok(last.at < 600000, '最后一段必须落在总时长内')
assert.ok((last.at + last.seconds * 1000) >= 600000, '最后一段必须铺到结尾')
assert.ok(last.seconds >= finalHoldMs / 1000, '结尾不允许出现小于 5 秒的残段')
// 同种子复现、不同种子不同。
const again = buildTimeline({ seed: 7, totalMs: 600000, difficulty: 'normal', tune: null, length: 'standard' })
assert.deepEqual(timeline.map(item => [item.at, item.seconds, item.mode]), again.map(item => [item.at, item.seconds, item.mode]))
const other = buildTimeline({ seed: 8, totalMs: 600000, difficulty: 'normal', tune: null, length: 'standard' })
assert.notDeepEqual(timeline.map(item => item.at), other.map(item => item.at))
// 长时间档必须拉长单段。
const longTimeline = buildTimeline({ seed: 7, totalMs: 600000, difficulty: 'normal', tune: null, length: 'long' })
assert.ok(longTimeline.length < timeline.length, '长指令档应当让段数变少')

// —— bindCommands：把口令绑进时间线、自带 seconds 时改写并顺移 ——
const bound = bindCommands(timeline.map(item => ({ ...item })), pool)
assert.ok(bound.every(item => item.command), '每段都要绑上口令')
for (const task of bound) {
  assert.equal(task.command!.mode, task.focus === 'glans' ? 'slow' : task.focus === 'nipple' ? 'stop' : task.mode)
}
const withSeconds = bindCommands([{ index: 0, at: 0, seconds: 5, mode: 'go', command: null, edge: false, focus: null }, { index: 1, at: 5000, seconds: 10, mode: 'go', command: null, edge: false, focus: null }], [{ text: '一条 60 秒的口令', mode: 'go', category: 'basic', bpm: 90, seconds: 60 }])
assert.equal(withSeconds[0]!.seconds, 60, '口令自带时长要覆盖')
assert.equal(withSeconds[1]!.at, 60000, '后续时间点要顺移')
assert.equal(withSeconds[0]!.edge, false, '没有 edge 标记就不是寸止段')

// —— taskAt：二分定位 ——
assert.equal(taskAt(timeline, -1)?.index, 0)
assert.equal(taskAt(timeline, 0)?.index, 0)
const secondTask = timeline[1]!
assert.equal(taskAt(timeline, secondTask.at)?.index, 1)
assert.equal(taskAt(timeline, secondTask.at + 1)?.index, 1)
assert.equal(taskAt(timeline, 599999)?.index, timeline.length - 1)
assert.equal(taskAt([], 0), null)

// —— formatClock ——
assert.equal(formatClock(0), '0:00')
assert.equal(formatClock(1000), '0:01')
assert.equal(formatClock(61000), '1:01')
assert.equal(formatClock(600000), '10:00')
assert.equal(formatClock(-5), '0:00')

// —— 设置：默认值、夹取、存取 ——
assert.equal(edgeStorageKey, 'shicun.edge.v1')
assert.equal(edgeSchemaVersion, 1)
const defaults = defaultEdgeSettings
assert.equal(defaults.minutes, 10)
assert.equal(defaults.difficulty, 'normal')
assert.equal(defaults.finale, 'draw')
assert.equal(defaults.instructionLength, 'standard')
assert.equal(defaults.rewardSeconds, 10)
assert.equal(defaults.rest.mode, 'random')
assert.equal(defaults.rest.min, 8)
assert.equal(defaults.rest.max, 16)
assert.equal(defaults.hand, 'right')
assert.equal(defaults.beatVolume, 100)
assert.equal(defaults.metronome, true)
assert.equal(defaults.heartbeat, true)
assert.equal(defaults.nipple.on, false)
assert.equal(defaults.glans.on, false)
assert.deepEqual(defaults.categories, { edge: true, tease: true, pose: true, pain: false })
const normalized = normalizeEdgeSettings({
  minutes: 999, difficulty: 'impossible', finale: 'nope', instructionLength: 'nope', beatVolume: 9999,
  heartbeatVolume: -5, brightness: 0, mediaVolume: 500, rewardSeconds: 999, hand: 'both',
  rest: { mode: 'fixed', seconds: 999, min: 200, max: 1 }, disabled: [3, 3, 1, -2], tune: { chance: 5, stop: 90, mix: { go: 50, slow: 30, stop: 30 } }
})
assert.equal(normalized.minutes, 180)
assert.equal(normalized.difficulty, 'normal')
assert.equal(normalized.finale, 'draw')
assert.equal(normalized.instructionLength, 'standard')
assert.equal(normalized.beatVolume, 300)
assert.equal(normalized.heartbeatVolume, 0)
assert.equal(normalized.brightness, 20)
assert.equal(normalized.mediaVolume, 100)
assert.equal(normalized.rewardSeconds, 60)
assert.equal(normalized.hand, 'right')
assert.equal(normalized.rest.seconds, 120)
assert.equal(normalized.rest.min <= normalized.rest.max, true, 'rest 上下限必须纠正顺序')
assert.deepEqual(normalized.disabled, [1, 3], '停用下标要去重排序')
assert.equal(normalized.tune.chance, 10, '手调许可率下限 10')
assert.equal(normalized.tune.stop, 60, '手调不许碰上限 60')
assert.equal(normalized.tune.mix, null, '三项和不为 100 的 mix 必须丢弃')
assert.equal(defaults.bpmRandom.on, false)
assert.equal(defaults.bpmRandom.min, 60)
assert.equal(defaults.bpmRandom.max, 160)
assert.equal(defaults.heartbeatSync, true)
const ranged = normalizeEdgeSettings({ bpmRandom: { on: true, min: 999, max: 10 }, heartbeatSync: false })
assert.equal(ranged.bpmRandom.on, true)
assert.equal(ranged.bpmRandom.max, 300, '每次变换节奏上限 300')
assert.equal(ranged.bpmRandom.min, 10 < 20 ? 20 : ranged.bpmRandom.min, '每次变换节奏下限 20')
assert.equal(ranged.bpmRandom.min <= ranged.bpmRandom.max, true, 'bpmRandom 上下限必须纠正顺序')
assert.equal(ranged.heartbeatSync, false)
// 每次变换节奏：开启后绿黄指令的 BPM 落在范围内且是 5 的倍数；红色不动。
const varySource = { text: '快一点。别停。', mode: 'go' as const, category: 'basic' as const, bpm: 90 }
const varied = varyBpm(varySource, { on: true, min: 60, max: 160 }, mulberry32(7))!
assert.equal(varied.bpm! >= 60 && varied.bpm! <= 160, true, '变换节奏的 BPM 必须落在范围内')
assert.equal(varied.bpm! % 5, 0, '变换节奏的 BPM 必须是 5 的倍数')
assert.equal(varied.bpm! >= 110, true, '绿色只取较快的一半')
assert.equal(varyBpm(varySource, { on: false, min: 60, max: 160 }, mulberry32(7))!.bpm, 90, '关掉后原样返回')
assert.equal(varyBpm({ ...varySource, mode: 'stop' as const }, { on: true, min: 60, max: 160 }, mulberry32(7))!.bpm, 90, '红色不参与变换节奏')
assert.equal(normalizeEdgeSettings(null).minutes, 10, '整体损坏时退回默认值')
assert.equal(normalizeEdgeSettings({ custom: [{ text: 'x'.repeat(100), mode: 'go' }] }).custom[0]!.text.length, 60, '自定义口令截断到 60 字')
assert.equal(normalizeEdgeSettings({ custom: Array.from({ length: 50 }, () => ({ text: '口令', mode: 'go' })) }).custom.length, 30, '自定义口令上限 30 条')
// 存取：写成功返回空串，读回与写入一致。
const storage = new Map<string, string>()
const stub = {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => { storage.set(key, value) },
} as unknown as Storage
const originalStorage = (globalThis as { localStorage?: Storage }).localStorage
Object.defineProperty(globalThis, 'localStorage', { value: stub, configurable: true })
assert.equal(writeEdgeSettings({ ...defaults, minutes: 25, difficulty: 'hard' }), '')
const stored = storage.get(edgeStorageKey)
assert.ok(stored, '写入后必须能在 localStorage 里找到')
const restored = readEdgeSettings(stored ?? null)
assert.equal(restored.minutes, 25)
assert.equal(restored.difficulty, 'hard')
// 空值与坏 JSON 都不能抛错，一律退回默认值。
assert.equal(readEdgeSettings(null).minutes, 10)
assert.equal(readEdgeSettings('{broken').minutes, 10)
Object.defineProperty(globalThis, 'localStorage', { value: originalStorage, configurable: true })

// —— EdgeSession：推进、忍住、射了、结局 ——
const session = new EdgeSession({ ...defaults, seed: 1234, minutes: 1 })
assert.equal(session.finished, false)
assert.ok(session.tasks.length > 0)
assert.equal(session.totalMs, 60000, '最短一局 1 分钟')
assert.equal(session.permit, 0.7)
const opening = session.frame()
assert.equal(opening.mode, 'go', '开局必须是可以撸')
assert.ok(opening.task && opening.task.index === 0)
assert.ok(opening.taskProgress >= 0 && opening.taskProgress <= 1)
// 忍住一次：次数 +1、进入等它平息、许可率 +5%。
assert.equal(session.hold(), true)
assert.equal(session.held, 1)
assertClose(session.permit, 0.75)
assert.equal(session.cooling, true)
const cooling = session.frame()
assert.equal(cooling.mode, 'stop', '忍住后要切到不许碰')
assert.equal(cooling.text, '松手。等它平息。')
// 冷却结束战斗后恢复原相位。
for (let index = 0; index < 30; index += 1) session.tick(1000)
assert.equal(session.cooling, false)
// 时间到：抽签；这里用固定种子走真实随机，只断言进入了 allow 或 done。
for (let index = 0; index < 120; index += 1) session.tick(1000)
if (session.phase === 'allow') {
  assert.ok(session.outcome === null || session.outcome === 'allow')
  for (let index = 0; index < 20; index += 1) session.tick(1000)
}
assert.equal(session.phase === 'done' || session.phase === 'allow', true)
// 射了：直接判负。
const lost = new EdgeSession({ ...defaults, seed: 99, minutes: 1 })
lost.lose()
assert.equal(lost.outcome, 'lost')
assert.equal(lost.finished, true)
// 必不允许：时间到即失败。
const never = new EdgeSession({ ...defaults, seed: 5, minutes: 1, finale: 'never' })
for (let index = 0; index < 70; index += 1) never.tick(1000)
assert.equal(never.outcome, 'deny')
assert.equal(never.finished, true)
// 必定允许：时间到进入许可窗口，并在窗口结束后收尾。
const always = new EdgeSession({ ...defaults, seed: 5, minutes: 1, finale: 'always', rewardSeconds: 5 })
for (let index = 0; index < 61; index += 1) always.tick(1000)
assert.equal(always.phase, 'allow', '必定允许应当进入许可窗口')
assert.ok(always.windowLeft > 0 && always.windowLeft <= 5)
for (let index = 0; index < 6; index += 1) always.tick(1000)
assert.equal(always.outcome, 'allow')
assert.equal(always.finished, true)
// 松手射精：也走许可窗口（参考站的松手收场同样弹奖励屏，只是文案不同），窗口结束后以 ruin 收尾。
const ruin = new EdgeSession({ ...defaults, seed: 5, minutes: 1, finale: 'ruin', rewardSeconds: 5 })
for (let index = 0; index < 61; index += 1) ruin.tick(1000)
assert.equal(ruin.phase, 'allow', '松手射精应当进入许可窗口')
assert.equal(ruin.ruined, true, '松手射精的奖励屏要走 ruin 文案')
for (let index = 0; index < 6; index += 1) ruin.tick(1000)
assert.equal(ruin.outcome, 'ruin')
assert.equal(ruin.finished, true)
// 随机时长：每局在 5～20 分钟之间决定，不再看 minutes。
const randomDuration = new EdgeSession({ ...defaults, seed: 7, minutes: 90, durationRandom: true })
assert.ok(randomDuration.totalMs >= 5 * 60_000 && randomDuration.totalMs <= 20 * 60_000, '随机时长应当落在 5～20 分钟')
assert.equal(randomDuration.totalMs % 60_000, 0, '随机时长按整分钟取')
const fixedDuration = new EdgeSession({ ...defaults, seed: 7, minutes: 90, durationRandom: false })
assert.equal(fixedDuration.totalMs, 90 * 60_000, '没开随机就用设定分钟数')

// 连续（多少次都行）：许可窗口固定 100 秒，里面每 25 秒切到下一条「再来一次」，最多 4 条；
// 100 秒走完按成功收场（不再自动开下一轮）。
const multi = new EdgeSession({ ...defaults, seed: 11, minutes: 1, finale: 'continuous', rewardSeconds: 5 })
for (let index = 0; index < 61; index += 1) multi.tick(1000)
assert.equal(multi.phase, 'allow', '连续结局也先弹许可屏')
assert.equal(multi.multi, true, '连续结局的许可屏走多轮文案')
assert.equal(multi.windowTotal, multiWindowSeconds, '连续结局的窗口固定 100 秒')
assert.equal(multi.multiRound, 1, '刚进窗口是第 1 次')
for (let index = 0; index < 25; index += 1) multi.tick(1000)
assert.equal(multi.multiRound, 2, '过 25 秒切到第 2 次')
for (let index = 0; index < 25; index += 1) multi.tick(1000)
assert.equal(multi.multiRound, 3, '再过 25 秒切到第 3 次')
for (let index = 0; index < 25; index += 1) multi.tick(1000)
assert.equal(multi.multiRound, multiRounds, '第 75 秒切到第 4 次（最多 4 条）')
for (let index = 0; index < 100; index += 1) multi.tick(1000)
assert.equal(multi.finished, true, '100 秒走完就收场')
assert.equal(multi.outcome, 'allow', '连续结局窗口走完算成功')

// 加时赛：没抽中不会以禁止收场，而是加时（先插一条 6 秒红色指令），最多 5 次后必给许可。
const extendRun = new EdgeSession({
  ...defaults, seed: 3, minutes: 1, difficulty: 'hell', finale: 'overtime', extendLen: 'normal', rewardSeconds: 5
})
let lastExtends = 0
let sawExtendHead = false
let sawExtendNote = false
for (let index = 0; index < 4000 && !extendRun.finished; index += 1) {
  const beforeTotal = extendRun.totalMs
  extendRun.tick(1000)
  if (extendRun.extends > lastExtends) {
    lastExtends = extendRun.extends
    const head = extendRun.tasks[0]!
    assert.equal(head.mode, 'stop', '加时抽出的指令是红色')
    assert.equal(head.seconds, extendLineSeconds, '加时指令固定 6 秒')
    assert.ok(extendLines.includes(head.command?.text ?? ''), '加时文案取自 lines')
    assert.equal(head.at, beforeTotal, '加时从原来的结束时刻接着走')
    assert.ok(extendRun.totalMs > beforeTotal, '加时后总时长变长')
    sawExtendHead = true
    if (extendRun.note.startsWith('加时第')) sawExtendNote = true
  }
}
assert.ok(sawExtendHead, '困难难度下应当至少加时一次')
assert.ok(sawExtendNote, '加时时要写明第几次')
assert.ok(lastExtends <= 5, '最多加时 5 次')
assert.notEqual(extendRun.outcome, 'deny', '加时赛不会以禁止结束')
assert.equal(extendRun.finished, true)

// —— 口吻：按第几条指令轮流、前后各自随机、寸止指令不加后置 ——
assert.deepEqual(toneOrder, ['strong', 'tease', 'abuse', 'sweet', 'feet'])
assert.deepEqual(Object.keys(toneLabels), toneOrder.slice())
assert.deepEqual(Object.keys(toneNotes), toneOrder.slice())
for (const lines of [strongLines, teaseLines, abuseLines, sweetLines, feetLines]) {
  for (const mode of ['go', 'slow', 'stop'] as const) {
    assert.ok(lines[mode].before.length >= 3, `${mode} 前置短句至少 3 条`)
    assert.ok(lines[mode].after.length >= 2, `${mode} 后置短句至少 2 条`)
  }
}
assert.ok(abuseLines.nipple.before.length >= 3, '辱骂口吻要有乳头专用短句')
const noTones = { strong: false, tease: false, abuse: false, sweet: false, feet: false }
assert.equal(toneForTask(noTones, 1), 'normal')
assert.equal(toneForTask({ ...noTones, strong: true }, 1), 'strong')
// 同时开两种时按第几条轮流。
const twoTones = { ...noTones, strong: true, tease: true }
assert.deepEqual([1, 2, 3, 4].map(count => toneForTask(twoTones, count)), ['strong', 'tease', 'strong', 'tease'])
const toneZeros = () => 0
assert.deepEqual(pickToneLine(strongLines.go, toneZeros, { before: true, after: 'always' }), { before: '动。', after: '再骚一点。' })
assert.deepEqual(pickToneLine(strongLines.go, toneZeros, { before: false, after: 'half' }), { after: '再骚一点。' })
assert.deepEqual(pickToneLine(strongLines.go, toneZeros, { before: false, after: 'never' }), {})
assert.equal(toneAfterForCommand({ category: 'edge' }, 'always'), 'never', '寸止指令不加后置短句')
assert.equal(toneAfterForCommand({ category: 'basic' }, 'always'), 'always')
// 会话里：开了口吻就有前后短句，同一条指令重复取到同一句。
const toned = new EdgeSession({ ...defaults, seed: 42, minutes: 1, tones: { ...noTones, strong: true } })
const tonedFrame = toned.frame()
assert.ok(tonedFrame.toneBefore.length > 0, '开了口吻后要在指令前给出短句')
assert.equal(tonedFrame.tone, 'strong')
assert.equal(toned.frame().toneBefore, tonedFrame.toneBefore, '同一条指令的口吻短句要稳定')
// 关掉就不出现。
const plain = new EdgeSession({ ...defaults, seed: 42, minutes: 1 })
assert.equal(plain.frame().tone, 'normal')
assert.equal(plain.frame().toneBefore, '')
assert.equal(plain.frame().toneAfter, '')

// 本机成绩：只统计成功 / 松手 / 禁止三种结局，分钟数与忍住次数累加。
assert.deepEqual(emptyStats, { sessions: 0, success: 0, ruin: 0, fail: 0, edges: 0, minutes: 0, longest: 0 })
const statsOnce = addSession(emptyStats, 'allow', 10, 3)
assert.deepEqual(statsOnce, { sessions: 1, success: 1, ruin: 0, fail: 0, edges: 3, minutes: 10, longest: 10 })
assert.deepEqual(addSession(statsOnce, 'deny', 4, 1), { sessions: 2, success: 1, ruin: 0, fail: 1, edges: 4, minutes: 14, longest: 10 })
assert.equal(addSession(statsOnce, 'ruin', 2, 0).ruin, 1)
assert.equal(addSession(statsOnce, 'lost', 2, 0).sessions, 2, '中途射了也算一局')
assert.equal(addSession(statsOnce, 'lost', 2, 0).success, statsOnce.success, '中途射了不算成功')
assert.equal(statsSummary(emptyStats), '', '没玩过就不显示成绩')
assert.ok(statsSummary(statsOnce).includes('至今 1 次'), '有成绩时显示局数')
assert.deepEqual(normalizeStats({ sessions: -3, success: 2.6, longest: 'x' }), { sessions: 0, success: 3, ruin: 0, fail: 0, edges: 0, minutes: 0, longest: 0 })
assert.deepEqual(readStats('not json'), emptyStats, '坏数据当没玩过')

// 镜子：默认关闭、place 只认 bg/corner，关掉或离页就停流。
assert.equal(defaults.mirror.on, false)
assert.equal(defaults.mirror.place, 'corner')
assert.deepEqual(normalizeEdgeSettings({ mirror: { on: true, place: 'bg' } }).mirror, { on: true, place: 'bg' })
assert.deepEqual(normalizeEdgeSettings({ mirror: { on: 'yes', place: 'left' } }).mirror, { on: false, place: 'corner' })
assert.equal(mirrorPlaceFor('bg', true), 'corner', '播放视频时镜子固定到右下角')
assert.equal(mirrorPlaceFor('bg', false), 'bg')
assert.equal(mirrorPlaceFor('corner', false), 'corner')
assert.equal(classifyMirrorError({ name: 'NotAllowedError' }), 'denied')
assert.equal(classifyMirrorError({ name: 'NotFoundError' }), 'none')
assert.equal(classifyMirrorError({ name: 'TypeError' }), 'unsupported')
assert.equal(classifyMirrorError({ name: 'NotReadableError' }), 'busy')
assert.equal(classifyMirrorError(null), 'busy')
assert.deepEqual(MIRROR_CONSTRAINTS, { video: { facingMode: 'user' }, audio: false })
assert.deepEqual(mirrorPlaces, ['bg', 'corner'])
assert.equal(mirrorPlaceLabels.bg, '铺满背景（调暗）')
assert.equal(mirrorPlaceLabels.corner, '右下角小窗')
assert.ok(mirrorText.consentYes.includes('允许'), '同意文案要说明会打开摄像头')
{
  // 「射了」的记录：次数 +1、最长取大，只有不是第一次且更久才算破纪录。
  assert.deepEqual(emptyLost, { count: 0, bestMs: 0 })
  const first = addLost(emptyLost, 90_000)
  assert.deepEqual(first.next, { count: 1, bestMs: 90_000 })
  assert.equal(first.isBest, false, '第一次没有可比对象，不算破纪录')
  const second = addLost(first.next, 120_000)
  assert.equal(second.isBest, true)
  assert.deepEqual(second.next, { count: 2, bestMs: 120_000 })
  const third = addLost(second.next, 60_000)
  assert.equal(third.isBest, false, '这次更短，不算破纪录')
  assert.deepEqual(third.next, { count: 3, bestMs: 120_000 })
  assert.deepEqual(normalizeLost({ count: -4, bestMs: 'x' }), emptyLost)
  assert.deepEqual(normalizeLost(null), emptyLost)
  assert.deepEqual(readLost('not json'), emptyLost)
  assert.deepEqual(readLost('{"count":3,"bestMs":180000}'), { count: 3, bestMs: 180_000 })
  // 完成度最多显示 99%，避免看成已完成。
  assert.equal(lostPct(30_000, 10), 5)
  assert.equal(lostPct(600_000, 10), 99)
  assert.equal(lostPct(0, 10), 0)
  assert.equal(lostPct(30_000, 0), 0)
}
{
  // 停流必须逐个 track 停掉，否则摄像头指示灯不灭。
  const stopped: string[] = []
  const stream = { getTracks: () => [{ id: 'a', stop: () => stopped.push('a') }, { id: 'b', stop: () => stopped.push('b') }] } as unknown as MediaStream
  stopStream(stream)
  assert.deepEqual(stopped, ['a', 'b'])
  stopStream(null)
}

{
  // 单部位模式：整局只出该部位的专属指令，且不再插入中途的专属段。
  assert.deepEqual(focusAreas, ['none', 'nipple', 'glans'])
  assert.equal(focusLabels.nipple, '只玩乳头')
  assert.equal(focusAllowBelow, '现在可以摸下面了。')
  assert.ok(focusNippleCommands.length >= 15, '乳头专属池要有足够条数')
  assert.ok(focusGlansCommands.length >= 12, '龟头专属池要有足够条数')
  assert.ok(focusNippleCommands.every(item => item.category === 'nipple' || item.category === 'edge'))
  assert.ok(focusGlansCommands.every(item => item.category === 'glans' || item.category === 'edge'))
  const nippleRun = new EdgeSession({ ...defaults, seed: 21, minutes: 3, focus: 'nipple', nipple: { on: true, times: 2 } })
  assert.ok(nippleRun.tasks.every(task => task.focus === null), '单部位模式不再插入中途专属段')
  assert.ok(nippleRun.tasks.every(task => (task.command?.category === 'nipple' || task.command?.category === 'edge')),
    '单部位模式整局只出乳头指令')
  const glansRun = new EdgeSession({ ...defaults, seed: 21, minutes: 3, focus: 'glans', glans: { on: true, times: 2 } })
  assert.ok(glansRun.tasks.every(task => task.focus === null))
  assert.ok(glansRun.tasks.every(task => (task.command?.category === 'glans' || task.command?.category === 'edge')),
    '单部位模式整局只出龟头指令')
  // 只玩乳头拿到许可时才有「现在可以摸下面了」。
  assert.equal(nippleRun.allowBelow, '')
  nippleRun.held = 0
  nippleRun.phase = 'allow'
  assert.equal(nippleRun.allowBelow, focusAllowBelow)
  nippleRun.ruined = true
  assert.equal(nippleRun.allowBelow, '', '松手射精时不提示可以摸下面')
}

// ---- 连续天数（每日打卡）----
{
  const base = new Date(2026, 10, 20, 12).getTime()
  assert.equal(dayKey(base), '2026-11-20')
  assert.equal(daysBetween('2026-11-20', '2026-11-21'), 1)
  assert.equal(daysBetween('2026-11-20', '2026-11-20'), 0)
  assert.equal(daysBetween('2026-11-20', '2026-11-19'), -1)
  // 坏数据一律归零
  assert.deepEqual(normalizeDays(null), { last: '', run: 0, best: 0 })
  assert.deepEqual(normalizeDays({ last: 'x', run: 9, best: 9 }), { last: '', run: 0, best: 0 })
  assert.deepEqual(normalizeDays({ last: '2026-11-20', run: 0, best: 0 }), { last: '2026-11-20', run: 1, best: 1 })
  assert.equal(readDays('not json').run, 0)
  assert.equal(readDays(null).best, 0)
  // 首次玩就是 1 天
  const first = addDay(emptyDays, base)
  assert.deepEqual(first.next, { last: '2026-11-20', run: 1, best: 1 })
  assert.deepEqual(first.view, { run: 1, best: 1, today: true })
  // 同一天再玩不加
  assert.deepEqual(addDay(first.next, base).next, first.next)
  // 隔一天 +1
  const second = addDay(first.next, new Date(2026, 10, 21, 9).getTime())
  assert.deepEqual(second.next, { last: '2026-11-21', run: 2, best: 2 })
  // 断一天就清零
  const gap = addDay(second.next, new Date(2026, 10, 23, 9).getTime())
  assert.deepEqual(gap.next, { last: '2026-11-23', run: 1, best: 2 }, '断一天清零但最高纪录保留')
  // daysView 只看不改
  assert.deepEqual(daysView(first.next, base), { run: 1, best: 1, today: true })
  assert.deepEqual(daysView(first.next, new Date(2026, 10, 22, 0, 30).getTime()), { run: 0, best: 1, today: false })
  // 里程碑
  assert.equal(nextMilestone(0), 3)
  assert.equal(nextMilestone(2), 3)
  assert.equal(nextMilestone(3), 7)
  assert.equal(nextMilestone(29), 30)
  assert.equal(nextMilestone(30), 60)
  // 剩余小时：至少 1，且不超过 24
  const hours = hoursLeftToday(base)
  assert.ok(hours >= 1 && hours <= 24, `剩余小时应当在 1…24，得到 ${hours}`)
  // 摘要：没玩过 / 今天已玩 / 明天再来
  const cold = daysSummary(emptyDays, base)
  assert.equal(cold[0], daysText.fresh)
  assert.ok(cold.some(line => line.includes('今天还剩')))
  const warm = daysSummary(first.next, base)
  assert.equal(warm[0], '已连续 1 天')
  assert.ok(warm.includes(daysText.doneToday))
  const tomorrow = daysSummary(first.next, new Date(2026, 10, 21, 8).getTime())
  assert.ok(tomorrow.some(line => line.includes('今天玩就是第 2 天')))
  // 存取往返
  const store = new Map<string, string>()
  const stub = { getItem: (key: string) => store.get(key) ?? null, setItem: (key: string, value: string) => void store.set(key, value), removeItem: (key: string) => void store.delete(key) }
  const original = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { value: stub, configurable: true })
  try {
    assert.equal(writeDays(first.next), '')
    assert.equal(store.get(daysStorageKey), JSON.stringify(first.next))
    assert.deepEqual(readDays(store.get(daysStorageKey) ?? null), first.next)
  } finally {
    if (original) Object.defineProperty(globalThis, 'localStorage', original)
    else delete (globalThis as { localStorage?: unknown }).localStorage
  }
}

// ---- 历史成绩（最近 30 条 + 累计）----
{
  assert.deepEqual(recordOrder, ['success', 'ruin', 'fail', 'lost'])
  // 结局映射与参考站一致
  assert.equal(recordOutcome('allow'), 'success')
  assert.equal(recordOutcome('duration'), 'success')
  assert.equal(recordOutcome('ruin'), 'ruin')
  assert.equal(recordOutcome('lost'), 'lost')
  assert.equal(recordOutcome('deny'), 'fail')
  assert.equal(recordOutcome('manual'), 'fail')
  assert.equal(recordOutcome('queue'), 'fail')
  // 累计：第一次玩时 seeded 变成 true，序号从 1 开始
  const counted = countResult(emptyTally, 'allow')
  assert.equal(counted.nth, 1)
  assert.deepEqual(counted.next, { n: 1, r: { success: 1, ruin: 0, fail: 0, lost: 0 }, seeded: true })
  assert.equal(countResult(counted.next, 'lost').nth, 2)
  assert.equal(countResult(counted.next, 'lost').next.r.lost, 1)
  // 旧成绩迁移：seeded 为真就不再动
  const seeded = { n: 7, r: { success: 3, ruin: 1, fail: 2, lost: 1 }, seeded: true }
  assert.equal(tallyFromStats(seeded, 10, 5, 2, 3, 1), seeded)
  const migrated = tallyFromStats(emptyTally, 2, 1, 0, 1, 1)
  assert.deepEqual(migrated, { n: 3, r: { success: 1, ruin: 0, fail: 1, lost: 1 }, seeded: false })
  // 详细记录的解析：坏数据丢掉、按时间倒序、最多 30 条
  const sample = { t: 1_700_000_000_000, o: 'success', m: 10, c: 24, e: 3, d: 'normal', n: 5 }
  assert.deepEqual(parseRecords([sample])[0], { ...sample })
  assert.deepEqual(parseRecords([{ ...sample, o: 'win' }]), [], '未知结局丢掉')
  assert.deepEqual(parseRecords([{ ...sample, t: 0 }]), [], '没有时间戳丢掉')
  assert.deepEqual(parseRecords(null), [])
  const older = { ...sample, t: sample.t - 1000 }
  const sorted = parseRecords([older, sample])
  assert.equal(sorted[0].t, sample.t)
  // 夹取与可选字段
  const clamped = parseRecords([{ t: sample.t, o: 'lost', m: 999, c: -5, e: 9999, d: 'nope', n: -1, ms: 90_000, x: 2, k: true }])[0]
  assert.equal(clamped.m, 180)
  assert.equal(clamped.c, 0)
  assert.equal(clamped.e, 99)
  assert.equal(clamped.d, 'normal')
  assert.equal(clamped.n, 0)
  assert.equal(clamped.ms, 90_000)
  assert.equal(clamped.x, 2)
  assert.equal(clamped.k, true)
  assert.equal(parseRecords([{ ...sample, o: 'success' }])[0].ms, undefined, '非中途结束不写 ms')
  // 只留最近 30 条
  const many = Array.from({ length: 40 }, (_, index) => ({ ...sample, t: sample.t + index }))
  const kept = pushRecord(parseRecords(many.slice(0, 30)), { ...sample, t: sample.t + 100 })
  assert.equal(kept.length, 30)
  assert.equal(kept[0].t, sample.t + 100)
  assert.equal(parseRecords(many).length, 30)
  // 集章
  assert.deepEqual(stamps(1), { index: 1, sheets: 0 })
  assert.deepEqual(stamps(10), { index: 10, sheets: 0 })
  assert.deepEqual(stamps(11), { index: 1, sheets: 1 })
  assert.deepEqual(stamps(25), { index: 5, sheets: 2 })
  // 时间文案
  const stamp = new Date(2026, 10, 25, 10, 32).getTime()
  assert.equal(recordTime(stamp), '2026/11/25 10:32')
  // 文案齐备
  // 推荐预设的说明文案
  assert.deepEqual(presetOrder, ['first', 'standard', 'long'])
  assert.equal(presetNotes.first, '5分钟·简单·必定允许。关闭寸止指令和姿势类指令')
  assert.equal(presetNotes.standard, '10分钟·普通·抽签（默认）')
  assert.equal(presetNotes.long, '20分钟·困难·抽签')
  assert.equal(presetNone, '自定义设置')
  // 悬浮小窗提示（pipOffer / pipSite）
  assert.equal(defaults.pipOffer, true)
  assert.equal(defaults.pipSite, '')
  assert.equal(normalizeEdgeSettings({ pipOffer: false }).pipOffer, false)
  assert.equal(normalizeEdgeSettings({ pipSite: ' https://example.com/watch ' }).pipSite, 'https://example.com/watch')
  assert.equal(normalizeEdgeSettings({ pipSite: 'example.com' }).pipSite, '')
  assert.equal(normalizeEdgeSettings({ pipSite: 'javascript:alert(1)' }).pipSite, '')
  assert.equal(normalizeEdgeSettings({ pipSite: 42 }).pipSite, '')
  assert.equal(normalizeEdgeSettings({ pipSite: `https://a.test/${'x'.repeat(300)}` }).pipSite.length, 200)
  assert.equal(recordsText.title, '历史成绩')
  assert.equal(recordsText.empty, '还没有详细记录。从下一局开始保存。')
  // 存取往返
  const store2 = new Map<string, string>()
  const stub2 = { getItem: (key: string) => store2.get(key) ?? null, setItem: (key: string, value: string) => void store2.set(key, value), removeItem: (key: string) => void store2.delete(key) }
  const original2 = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { value: stub2, configurable: true })
  try {
    assert.equal(writeRecords([sample]), '')
    assert.equal(store2.get(recordsStorageKey), JSON.stringify([sample]))
    assert.deepEqual(readRecords(store2.get(recordsStorageKey) ?? null), [sample])
    assert.equal(writeTally(counted.next), '')
    assert.deepEqual(readTally(store2.get(tallyStorageKey) ?? null), counted.next)
    assert.deepEqual(readRecords('not json'), [])
    assert.deepEqual(readTally('not json'), emptyTally)
  } finally {
    if (original2) Object.defineProperty(globalThis, 'localStorage', original2)
    else delete (globalThis as { localStorage?: unknown }).localStorage
  }
}

console.log('edge engine checks passed')
