// 运行时口吻台词：雌小鬼式的居高临下、催促与嘲讽。
// 只做语气层（挑衅、数落、威胁重来），不含性描写；具体动作指令见 edge.ts 的 builtinCommands。

export type VoiceMoment =
  | 'start'
  | 'phase-fast'
  | 'phase-slow'
  | 'phase-rest'
  | 'held'
  | 'ending-allow'
  | 'ending-deny'

export interface VoiceLine {
  /** 台词正文，念出来用 */
  text: string
  /** 出现的时机 */
  when: VoiceMoment
}

/** 全体台词：每条都保持「你在我手里」的压迫感，靠语气而不是描写 */
export const mesugakiLines: VoiceLine[] = [
  { when: 'start', text: '开始了哦，别一副很想的样子。' },
  { when: 'start', text: '接下来听我的，我说什么你做什么。' },
  { when: 'start', text: '撑到最后再来得意吧。' },

  { when: 'phase-fast', text: '快一点，我又没说可以慢。' },
  { when: 'phase-fast', text: '就这样，别停，停了就重来。' },
  { when: 'phase-fast', text: '跟得上吗？跟不上也没关系，我会等你的。' },
  { when: 'phase-fast', text: '手别抖，看着就不太行的样子。' },

  { when: 'phase-slow', text: '慢下来，谁让你一直那么急了。' },
  { when: 'phase-slow', text: '一下一下地来，急的人看起来最可怜。' },
  { when: 'phase-slow', text: '这么想快点结束？偏不。' },
  { when: 'phase-slow', text: '收着点，别把自己弄得太狼狈。' },

  { when: 'phase-rest', text: '停，手拿开，听不懂吗？' },
  { when: 'phase-rest', text: '松手，放好，我还没说可以。' },
  { when: 'phase-rest', text: '忍一下又不会怎样，这么娇气。' },
  { when: 'phase-rest', text: '别偷偷碰，我数着呢。' },

  { when: 'held', text: '哦——这次倒是忍住了，第几次了？' },
  { when: 'held', text: '就这点出息，还以为你能早点认输。' },
  { when: 'held', text: '忍住了？那就再来一次，反正你也没得选。' },
  { when: 'held', text: '别以为忍一次就有奖励，还早得很。' },
  { when: 'held', text: '手放好，看着我，别急着高兴。' },

  { when: 'ending-allow', text: '行吧，看在你这么努力的份上。' },
  { when: 'ending-allow', text: '允许你了，谢我也没用。' },

  { when: 'ending-deny', text: '时间到了。忍到结束也没用哦。' },
  { when: 'ending-deny', text: '就到这儿，什么都没给你留。下次再说吧。' },
]

/** 按时机取一条台词；同一时机内随机，可选地避开上一条 */
export function pickVoiceLine(
  when: VoiceMoment,
  random: () => number = Math.random,
  lastText = '',
): string | null {
  const pool = mesugakiLines.filter((line) => line.when === when && line.text !== lastText)
  const source = pool.length > 0 ? pool : mesugakiLines.filter((line) => line.when === when)
  if (source.length === 0) return null
  const pick = source[Math.min(source.length - 1, Math.floor(random() * source.length))]
  return pick ? pick.text : null}
