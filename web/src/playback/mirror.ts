// 镜子：把前置摄像头的画面左右翻转后显示在屏幕上。
// 画面只在本机使用：不录像、不保存、不上传；暂停、结束或离开页面时立刻关掉摄像头。

export const mirrorPlaces = ['bg', 'corner'] as const
export type MirrorPlace = (typeof mirrorPlaces)[number]

export const mirrorPlaceLabels: Record<MirrorPlace, string> = {
  bg: '铺满背景（调暗）',
  corner: '右下角小窗'
}

export const MIRROR_CONSTRAINTS: MediaStreamConstraints = { video: { facingMode: 'user' }, audio: false }

export type MirrorError = 'denied' | 'none' | 'unsupported' | 'busy'

export const mirrorErrorLabels: Record<MirrorError, string> = {
  denied: '没有获得摄像头权限，已关闭镜子。',
  none: '找不到前置摄像头，已关闭镜子。',
  unsupported: '这个浏览器无法使用摄像头，已关闭镜子（需要 https 和较新的浏览器）。',
  busy: '无法打开摄像头（可能被其他应用占用），已关闭镜子。'
}

/** 镜子的中文文案，文案对齐参考实现。 */
export const mirrorText = {
  legend: '镜子',
  label: '镜子（用前置摄像头看自己）',
  note: '游戏中把前置摄像头的画面左右翻转显示在屏幕上。画面不会离开你的设备（不录像、不保存、不上传）。',
  consentTitle: '将使用前置摄像头',
  consentBody: '画面不会离开你的设备。不录像、不保存、不上传。暂停、结束或离开页面时会关闭摄像头。接下来浏览器会询问，请选择“允许”。',
  consentYes: '允许使用摄像头',
  consentNo: '取消',
  placeLegend: '镜子的位置',
  placeNote: '播放视频时会固定为右下角小窗。',
  aria: '镜子（你的画面，只在本机显示）'
}

/** 探测摄像头可用性：安全上下文 + mediaDevices.getUserMedia。返回错误码或 null（可用）。 */
export function mirrorSupport(): MirrorError | null {
  if (window.isSecureContext === false) return 'unsupported'
  const devices = typeof navigator === 'undefined' ? undefined : navigator.mediaDevices
  return devices && typeof devices.getUserMedia === 'function' ? null : 'unsupported'
}

/** 把 getUserMedia 的异常归类成四种给用户看的说明。 */
export function classifyMirrorError(error: unknown): MirrorError {
  const name = (error as { name?: string } | null)?.name ?? ''
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') return 'denied'
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError' || name === 'OverconstrainedError') return 'none'
  if (name === 'TypeError' || name === 'NotSupportedError') return 'unsupported'
  return 'busy'
}

/** 结束整条流（必须逐个 track 停，否则摄像头指示灯不灭）。 */
export function stopStream(stream: MediaStream | null | undefined) {
  if (!stream) return
  for (const track of stream.getTracks()) {
    try {
      track.stop()
    } catch {
      // 已经停掉的 track 会抛，忽略即可
    }
  }
}

/** 播放视频时镜子固定收到右下角，避免挡住画面。 */
export function mirrorPlaceFor(place: MirrorPlace, playingVideo: boolean): MirrorPlace {
  return playingVideo ? 'corner' : place
}
