import assert from 'node:assert/strict'
import {
  builtinCommands, commandPool, commandTypeLabels, difficultyOrder, difficultyProfiles, edgeWindowOptions, endingHints,
  endingLabels, endingOrder, instructionPaceRatios, nextPermitRate, overtimeLimit, overtimeStep, permitMaxGain, permitStep,
  phaseDurationMs, pickCommand, pickPhaseKind, propLabels, resolveEnding, toneLabels, vibrateLabels, voicePitchLabels,
  waitDurationMs, waitPresets
} from '../src/playback/edge.ts'
import { phaseOrder, type PhaseKind } from '../src/playback/types.ts'

// 固定种子的伪随机，保证断言可复现。
function seeded(seed: number) {
  let state = seed >>> 0
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0
    return state / 0x1_0000_0000
  }
}

// —— 常量口径 ——
assert.equal(permitStep, 5)
assert.equal(permitMaxGain, 20)
assert.equal(overtimeStep, 15)
assert.equal(overtimeLimit, 5)
assert.deepEqual(edgeWindowOptions, [5, 10, 20, 30, 45, 60])
assert.deepEqual(difficultyOrder, ['easy', 'normal', 'hard', 'hell'])
assert.deepEqual(endingOrder, ['draw', 'always', 'never', 'ruin', 'continuous', 'overtime'])
assert.deepEqual(instructionPaceRatios, { standard: 1, long: 1.5, veryLong: 2.5 })
assert.deepEqual(Object.keys(endingLabels), endingOrder)
assert.deepEqual(Object.keys(toneLabels), ['firm', 'tease', 'degrade', 'gentle'])
assert.deepEqual(Object.keys(commandTypeLabels), ['fast', 'slow', 'rest', 'tease', 'nipple', 'glans'])
assert.deepEqual(Object.keys(voicePitchLabels), ['auto', 'low', 'normal', 'high'])
assert.deepEqual(Object.keys(vibrateLabels), ['off', 'switch', 'edge', 'ending'])
for (const ending of endingOrder) assert.ok(endingHints[ending]!.length > 0, `${ending} 要有说明`)
for (const profile of Object.values(difficultyProfiles)) {
  assert.equal(profile.fast + profile.slow + profile.rest, 100, `${profile.label} 三比例合计 100`)
}
assert.equal(difficultyProfiles.normal.fast, 60)
assert.equal(difficultyProfiles.normal.slow, 20)
assert.equal(difficultyProfiles.normal.rest, 20)
assert.equal(difficultyProfiles.normal.permit, 70)
assert.deepEqual(
  waitPresets.map(item => [item.id, item.min, item.max]),
  [['8-16', 8, 16], ['10-40', 10, 40], ['20-60', 20, 60]]
)
assert.equal(propLabels.cup, '飞机杯')
assert.equal(propLabels.aneros, '前列腺按摩器')

// —— 内置口令：六类各 4 条、id 与类型对应、每条 ≤18 字 ——
assert.equal(builtinCommands.length, 24)
assert.equal(new Set(builtinCommands.map(command => command.id)).size, 24)
for (const type of Object.keys(commandTypeLabels) as (keyof typeof commandTypeLabels)[]) {
  assert.equal(builtinCommands.filter(command => command.type === type).length, 4, `${type} 各 4 条`)
}
for (const command of builtinCommands) {
  assert.match(command.id, new RegExp(`^${command.type}-[1-4]$`))
  assert.ok(command.text.length > 0 && command.text.length <= 18, `${command.id} 文案长度`)
}

// —— nextPermitRate：每忍住一次 +5%，最多 +20%，总数不超过 100 ——
assert.equal(nextPermitRate(70, 0), 70)
assert.equal(nextPermitRate(70, 1), 75)
assert.equal(nextPermitRate(70, 4), 90)
assert.equal(nextPermitRate(70, 5), 90)
assert.equal(nextPermitRate(70, 100), 90)
assert.equal(nextPermitRate(95, 3), 100)
assert.equal(nextPermitRate(30, 0), 30)
assert.equal(nextPermitRate(30, 2.9), 40)
assert.equal(nextPermitRate(30, -3), 30)
assert.equal(nextPermitRate(0, 1), 5)

