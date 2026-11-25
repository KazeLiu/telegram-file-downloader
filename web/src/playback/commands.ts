// 男生版内置口令池：与 100adults 男生版逐条对应（88 条）。
// text/mode/category/bpm/seconds/edge 来自同一份官方数据结构，hint 使用官方中文文案。
export type EdgeMode = 'go' | 'slow' | 'stop'
export type EdgeCategory = 'basic' | 'edge' | 'tease' | 'pose' | 'pain' | 'nipple' | 'glans' | 'custom'

export interface EdgeCommand {
  text: string
  mode: EdgeMode
  category: EdgeCategory
  bpm?: number
  seconds?: number
  edge?: boolean
  hint?: string
  /** 只能用手直接做（开道具模式时整条剔除） */
  bareHand?: boolean
  /** 必须握着柱身（开道具模式时整条剔除） */
  shaft?: boolean
}

export const maleCommands: EdgeCommand[] = [
  { text: "用平常的速度撸。", mode: "go", category: "basic", bpm: 90 },
  { text: "快一点。别停。", mode: "go", category: "basic", bpm: 150 },
  { text: "用尽全力，越快越好。", mode: "go", category: "basic", bpm: 190, seconds: 10 },
  { text: "接着刚才的。别乱了节奏。", mode: "go", category: "basic", bpm: 100 },
  { text: "换另一只手。", mode: "go", category: "basic", bpm: 80 },
  { text: "快慢交替，边数边撸。", mode: "go", category: "basic", bpm: 120 },
  { text: "握紧，加快。", mode: "go", category: "basic", bpm: 140 },
  { text: "只撸冠状沟那一圈，快一点。", mode: "go", category: "tease", bpm: 150, bareHand: true },
  { text: "跟着节拍。一拍一下。", mode: "go", category: "basic", bpm: 110, hint: "光和声音就是节拍。别慢也别抢" },
  { text: "慢慢来。上下都慢慢撸，仔细感受。", mode: "slow", category: "basic", bpm: 20 },
  { text: "只摸龟头。用指尖。", mode: "slow", category: "tease", bpm: 30, bareHand: true },
  { text: "紧握根部，别动。", mode: "slow", category: "basic", seconds: 12 },
  { text: "握松一点，轻轻撸。", mode: "slow", category: "tease", bpm: 40 },
  { text: "用手掌轻轻抚摸，不许撸。", mode: "slow", category: "tease", bpm: 30, bareHand: true },
  { text: "只用两根手指，慢慢来。", mode: "slow", category: "tease", bpm: 30, bareHand: true },
  { text: "只摸蛋蛋。别碰柱身。", mode: "slow", category: "tease" },
  { text: "速度减半。", mode: "slow", category: "basic", bpm: 50 },
  { text: "撸到快要射的前一刻，停下。", mode: "go", category: "edge", bpm: 110, seconds: 30, edge: true, hint: "忍住了就按“忍住了”。射了就输" },
  { text: "快速撸到快射，最后一刻松手。", mode: "go", category: "edge", bpm: 160, seconds: 25, edge: true, hint: "松开了就按“忍住了”" },
  { text: "慢慢撸到极限。停下，看着它抽动。", mode: "slow", category: "edge", bpm: 40, seconds: 30, edge: true, hint: "忍住了就按“忍住了”" },
  { text: "松手。结束前不许碰。", mode: "stop", category: "basic" },
  { text: "双手抱头。不许碰。", mode: "stop", category: "basic" },
  { text: "立刻松手。", mode: "stop", category: "basic", seconds: 5 },
  { text: "深呼吸。手放膝盖上。", mode: "stop", category: "basic", seconds: 12 },
  { text: "闭上眼，什么都别碰，等着。", mode: "stop", category: "basic", seconds: 8 },
  { text: "双手捏乳头。下面不许碰。", mode: "stop", category: "tease" },
  { text: "只用手指揉乳头。", mode: "stop", category: "tease" },
  { text: "站起来，双脚与肩同宽。手背在身后。", mode: "stop", category: "pose" },
  { text: "跪坐，盯着屏幕。", mode: "stop", category: "pose", seconds: 12 },
  { text: "摆一个你觉得最羞耻的姿势。", mode: "stop", category: "pose", seconds: 10 },
  { text: "四肢着地趴好，等着。", mode: "stop", category: "pose", seconds: 10 },
  { text: "做俯卧撑直到时间结束。不许碰。", mode: "stop", category: "pose", seconds: 12 },
  { text: "用镜子或前置摄像头看自己。别碰。", mode: "stop", category: "pose", seconds: 10 },
  { text: "轻拍大腿。下面不许碰。", mode: "stop", category: "pain" },
  { text: "轻拍蛋蛋。", mode: "stop", category: "pain", seconds: 10 },
  { text: "用手掌轻拍柱身。", mode: "stop", category: "pain", seconds: 8, shaft: true },
  { text: "用手指刮起前列腺液，抹在龟头上。", mode: "slow", category: "tease", bpm: 30, bareHand: true },
  { text: "可以出声。别忍，一边撸一边叫。", mode: "go", category: "basic", bpm: 120 },
  { text: "挺腰。手别动，自己往里顶。", mode: "go", category: "tease", bpm: 110 },
  { text: "脱掉内裤，张开腿给我看。别碰。", mode: "stop", category: "pose", seconds: 12 },
  { text: "只用一根手指，沿着下面那条筋划。", mode: "slow", category: "tease", bpm: 30, bareHand: true },
  { text: "想象射出来的那一刻，快一点。但不许射。", mode: "go", category: "basic", bpm: 150 },
  { text: "闻闻自己的味道。手指贴在鼻子上，别碰。", mode: "stop", category: "pose", seconds: 10 },
  { text: "想象有人在看着你撸。叫出声，让他们听见。", mode: "go", category: "tease", bpm: 100 },
  { text: "一只手掐着乳头，另一只手撸。", mode: "go", category: "tease", bpm: 120 },
  { text: "只用右手。左手背到身后。", mode: "go", category: "basic", bpm: 110 },
  { text: "用不常用的那只手，慢慢来。感受那种生疏。", mode: "slow", category: "tease", bpm: 40 },
  { text: "用手掌包住蛋蛋，轻轻揉搓。别碰柱身。", mode: "slow", category: "tease", bpm: 30 },
  { text: "用指尖一边一个，慢慢搓蛋蛋。别碰柱身。", mode: "slow", category: "tease" },
  { text: "一只手轻轻揉搓蛋蛋，另一只手慢慢撸。", mode: "slow", category: "tease", bpm: 40 },
  { text: "30秒，用最快的速度撸。不准停。", mode: "go", category: "basic", bpm: 180, seconds: 30 },
  { text: "只用左手，整整一分钟。右手背到身后，不准停。", mode: "go", category: "basic", bpm: 100, seconds: 60 },
  { text: "左手撸，右手捏奶头。", mode: "go", category: "tease", bpm: 110 },
  { text: "轻轻扇自己巴掌。下面不准碰。", mode: "stop", category: "pain", seconds: 8 },
  { text: "只用右手，整整一分钟。左手背到身后，不准停。", mode: "go", category: "basic", bpm: 100, seconds: 60 },
  { text: "像榨精一样，从根部往上慢慢挤到头。到头了，再从根部开始。", mode: "slow", category: "basic", bpm: 40 },
  { text: "只能摸奶头，整整一分钟。下面不准碰，用指尖一直揉。", mode: "stop", category: "tease", bpm: 60, seconds: 60 },
  { text: "轻拍蛋蛋10下。一拍一下，别太用力。", mode: "stop", category: "pain", bpm: 40, seconds: 15 },
  { text: "只用右手，整整三分钟。左手背到身后，不准停。", mode: "go", category: "basic", bpm: 100, seconds: 180 },
  { text: "再快点。用你的极限速度撸20秒，不准停。", mode: "go", category: "basic", bpm: 200, seconds: 20 },
  { text: "把脱下来的袜子捂在鼻子上，闻着味儿，慢慢撸。", mode: "slow", category: "tease", bpm: 40 },
  { text: "用手掌轻拍鸡巴10下。一拍一下，别太用力。", mode: "stop", category: "pain", bpm: 40, seconds: 15, shaft: true },
  { text: "只准撸20下，一边数一边撸。数到20就松手，没有第21下。", mode: "go", category: "basic", bpm: 90, seconds: 15 },
  { text: "伸出舌头，用右手揉乳头。下面不准碰。", mode: "stop", category: "tease" },
  { text: "坐在椅子上，靠着椅背，慢慢撸。", mode: "slow", category: "pose", bpm: 40 },
  { text: "仰面躺下，膝盖立起来撸。", mode: "go", category: "pose", bpm: 100 },
  { text: "站着，腿分开撸。不准坐下。", mode: "go", category: "pose", bpm: 110 },
  { text: "用指甲尖轻轻挠乳头。下面不许碰。", mode: "stop", category: "tease", seconds: 15 },
  { text: "用手指弹乳头。一拍弹一下。下面不许碰。", mode: "stop", category: "tease", bpm: 60, seconds: 15 },
  { text: "一边捏住一侧乳头，一边用手指弹另一侧。下面不许碰。", mode: "stop", category: "tease", bpm: 50 },
  { text: "把舌头伸出来撸。舌头不准缩回去。", mode: "go", category: "tease", bpm: 110 },
  { text: "轻拍自己的屁股10下。一拍一下，别太用力。", mode: "stop", category: "pain", bpm: 40, seconds: 15 },
  { text: "仰面躺下，抱住双腿张开，全部给屏幕看。别碰。", mode: "stop", category: "pose", seconds: 12 },
  { text: "想象是别人的脚在帮你弄，慢慢撸，想着脚底的触感。", mode: "slow", category: "tease", bpm: 40 },
  { text: "把脱下来的袜子套在鸡巴上，隔着袜子撸。", mode: "go", category: "tease", bpm: 100 },
  { text: "吐舌头翻白眼，左手比耶，右手撸。", mode: "go", category: "tease", bpm: 110 },
  { text: "闻着穿过的鞋子里的味道，慢慢撸。", mode: "slow", category: "tease", bpm: 40 },
  { text: "想象自己被脚踩着。像舔脚底一样伸出舌头，慢慢撸。", mode: "slow", category: "tease", bpm: 40 },
  { text: "只用左手二十秒。右手背到身后，不准停。", mode: "go", category: "basic", bpm: 110, seconds: 20 },
  { text: "全程只用左手单手撸。右手不准用。", mode: "go", category: "basic", bpm: 100 },
  { text: "左手右手轮换着撸。每次换手都保持同样的速度。", mode: "go", category: "basic", bpm: 100 },
  { text: "只摸龟头十秒。别握柱身。", mode: "slow", category: "tease", bpm: 40, seconds: 10, bareHand: true },
  { text: "想象恋人正被别人抱着，慢慢撸。", mode: "slow", category: "tease", bpm: 40 },
  { text: "想象恋人说比起你更想选那个人。带着丢脸的表情继续撸。", mode: "go", category: "tease", bpm: 100 },
  { text: "想象恋人和那个人一起羞辱有绿帽癖的你。听着他们的嘲笑，慢慢撸。", mode: "slow", category: "tease", bpm: 40 },
  { text: "想象自己在舔穴，伸出舌头，慢慢撸。", mode: "slow", category: "tease", bpm: 40 },
  { text: "一边扭屁股一边撸。手的速度不许变。", mode: "go", category: "tease", bpm: 100 },
  { text: "右手包住龟头转圈，左手握紧根部，慢慢撸。", mode: "slow", category: "tease", bpm: 40, bareHand: true },
]

