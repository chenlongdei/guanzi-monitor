import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Suspense, useEffect, useState } from 'react'
import { BellRing, Hash, LayoutDashboard, Library, Link2, ListChecks, LogOut, Menu, Settings, UserRound, Users, X } from 'lucide-react'
import { Navigate, NavLink, Outlet, useLocation } from 'react-router-dom'
import { api } from '../api'
import { Avatar } from './ui'

const NAV = [
  { to: '/', label: '总览', icon: LayoutDashboard, end: true },
  { to: '/single', label: '单条采集', icon: Link2 },
  { to: '/keyword', label: '关键词', icon: Hash },
  { to: '/blogger', label: '博主', icon: Users },
  { to: '/monitors', label: '监控', icon: BellRing },
  { to: '/library', label: '内容库', icon: Library },
  { to: '/jobs', label: '任务记录', icon: ListChecks },
]

function Item({ to, label, icon: Icon, end, badge }: any) {
  return (
    <NavLink to={to} end={end}
      className={({ isActive }) => clsx('flex items-center gap-2.5 h-9 px-3 rounded-lg text-[14px] transition',
        isActive ? 'bg-lime text-ink font-medium' : 'text-white/65 hover:text-white hover:bg-white/5')}>
      <Icon className="size-4" />
      <span className="flex-1">{label}</span>
      {badge}
    </NavLink>
  )
}

export default function Layout() {
  const { data: s } = useQuery({ queryKey: ['settings'], queryFn: () => api('/settings') })
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: () => api('/auth/me') })
  const { data: running } = useQuery({
    queryKey: ['jobs-running'], refetchInterval: 3000,
    queryFn: () => api<any[]>('/jobs?status=running&limit=20'),
  })
  const n = running?.length || 0
  const loc = useLocation()
  const [open, setOpen] = useState(false)   // 手机上的侧栏抽屉
  useEffect(() => setOpen(false), [loc.pathname])
  if (me?.server && !me.user) return <Navigate to="/login" replace />
  // 还没填数据渠道的 Key：先去欢迎页
  if (s && !s.ready && !s.demo && !['/welcome', '/settings', '/profile'].includes(loc.pathname)) return <Navigate to="/welcome" replace />
  return (
    <div className="flex h-full">
      {open && <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={() => setOpen(false)} />}
      <aside className={clsx('w-[216px] shrink-0 bg-ink flex flex-col z-40',
        'fixed inset-y-0 left-0 transition-transform md:static md:translate-x-0', open ? 'translate-x-0' : '-translate-x-full')}>
        <div className="px-5 pt-5 pb-4 relative">
          <button className="md:hidden absolute right-3 top-4 text-white/60 p-1" onClick={() => setOpen(false)} aria-label="关闭菜单"><X className="size-5" /></button>
          <img src="/logo-white.png" alt="观自行深" className="h-[26px] w-auto" />
          <div className="mt-2 flex items-center gap-1.5 text-[11px] leading-tight">
            <span className="rounded bg-lime text-ink font-semibold px-1.5 py-0.5">监控台</span>
            <span className="text-white/40">抖音 · 小红书 · 视频号</span>
          </div>
        </div>
        <nav className="flex-1 px-3 py-2 space-y-0.5">
          {NAV.map((x) => (
            <Item key={x.to} {...x} badge={x.to === '/jobs' && n > 0 ? <span className="text-[11px] rounded-full bg-sky-400 text-ink px-1.5 font-semibold">{n}</span> : null} />
          ))}
        </nav>
        <div className="px-3 pb-3 space-y-0.5 border-t border-white/10 pt-3">
          {s?.demo && <div className="mx-1 mb-2 rounded-lg bg-amber-400/15 text-amber-300 text-[12px] px-2.5 py-1.5">演示模式 · 假数据 · 不花钱</div>}
          <Item to="/settings" label="设置" icon={Settings} />
          {me?.server && me.user && (
            <button onClick={async () => { await api('/auth/logout', { method: 'POST' }); location.href = '/login' }}
              className="w-full flex items-center gap-2.5 h-9 px-3 rounded-lg text-[14px] text-white/65 hover:text-white hover:bg-white/5 transition cursor-pointer">
              <LogOut className="size-4" /><span className="flex-1 text-left truncate">退出 · {me.user.username}</span>
            </button>
          )}
          <NavLink to="/profile" className={({ isActive }) => clsx('flex items-center gap-2.5 h-11 px-2 rounded-lg transition', isActive ? 'bg-white/10' : 'hover:bg-white/5')}>
            <Avatar src={s?.profile_avatar} name={s?.profile_name || "观"} size={28} />
            <div className="min-w-0 flex-1">
              <div className="text-white text-[13px] truncate">{s?.profile_name || me?.user?.username || '我的监控台'}</div>
              <div className="text-white/40 text-[11px] flex items-center gap-1"><UserRound className="size-3" />个人信息 · {s?.demo ? '演示' : s?.provider === 'tikhub' ? 'TikHub' : 'Monid'}</div>
            </div>
          </NavLink>
        </div>
      </aside>
      <main className="flex-1 min-w-0 overflow-auto scroll-thin">
        <div className="md:hidden sticky top-0 z-20 bg-ink flex items-center gap-3 px-4 h-12">
          <button onClick={() => setOpen(true)} className="text-white p-1 -ml-1" aria-label="打开菜单"><Menu className="size-5" /></button>
          <img src="/logo-white.png" alt="观自行深" className="h-[20px] w-auto" />
          {n > 0 && <span className="ml-auto text-[11px] rounded-full bg-sky-400 text-ink px-2 py-0.5 font-semibold">{n} 个任务运行中</span>}
        </div>
        <div className="max-w-[1280px] mx-auto px-4 py-5 md:px-8 md:py-7">
          <Suspense fallback={<div className="py-20 text-center text-sm text-mute">加载中…</div>}>
            <Outlet />
          </Suspense>
        </div>
      </main>
    </div>
  )
}
