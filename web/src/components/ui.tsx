import clsx from 'clsx'
import { Loader2, X } from 'lucide-react'
import { ReactNode, useEffect } from 'react'
import { PLATFORMS } from '../api'

export function Button({ children, variant = 'default', size = 'md', className, loading, ...p }:
  { variant?: 'default' | 'primary' | 'ghost' | 'danger'; size?: 'sm' | 'md'; loading?: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...p}
      disabled={p.disabled || loading}
      className={clsx(
        'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer',
        size === 'sm' ? 'h-8 px-2.5 text-[13px]' : 'h-9 px-3.5 text-sm',
        variant === 'primary' && 'bg-ink text-lime hover:bg-ink-3',
        variant === 'default' && 'bg-white border border-line hover:border-ink/30 text-ink',
        variant === 'ghost' && 'text-mute hover:text-ink hover:bg-black/5',
        variant === 'danger' && 'bg-white border border-red-200 text-red-600 hover:bg-red-50',
        className,
      )}
    >
      {loading && <Loader2 className="size-3.5 animate-spin" />}
      {children}
    </button>
  )
}

export function Card({ children, className, title, extra, pad = true }: { children: ReactNode; className?: string; title?: ReactNode; extra?: ReactNode; pad?: boolean }) {
  return (
    <section className={clsx('bg-white rounded-xl border border-line', className)}>
      {(title || extra) && (
        <div className="flex items-center justify-between px-4 h-12 border-b border-line">
          <div className="font-semibold text-[15px]">{title}</div>
          <div className="flex items-center gap-2">{extra}</div>
        </div>
      )}
      <div className={pad ? 'p-4' : ''}>{children}</div>
    </section>
  )
}

const PCOLOR: Record<string, string> = {
  douyin: 'bg-ink text-white',
  xhs: 'bg-[#ff2442] text-white',
  sph: 'bg-[#f59a23] text-white',
}
export function PlatformBadge({ p, className }: { p: string; className?: string }) {
  return <span className={clsx('inline-flex items-center rounded px-1.5 h-5 text-[11px] font-medium shrink-0', PCOLOR[p] || 'bg-gray-200', className)}>{PLATFORMS[p] || p}</span>
}

export function Badge({ children, tone = 'gray', className }: { children: ReactNode; tone?: 'gray' | 'lime' | 'red' | 'amber' | 'blue' | 'ink'; className?: string }) {
  return (
    <span className={clsx('inline-flex items-center gap-1 rounded-full px-2 h-5 text-[11px] font-medium whitespace-nowrap', {
      gray: 'bg-black/5 text-mute', lime: 'bg-lime text-ink', red: 'bg-red-50 text-red-600',
      amber: 'bg-amber-50 text-amber-700', blue: 'bg-sky-50 text-sky-700', ink: 'bg-ink text-lime',
    }[tone], className)}>{children}</span>
  )
}

export function Stat({ label, value, sub, accent }: { label: string; value: ReactNode; sub?: ReactNode; accent?: boolean }) {
  return (
    <div className={clsx('rounded-xl p-4 border', accent ? 'bg-ink border-ink text-white' : 'bg-white border-line')}>
      <div className={clsx('text-xs', accent ? 'text-white/60' : 'text-mute')}>{label}</div>
      <div className={clsx('mt-1.5 text-2xl font-semibold num', accent && 'text-lime')}>{value}</div>
      {sub && <div className={clsx('mt-1 text-xs', accent ? 'text-white/50' : 'text-mute')}>{sub}</div>}
    </div>
  )
}

export function Empty({ children, icon }: { children: ReactNode; icon?: ReactNode }) {
  return <div className="flex flex-col items-center justify-center gap-2 py-14 text-sm text-mute">{icon}{children}</div>
}

export function Input(p: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={clsx('h-9 rounded-lg border border-line bg-white px-3 text-sm outline-none focus:border-ink/40 focus:ring-2 focus:ring-lime/60', p.className)} />
}

export function Textarea(p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...p} className={clsx('w-full rounded-lg border border-line bg-white px-3 py-2 text-sm outline-none focus:border-ink/40 focus:ring-2 focus:ring-lime/60', p.className)} />
}

export function Select({ value, onChange, options, className }: { value: any; onChange: (v: string) => void; options: [any, string][]; className?: string }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className={clsx('h-9 rounded-lg border border-line bg-white px-2.5 text-sm outline-none focus:border-ink/40', className)}>
      {options.map(([v, l]) => <option key={String(v)} value={v}>{l}</option>)}
    </select>
  )
}