// 只玩乳头 / 只玩龟头：参考站在时间线里插入的专属段，各自 5 条，固定 stop / slow。
// 乳头文案取自官方中文文案；龟头 5 条按官方日文池逐条对应写成中文（官方中文 locale 未单列这一池）。
export const nippleCommands: EdgeCommand[] = [
  { text: '只摸乳头。下面不许碰。用指尖搓', mode: 'stop', category: 'nipple', bpm: 60, seconds: 25 },
  { text: '两边乳头，用指尖画圈。下面不许碰', mode: 'stop', category: 'nipple', bpm: 40, seconds: 25 },
  { text: '捏住乳头，力度不变，数着来。一拍一下', mode: 'stop', category: 'nipple', bpm: 60, seconds: 30 },
  { text: '别停。只准碰乳头。手往下伸就算输', mode: 'stop', category: 'nipple', bpm: 90, seconds: 20 },
  { text: '轻轻拉一下乳头，放开。重复。下面不许碰', mode: 'stop', category: 'nipple', bpm: 50, seconds: 25 },
]

export const glansCommands: EdgeCommand[] = [
  { text: '只摸龟头。别碰柱身。用指尖打圈。', mode: 'slow', category: 'glans', bpm: 60, seconds: 25 },
  { text: '用手掌包住龟头，慢慢磨。柱身不许碰。', mode: 'slow', category: 'glans', bpm: 40, seconds: 25 },
  { text: '用指尖像捏一样，轻轻揉龟头。别碰柱身。', mode: 'slow', category: 'glans', bpm: 50, seconds: 25 },
  { text: '在冠状沟处用手指做个圈，只让龟头上下。一拍一下。', mode: 'slow', category: 'glans', bpm: 60, seconds: 30 },
  { text: '别停。只摸龟头。握住柱身就算输。', mode: 'slow', category: 'glans', bpm: 80, seconds: 20 },
]

