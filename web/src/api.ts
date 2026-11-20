export const PLATFORMS: Record<string, string> = { douyin: '抖音', xhs: '小红书', sph: '视频号' }

export async function api<T = any>(path: string, opts: { method?: string; body?: any } = {}): Promise<T> {
  const r = await fetch('/api' + path, {
    method: opts.method || (opts.body ? 'POST' : 'GET'),
    headers: opts.body ? { 'Content-Type': 'application/json' } : undefined,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  if (r.status === 401 && !path.startsWith('/auth/')) {
    // 网页版：没登录或登录过期，去登录页
    if (location.pathname !== '/login') location.href = '/login'
    throw new Error('请先登录')
  }
  if (!r.ok) {
    let msg = r.statusText
    try { const j = await r.json(); msg = j.detail || JSON.stringify(j) } catch {}
    throw new Error(msg)
  }
  return r.json()
}

export function fmtNum(n?: number | null): string {
  if (n === null || n === undefined) return '—'
  if (n >= 1e8) return (n / 1e8).toFixed(1) + '亿'
  if (n >= 1e4) return (n / 1e4).toFixed(n >= 1e5 ? 0 : 1) + 'w'
  return String(n)
}

export function fmtTime(t?: number | null, withTime = true): string {
  if (!t) return '—'
  const d = new Date(t * 1000)
  const p = (x: number) => String(x).padStart(2, '0')
  const s = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
  return withTime ? `${s} ${p(d.getHours())}:${p(d.getMinutes())}` : s
}

export function ago(t?: number | null): string {
  if (!t) return '—'
  const s = Date.now() / 1000 - t
  if (s < 0) return '即将'
  if (s < 60) return '刚刚'
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} 天前`
  return fmtTime(t, false)
}

export function until(t?: number | null): string {
  if (!t) return '—'
  const s = t - Date.now() / 1000
  if (s <= 0) return '马上'
  if (s < 3600) return `${Math.ceil(s / 60)} 分钟后`
  if (s < 86400) return `${Math.round(s / 3600)} 小时后`
  return `${Math.round(s / 86400)} 天后`
}

export function fmtDur(s?: number | null): string {
  if (!s) return '—'
  return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`
}

export function engagement(c: any): number | null {
  const base = c.views
  if (!base) return null
  return ((c.likes || 0) + (c.comments || 0) + (c.saves || 0) + (c.shares || 0)) / base
}
