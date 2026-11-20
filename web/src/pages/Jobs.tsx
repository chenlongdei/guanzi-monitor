import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, RotateCcw } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'
import { ago, api, fmtTime } from '../api'
import ContentTable from '../components/ContentTable'
import { JobProgress, useJob } from '../components/jobs'
import { Badge, Button, Card, Empty, JobStatus, PageHeader, PlatformBadge } from '../components/ui'

export function Jobs() {
  const nav = useNavigate()
  const { data } = useQuery({ queryKey: ['jobs', 'all'], queryFn: () => api<any[]>('/jobs?limit=200'), refetchInterval: 3000 })
  return (
    <div>
      <PageHeader title="任务记录" desc="每次运行的渠道、条数、失败原因和花费" />
      {!data?.length ? <Card><Empty>还没有任务</Empty></Card> : (
        <div className="bg-white rounded-xl border border-line">
          <table className="w-full text-sm">
            <thead><tr className="h-10 border-b border-line text-xs text-mute">
              <th className="text-left px-4 font-medium">任务</th><th className="text-left px-3 font-medium">状态</th>
              <th className="text-right px-3 font-medium">成功</th><th className="text-right px-3 font-medium">失败</th>
              <th className="text-right px-3 font-medium">新入库</th><th className="text-right px-3 font-medium">花费</th>
              <th className="text-left px-3 font-medium">最新进度</th><th className="text-right px-4 font-medium">时间</th>
            </tr></thead>
            <tbody>
              {data.map((j) => (
                <tr key={j.id} onClick={() => nav(`/jobs/${j.id}`)} className="border-b border-line last:border-0 h-12 hover:bg-paper/70 cursor-pointer">
                  <td className="px-4"><div className="flex items-center gap-2">{j.platform ? <PlatformBadge p={j.platform} /> : <Badge>{j.kind_label}</Badge>}<span>{j.title}</span>{j.monitor_id ? <Badge tone="ink">监控</Badge> : null}</div></td>
                  <td className="px-3"><JobStatus s={j.status} /></td>
                  <td className="px-3 text-right num">{j.done}</td>
                  <td className={`px-3 text-right num ${j.failed ? 'text-red-600' : 'text-mute'}`}>{j.failed}</td>
                  <td className="px-3 text-right num">{j.new_count}</td>
                  <td className="px-3 text-right num text-mute">${j.cost_usd?.toFixed(3)}{j.cost_cny ? ` + ¥${j.cost_cny.toFixed(2)}` : ''}</td>
                  <td className="px-3 text-mute max-w-[260px] truncate">{j.error || j.last_log}</td>
                  <td className="px-4 text-right text-mute whitespace-nowrap">{ago(j.created)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function JobDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { data: j } = useJob(Number(id))
  if (!j) return null
  const retry = async () => { const r = await api(`/jobs/${j.id}/retry`, { method: 'POST' }); qc.invalidateQueries(); nav(`/jobs/${r.job_id}`) }
  const newIds = new Set<number>((j.results || []).filter((r: any) => !r.seen_before).map((r: any) => r.id))
  return (
    <div>
      <button onClick={() => nav(-1)} className="flex items-center gap-1 text-sm text-mute hover:text-ink mb-4 cursor-pointer"><ArrowLeft className="size-4" />返回</button>
      <PageHeader title={`任务 #${j.id}`} desc={`${j.kind_label} · 创建于 ${fmtTime(j.created)}${j.finished ? ` · 用时 ${Math.round(j.finished - (j.started || j.created))} 秒` : ''} · 接口调用 ${j.calls?.n || 0} 次${j.calls?.failed ? `（失败 ${j.calls.failed}）` : ''}`}
        extra={!['queued', 'running'].includes(j.status) && <Button onClick={retry}><RotateCcw className="size-4" />重跑</Button>} />
      <JobProgress job={j} />
      <div className="grid grid-cols-[1fr_340px] gap-4 mt-4">
        <ContentTable items={j.results || []} newIds={newIds} cols={j.kind === 'keyword' ? ['rank', 'author', 'published_at', 'views', 'likes', 'comments', 'saves', 'transcript'] : ['author', 'published_at', 'views', 'likes', 'comments', 'saves', 'transcript']} emptyText="这个任务没有产出内容" />
        <Card title="日志" pad={false}>
          <div className="max-h-[560px] overflow-auto scroll-thin p-3 space-y-1 text-xs font-mono">
            {(j.log || []).map((l: any, i: number) => (
              <div key={i} className={l.level === 'error' ? 'text-red-600' : l.level === 'warn' ? 'text-amber-700' : 'text-mute'}>
                <span className="opacity-60">{fmtTime(l.t).slice(11)}</span> {l.msg}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