// 道具模式（飞机杯）：20 条，文案与节拍全部取自官方中文文案。
// 开启后主池里「只能用手直接做」（bareHand）与「必须握着柱身」（shaft）的指令会被剔除。
export const toyCommands: EdgeCommand[] = [
  { text: "用平常的速度，从根部到顶端来回套", mode: "go", category: "basic", bpm: 80 },
  { text: "快。插到底，别停", mode: "go", category: "basic", bpm: 130 },
  { text: "全力，快到能听见声音", mode: "go", category: "basic", bpm: 170, seconds: 10 },
  { text: "浅浅地，只让龟头快速进出", mode: "go", category: "tease", bpm: 140 },
  { text: "推到最深，一边转一边动", mode: "go", category: "tease", bpm: 70 },
  { text: "跟着节拍。一拍一个来回", mode: "go", category: "basic", bpm: 100, hint: "光和声音就是节拍。别慢也别抢" },
  { text: "握紧杯子夹住，快", mode: "go", category: "basic", bpm: 120 },
  { text: "杯子别动，自己挺腰往里顶", mode: "go", category: "tease", bpm: 100 },
  { text: "动到极限前一步，停", mode: "go", category: "edge", bpm: 110, seconds: 30, edge: true, hint: "忍住了就按“忍住了”。射了就输" },
  { text: "快速动到快射，最后一刻拔出来", mode: "go", category: "edge", bpm: 150, seconds: 25, edge: true, hint: "拔出来了就按“忍住了”" },
  { text: "慢。从根部到顶端，慢慢来", mode: "slow", category: "basic", bpm: 25 },
  { text: "插到底别动。感受它夹紧", mode: "slow", category: "basic", seconds: 12 },
  { text: "只放进龟头，慢慢进出。不许插深", mode: "slow", category: "tease", bpm: 30 },
  { text: "握松一点，慢慢来。不够也要忍", mode: "slow", category: "tease", bpm: 35 },
  { text: "速度减半。腰别动", mode: "slow", category: "basic", bpm: 45 },
  { text: "补一点润滑液。补完再慢慢开始", mode: "slow", category: "basic", seconds: 12 },
  { text: "慢慢动到极限。停下，感受它在里面一跳一跳", mode: "slow", category: "edge", bpm: 35, seconds: 30, edge: true, hint: "忍住了就按“忍住了”" },
  { text: "停下别动。插着，松手", mode: "stop", category: "basic" },
  { text: "马上拔出来", mode: "stop", category: "basic", seconds: 5 },
  { text: "插着别动。腰也别动", mode: "stop", category: "tease", seconds: 10 },
]

// 前列腺按摩器（Aneros）：6 条，全部是红色段，与官方中文文案逐条对应。
export const anerosCommands: EdgeCommand[] = [
  { text: "按摩器留在里面，松手。跟着节拍，夹紧、放松，反复来", mode: "stop", category: "basic", bpm: 30, seconds: 20 },
  { text: "不许碰。慢慢夹紧按摩器，停5秒，再放松", mode: "stop", category: "basic", seconds: 20 },
  { text: "深吸气，呼气时夹紧。只感受里面的动静", mode: "stop", category: "basic", seconds: 25 },
  { text: "全身放松。等按摩器自己动起来。不许用手", mode: "stop", category: "basic", seconds: 20 },
  { text: "快速、轻轻地夹紧。手放在膝盖上", mode: "stop", category: "basic", bpm: 90, seconds: 15 },
  { text: "捏着乳头，夹紧、放松，反复来。下面不许碰", mode: "stop", category: "tease", bpm: 40, seconds: 20 },
]
