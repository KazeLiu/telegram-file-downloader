export type CloudMedia = { id: string; name: string; kind: 'image' | 'video'; size: number | null; taken_at: number | null; thumbnail?: string }

export function takenAt(value: number | null) {
  return value ? new Date(value).toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }) : '时间未知'
}

export function formatNames(names: string[]) {
  return names.map(name => /[,，"\r\n]|^\s|\s$/.test(name) ? '"' + name.replaceAll('"', '""') + '"' : name).join(', ')
}

export function parseNames(text: string) {
  const names = new Set<string>()
  let end = 0
  for (const match of text.matchAll(/[ \t]*(?:"((?:[^"]|"")*)"|([^",，\r\n]*?))[ \t]*(?:[,，\r\n]+|$)/gy)) {
    end = match.index + match[0].length
    const name = match[1]?.replaceAll('""', '"') ?? match[2]?.trim()
    if (name) names.add(name)
  }
  if (end !== text.length) throw new Error('文件名中的逗号请用双引号包住整个文件名。')
  if (!names.size || names.size > 2000 || [...names].some(name => name.length > 255)) throw new Error('请输入 1–2000 个完整文件名，每个不超过 255 字。')
  return [...names]
}