// —— pickPhaseKind：三比例抽签、不连续同相位、零比例不选中 ——
const steady = () => 0.6
assert.equal(pickPhaseKind(100, 0, 0, null, steady), 'fast')
assert.equal(pickPhaseKind(0, 100, 0, null, steady), 'slow')
assert.equal(pickPhaseKind(0, 0, 100, null, steady), 'rest')
// 只有一档可选时无法避免重复，但不会返回不存在的相位。
assert.equal(pickPhaseKind(100, 0, 0, 'fast', steady), 'fast')
// 重抽仍相同 → 顺延到 phaseOrder 里的下一个非零相位。
assert.equal(pickPhaseKind(50, 50, 0, 'fast', steady), 'slow')
assert.equal(pickPhaseKind(50, 0, 50, 'rest', steady), 'fast')
// 全零：没有比例时按固定次序兜底，且尽量不重复。
assert.equal(pickPhaseKind(0, 0, 0, null, steady), 'fast')
assert.equal(pickPhaseKind(0, 0, 0, 'fast', steady), 'slow')
// 负数按 0 处理。
assert.equal(pickPhaseKind(-10, 100, 0, null, steady), 'slow')

const phaseRandom = seeded(7)
const phaseCount: Record<PhaseKind, number> = { slow: 0, fast: 0, rest: 0 }
let previousPhase: PhaseKind | null = null
for (let index = 0; index < 4000; index++) {
  const kind = pickPhaseKind(60, 20, 20, previousPhase, phaseRandom)
  assert.notEqual(kind, previousPhase, '相邻两段不得同相位')
  phaseCount[kind] = (phaseCount[kind] ?? 0) + 1
  previousPhase = kind
}
assert.ok(phaseCount.fast > phaseCount.slow, '快速段应最多')
assert.ok(phaseCount.slow > 0 && phaseCount.rest > 0)

// 合计不为 100 时按归一化处理：2:1:1 的快速约占一半。
const normalRandom = seeded(11)
let normalizedFast = 0
for (let index = 0; index < 2000; index++) {
  if (pickPhaseKind(2, 1, 1, null, normalRandom) === 'fast') normalizedFast++
}
assert.ok(normalizedFast > 900 && normalizedFast < 1100, `归一化后快速占比 ${normalizedFast}`)

// —— phaseDurationMs：rest 不乘指令时长倍率，fast/slow 乘倍率 ——
assert.equal(phaseDurationMs('rest', 'standard', () => 0), 10_000)
assert.equal(phaseDurationMs('rest', 'standard', () => 0.999999), 16_000)
assert.equal(phaseDurationMs('rest', 'long', () => 0.5), 13_000)
assert.equal(phaseDurationMs('rest', 'veryLong', () => 0), 10_000)
assert.equal(phaseDurationMs('fast', 'standard', () => 0), 18_000)
assert.equal(phaseDurationMs('fast', 'long', () => 0), 27_000)
assert.equal(phaseDurationMs('fast', 'veryLong', () => 0), 45_000)
assert.equal(phaseDurationMs('slow', 'long', () => 0.999999), 46_500)

const durationRandom = seeded(3)
for (let index = 0; index < 500; index++) {
  const rest = phaseDurationMs('rest', 'veryLong', durationRandom)
  assert.ok(rest >= 10_000 && rest <= 16_000, `rest 时长越界 ${rest}`)
  const fast = phaseDurationMs('fast', 'standard', durationRandom)
  assert.ok(fast >= 18_000 && fast <= 31_000, `fast 时长越界 ${fast}`)
  const slow = phaseDurationMs('slow', 'veryLong', durationRandom)
  assert.ok(slow >= 45_000 && slow <= 77_500, `slow 时长越界 ${slow}`)
}

