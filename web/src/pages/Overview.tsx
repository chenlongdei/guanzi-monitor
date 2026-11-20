import { useQuery } from '@tanstack/react-query'
import { BellRing, Hash, Link2, Users } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts'
import { ago, api, PLATFORMS } from '../api'
import { Avatar, Badge, Card, Empty, JobStatus, PageHeader, PlatformBadge, Stat } from '../components/ui'

export default function Overview() {
  const { data: o } = useQuery({ queryKey: ['overview'], queryFn: () => api('/overview'), refetchInterval: 5000 })
  const nav = useNavigate()
  if (!o) return null
  const quick = [
    { to: '/single', icon: Link2, t: '单条采集', d: '粘贴分享链接' },
    { to: '/keyword', icon: Hash, t: '关键词', d: '搜一批热门内容' },
    { to: '/blogger', icon: Users, t: '博主', d: '拉一个博主的作品' },
    { to: '/monitors', icon: BellRing, t: '监控', d: `${o.monitors} 个在运行` },
  ]
  return (
    <div>
      <PageHeader title="总览" desc={`数据渠道：${o.provider === 'demo' ? '演示' : o.provider === 'tikhub' ? 'TikHub' : 'Monid'}`} />
      <div className="grid grid-cols-4 gap-3">
        <Stat accent label="今日新入库" value={o.today_new} sub={`库里共 ${o.total_contents} 条`} />
        <Stat label="博主" value={o.total_authors} sub={`监控中 ${o.monitors} 个`} />
        <Stat label="逐字稿" value={o.transcripts} />
        <Stat label="本月花费" value={`¥${o.month_cny}`} sub={`接口 $${o.month_usd} · 转写 ¥${o.month_asr_cny}`} />
      </div>

      <div className="grid grid-cols-4 gap-3 mt-3">
        {quick.map(({ to, icon: Icon, t, d }) => (
          <Link key={to} to={to} className="group rounded-xl border border-line bg-white p-4 flex items-center gap-3 hover:border-ink transition">
            <div className="size-9 rounded-lg bg-paper group-hover:bg-lime flex items-center justify-center transition"><Icon className="size-4" /></div>
            <div><div className="font-medium text-sm">{t}</div><div className="text-xs text-mute">{d}</div></div>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-5 gap-3 mt-3">
        <Card className="col-span-3" title="最近任务" extra={<Link to="/jobs" className="text-xs text-mute hover:text-ink">全部 →</Link>} pad={false}>
          {o.recent_jobs.length === 0 ? <Empty>还没有任务，从上面任意入口开始</Empty> : (
            <div className="divide-y divide-line">
              {o.recent_jobs.map((j: any) => (
                <div key={j.id} onClick={() => nav(`/jobs/${j.id}`)} className="flex items-center gap-3 px-4 h-12 hover:bg-paper/70 cursor-pointer text-sm">
                  {j.platform ? <PlatformBadge p={j.platform} /> : <Badge>{j.kind_label}</Badge>}
                  <span className="flex-1 truncate">{j.title}</span>
                  <span className="text-xs text-mute num">{j.done} 条{j.new_count ? ` · 新 ${j.new_count}` : ''}</span>
                  <JobStatus s={j.status} />
                  <span className="text-xs text-mute w-20 text-right">{ago(j.created)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card className="col-span-2" title="监控动态" extra={<Link to="/monitors" className="text-xs text-mute hover:text-ink">管理 →</Link>} pad={false}>
          {o.monitor_feed.length === 0 ? <Empty>还没有监控运行过</Empty> : (
            <div className="divide-y divide-line">
              {o.monitor_feed.map((m: any) => (
                <div key={m.id} className="flex items-center gap-3 px-4 h-12 text-sm">
                  {m.kind === 'blogger' ? <Avatar src={m.avatar} name={m.nickname} size={24} /> : <div className="size-6 rounded-full bg-paper flex items-center justify-center"><Hash className="size-3" /></div>}
                  <span className="flex-1 truncate">{m.kind === 'blogger' ? m.nickname : `「${m.target}」`} <span className="text-mute">· {PLATFORMS[m.platform]}</span></span>
                  {m.last_new ? <Badge tone="lime">新 {m.last_new}</Badge> : <span className="text-xs text-mute">无新增</span>}
                  <span className="text-xs text-mute">{ago(m.last_run)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card className="mt-3" title="近 14 天入库">
        {o.daily.length === 0 ? <Empty>暂无数据</Empty> : (
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={o.daily}>
              <XAxis dataKey="d" tickFormatter={(d) => d.slice(5)} tick={{ fontSize: 11, fill: '#6b7068' }} axisLine={false} tickLine={false} />
              <Tooltip cursor={{ fill: '#f5f6f2' }} formatter={(v: any) => [v, '条']} contentStyle={{ borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="n" fill="#111311" radius={[4, 4, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>
    </div>
  )
}
