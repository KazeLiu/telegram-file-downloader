// 全部音效由 WebAudio 振荡器实时合成，与参考实现一致：不加载任何音频文件。
// 节拍 go 用 880Hz、slow 用 520Hz；提示音是 660/990Hz 双音；心跳是 58→38Hz 双下潜。
export interface SoundOptions {
  /** 0–300，100 为基准音量 */
  beatVolume: number
  /** 0–300 */
  heartbeatVolume: number
  /** 视频音量 0–100，用于「边听音乐边玩」时的压低 */
  duck?: () => number
}

export class SoundEngine {
  private context: AudioContext | null = null
  private master: GainNode | null = null
  private keepAlive: AudioBufferSourceNode | null = null
  private suspended = false

  get currentTime() {
    return this.context?.currentTime ?? 0
  }

  get ready() {
    return !!this.context
  }

  /** 必须由用户手势触发：浏览器只在手势里允许创建 / 恢复 AudioContext。 */
  async ensure(): Promise<AudioContext | null> {
    if (!this.context) {
      const Ctor = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctor) return null
      this.context = new Ctor()
      this.master = this.context.createGain()
      this.master.gain.value = 1
      this.master.connect(this.context.destination)
      this.startKeepAlive()
    }
    if (this.context.state === 'suspended' && !this.suspended) await this.context.resume().catch(() => undefined)
    return this.context
  }

  // 某些移动浏览器会在空闲后挂起音频；用一个空 buffer 常驻保持运行。
  private startKeepAlive() {
    if (!this.context || !this.master || this.keepAlive) return
    const buffer = this.context.createBuffer(1, 1, 22050)
    const source = this.context.createBufferSource()
    source.buffer = buffer
    source.loop = true
    const gain = this.context.createGain()
    gain.gain.value = 0.0001
    source.connect(gain).connect(this.master)
    source.start(0)
    this.keepAlive = source
  }

  async suspend() {
    this.suspended = true
    await this.context?.suspend().catch(() => undefined)
  }

  async resume() {
    this.suspended = false
    await this.context?.resume().catch(() => undefined)
  }

  close() {
    try {
      this.keepAlive?.stop()
    } catch {
      // 忽略：已经停止
    }
    this.keepAlive = null
    this.context?.close().catch(() => undefined)
    this.context = null
    this.master = null
  }

  private envelope(value: number) {
    return Math.max(0.0001, Math.min(1, value))
  }

  /** 节拍：慢速 520Hz、可以撸 880Hz，短促衰减。 */
  beat(mode: 'go' | 'slow' | 'stop' = 'go', options: SoundOptions) {
    const context = this.context
    const master = this.master
    if (!context || !master) return
    const now = context.currentTime
    const volume = 0.5 * (options.beatVolume / 100) * (options.duck?.() ?? 1)
    const osc = context.createOscillator()
    const gain = context.createGain()
    osc.type = 'sine'
    osc.frequency.value = mode === 'slow' ? 520 : 880
    gain.gain.setValueAtTime(1e-4, now)
    gain.gain.exponentialRampToValueAtTime(this.envelope(volume), now + 0.005)
    gain.gain.exponentialRampToValueAtTime(1e-4, now + 0.06)
    osc.connect(gain).connect(master)
    osc.start(now)
    osc.stop(now + 0.07)
  }

  /** 提示音：660Hz + 990Hz 双音，用于换指令 / 许可发放。 */
  cue(options: SoundOptions) {
    const context = this.context
    const master = this.master
    if (!context || !master) return
    const now = context.currentTime
    const volume = 0.4 * (options.beatVolume / 100) * (options.duck?.() ?? 1)
    ;[660, 990].forEach((frequency, index) => {
      const osc = context.createOscillator()
      const gain = context.createGain()
      const start = now + 0.14 * index
      osc.type = 'sine'
      osc.frequency.value = frequency
      gain.gain.setValueAtTime(1e-4, start)
      gain.gain.exponentialRampToValueAtTime(this.envelope(volume), start + 0.01)
      gain.gain.exponentialRampToValueAtTime(1e-4, start + 0.3)
      osc.connect(gain).connect(master)
      osc.start(start)
      osc.stop(start + 0.32)
    })
  }

  /** 心跳：两次下潜式低频撞击。 */
  heartbeat(options: SoundOptions) {
    const context = this.context
    const master = this.master
    if (!context || !master) return
    const level = Math.max(0, Math.min(3, options.heartbeatVolume / 100))
    const now = context.currentTime
    const thump = (start: number, amplitude: number) => {
      const osc = context.createOscillator()
      const gain = context.createGain()
      osc.type = 'sine'
      osc.frequency.setValueAtTime(58, start)
      osc.frequency.exponentialRampToValueAtTime(38, start + 0.12)
      gain.gain.setValueAtTime(1e-4, start)
      gain.gain.exponentialRampToValueAtTime(this.envelope(Math.max(2e-4, amplitude * level)), start + 0.012)
      gain.gain.exponentialRampToValueAtTime(1e-4, start + 0.14)
      osc.connect(gain).connect(master)
      osc.start(start)
      osc.stop(start + 0.16)
    }
    thump(now, 0.9)
    thump(now + 0.17, 0.55)
  }
}