// —— resolveEnding：六种结局分支 ——
for (let index = 1; index < 20; index++) {
  const value = index / 20
  assert.equal(resolveEnding('always', 0, () => value), 'allow')
  assert.equal(resolveEnding('never', 100, () => value), 'deny')
}
assert.equal(resolveEnding('ruin', 70, () => 0.49), 'ruin')
assert.equal(resolveEnding('ruin', 70, () => 0.5), 'deny')
assert.equal(resolveEnding('draw', 70, () => 0.699), 'allow')
assert.equal(resolveEnding('draw', 70, () => 0.7), 'deny')
assert.equal(resolveEnding('draw', 0, () => 0), 'deny')
assert.equal(resolveEnding('draw', 100, () => 0.999999), 'allow')
assert.equal(resolveEnding('continuous', 70, () => 0.1), 'allow')
assert.equal(resolveEnding('continuous', 70, () => 0.9), 'deny')
assert.equal(resolveEnding('overtime', 0, () => 0.99), 'deny')
assert.equal(resolveEnding('overtime', 0, () => 0.99, 4), 'deny')
assert.equal(resolveEnding('overtime', 0, () => 0.99, 5), 'allow')
assert.equal(resolveEnding('overtime', 100, () => 0.99, 0), 'allow')
// 不传 random 时用 Math.random 兜底，返回合法判定。
assert.ok(['allow', 'deny', 'ruin'].includes(resolveEnding('draw', 50)))

// —— waitDurationMs：随机档落在预设区间内，固定档用给定最短／最长 ——
assert.equal(waitDurationMs('random', '8-16', 0, 0, () => 0), 8_000)
assert.equal(waitDurationMs('random', '8-16', 100, 3, () => 0.999999), 16_000)
assert.equal(waitDurationMs('fixed', '8-16', 40, 80, () => 0), 40_000)
assert.equal(waitDurationMs('fixed', '8-16', 40, 80, () => 0.5), 60_000)
assert.equal(waitDurationMs('fixed', '8-16', 40, 20, () => 0), 20_000)

const waitRandom = seeded(5)
for (const preset of waitPresets) {
  for (let index = 0; index < 300; index++) {
    const ms = waitDurationMs('random', preset.id, 0, 0, waitRandom)
    assert.ok(ms >= preset.min * 1000 && ms <= preset.max * 1000, `${preset.id} 越界 ${ms}`)
  }
}

// —— commandPool：按类型取内置、跳过禁用、自定义追加在后 ——
const restPool = commandPool(['rest'], [], ['rest-2'])
assert.equal(restPool.length, 3)
assert.ok(restPool.every(command => command.type === 'rest'))
assert.equal(restPool.some(command => command.id === 'rest-2'), false)
assert.deepEqual(commandPool([], [], []), [])
const customPool = commandPool(['fast'], [{ text: '自己写的一条', type: 'fast' }, { text: '类型没开', type: 'tease' }], [])
assert.equal(customPool.length, 5)
assert.equal(customPool.at(-1)!.id, 'custom-1')
assert.equal(customPool.at(-1)!.text, '自己写的一条')
assert.equal(customPool.some(command => command.text === '类型没开'), false)
assert.equal(commandPool(['fast'], [{ text: '只留自定义', type: 'fast' }], ['fast-1', 'fast-2', 'fast-3', 'fast-4']).length, 1)

// —— pickCommand：不重复上一条，池空返回 null ——
assert.equal(pickCommand([], 'none'), null)
const singlePool = [{ id: 'only', type: 'rest' as const, text: '停' }]
assert.equal(pickCommand(singlePool, 'only', () => 0)!.id, 'only')
const pickRandom = seeded(9)
const seenIds = new Set<string>()
let lastId = ''
for (let index = 0; index < 2000; index++) {
  const command = pickCommand(builtinCommands, lastId, pickRandom)!
  assert.notEqual(command.id, lastId, '不重复上一条')
  seenIds.add(command.id)
  lastId = command.id
}
assert.equal(seenIds.size, builtinCommands.length)
assert.equal(pickCommand(builtinCommands, '不存在', () => 0)!.id, builtinCommands[0]!.id)
assert.equal(pickCommand(builtinCommands, builtinCommands[0]!.id, () => 0)!.id, builtinCommands[1]!.id)