export function Segmented<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: [T, ReactNode][] }) {
  return (
    <div className="inline-flex rounded-lg bg-black/5 p-0.5">
      {options.map(([v, l]) => (
        <button key={v} onClick={() => onChange(v)}
          className={clsx('h-8 px-3 rounded-md text-sm transition cursor-pointer', value === v ? 'bg-white shadow-sm font-medium' : 'text-mute hover:text-ink')}>{l}</button>
      ))}
    </div>
  )
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode }) {
  return (
    <label className="inline-flex items-center gap-2 cursor-pointer select-none text-sm">
      <span onClick={() => onChange(!checked)} className={clsx('relative w-9 h-5 rounded-full transition', checked ? 'bg-ink' : 'bg-black/15')}>
        <span className={clsx('absolute top-0.5 size-4 rounded-full transition', checked ? 'left-[18px] bg-lime' : 'left-0.5 bg-white')} />
      </span>
      {label && <span onClick={() => onChange(!checked)}>{label}</span>}
    </label>
  )
}

export function Modal({ open, onClose, title, children, footer, width = 480 }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; width?: number }) {
  useEffect(() => {
    const f = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', f)
    return () => window.removeEventListener('keydown', f)
  }, [onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl max-h-[90vh] flex flex-col" style={{ width }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 h-14 border-b border-line">
          <div className="font-semibold">{title}</div>
          <button onClick={onClose} className="text-mute hover:text-ink cursor-pointer"><X className="size-4" /></button>
        </div>
        <div className="p-5 overflow-auto">{children}</div>
        {footer && <div className="flex justify-end gap-2 px-5 py-3 border-t border-line">{footer}</div>}
      </div>
    </div>
  )
}

/** 外部图片统一走后端中转：HEIC 转 JPEG、本地缓存（链接过期也能看）、绕开防盗链。 */
export const imgUrl = (u?: string | null) => (u && /^https?:/.test(u) ? `/api/img?u=${encodeURIComponent(u)}` : u || '')

export function Cover({ src, className, alt = '' }: { src?: string | null; className?: string; alt?: string }) {
  return src ? (
    <img src={imgUrl(src)} alt={alt} referrerPolicy="no-referrer" loading="lazy"
      className={clsx('object-cover bg-black/5', className)}
      onError={(e) => ((e.target as HTMLImageElement).style.visibility = 'hidden')} />
  ) : <div className={clsx('bg-black/5', className)} />
}

export function Avatar({ src, name, size = 32 }: { src?: string | null; name?: string | null; size?: number }) {
  return src ? (
    <img src={imgUrl(src)} referrerPolicy="no-referrer" loading="lazy" className="rounded-full object-cover bg-black/5 shrink-0" style={{ width: size, height: size }} />
  ) : (
    <div className="rounded-full bg-ink text-lime flex items-center justify-center font-semibold shrink-0" style={{ width: size, height: size, fontSize: size * 0.42 }}>
      {(name || '?').slice(0, 1)}
    </div>
  )
}

const STATUS: Record<string, [string, 'gray' | 'lime' | 'red' | 'amber' | 'blue' | 'ink']> = {
  queued: ['排队中', 'gray'], running: ['进行中', 'blue'], done: ['完成', 'lime'], partial: ['部分失败', 'amber'],
  failed: ['失败', 'red'], canceled: ['已取消', 'gray'], interrupted: ['已中断', 'amber'],
}
export function JobStatus({ s }: { s: string }) {
  const [l, t] = STATUS[s] || [s, 'gray']
  return <Badge tone={t}>{s === 'running' && <Loader2 className="size-3 animate-spin" />}{l}</Badge>
}

const TS: Record<string, [string, 'gray' | 'lime' | 'red' | 'amber' | 'blue' | 'ink']> = {
  none: ['未转写', 'gray'], running: ['转写中', 'blue'], done: ['已转写', 'lime'], failed: ['转写失败', 'red'], na: ['图文', 'gray'],
}
export function TranscriptBadge({ s }: { s: string }) {
  const [l, t] = TS[s] || [s, 'gray']
  return <Badge tone={t}>{s === 'running' && <Loader2 className="size-3 animate-spin" />}{l}</Badge>
}

export function PageHeader({ title, desc, extra }: { title: ReactNode; desc?: ReactNode; extra?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4 mb-5">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight">{title}</h1>
        {desc && <p className="mt-1 text-sm text-mute">{desc}</p>}
      </div>
      {extra && <div className="flex items-center gap-2">{extra}</div>}
    </div>
  )
}
