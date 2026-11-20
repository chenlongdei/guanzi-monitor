import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Hash, Play, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ago, api, PLATFORMS, until } from '../api'
import { INTERVALS } from '../components/MonitorDialog'
import { Avatar, Badge, Button, Card, Empty, Input, JobStatus, Modal, PageHeader, PlatformBadge, Segmented, Select, Toggle } from '../components/ui'

export default function Monitors() {
  const [tab, setTab] = useState<'keyword' | 'blogger'>('keyword')
  const [hist, setHist] = useState<any>(null)
  const qc = useQueryClient()
  const nav = useNavigate()
  const { data: list } = useQuery({ queryKey: ['monitors', 'all'], queryFn: () => api<any[]>('/monitors'), refetchInterval: 4000 })
  const { data: runs } = useQuery({ queryKey: ['monitor-runs', hist?.id], enabled: !!hist, queryFn: () => api<any[]>(`/monitors/${hist.id}/runs`) })
  const rows = (list || []).filter((m) => m.kind === tab)
  const patch = async (id: number, body: any) => { await api(`/monitors/${id}`, { method: 'PATCH', body }); qc.invalidateQueries({ queryKey: ['monitors'] }) }
  const del = async (m: any) => { if (confirm(`删除监控「${m.label || m.target}」？已采集的内容不会删。`)) { await api(`/monitors/${m.id}`, { method: 'DELETE' }); qc.invalidateQueries() } }
  const runNow = async (id: number) => { await api(`/monitors/${id}/run`, { method: 'POST' }); qc.invalidateQueries() }
  const kwCount = (list || []).filter((m) => m.kind === 'keyword').length
  return (
    <div>
      <PageHeader title="监控" desc="监控台开着时按频率自动跑；新内容标「新」，老内容记一次数据快照"
        extra={<Segmented value={tab} onChange={setTab} options={[['keyword', `关键词 ${kwCount}`], ['blogger', `博主 ${(list?.length || 0) - kwCount}`]]} />} />
      {!rows.length ? (
        <Card><Empty icon={<Hash className="size-6" />}>
          还没有{tab === 'keyword' ? '关键词' : '博主'}监控。{tab === 'keyword' ? <>去 <Link className="underline" to="/keyword">关键词</Link> 搜一次，再点「加入关键词监控」</> : <>打开任意 <Link className="underline" to="/blogger">博主</Link>，点「加入博主监控」</>}
        </Empty></Card>
      ) : (
        <div className="bg-white rounded-xl border border-line">
          <table className="w-full text-sm">
            <thead><tr className="h-10 border-b border-line text-xs text-mute">
              <th className="text-left px-4 font-medium">{tab === 'keyword' ? '关键词' : '博主'}</th>
              <th className="text-left px-3 font-medium">频率</th>
              <th className="text-left px-3 font-medium">单次最多</th>
              <th className="text-left px-3 font-medium">自动转写</th>
              <th className="text-left px-3 font-medium">上次</th>
              <th className="text-left px-3 font-medium">下次</th>
              <th className="text-right px-3 font-medium">累计</th>
              <th className="px-3 font-medium">开关</th>
              <th />
            </tr></thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id} className="border-b border-line last:border-0 h-14">
                  <td className="px-4">
                    <button className="flex items-center gap-2.5 text-left cursor-pointer" onClick={() => m.kind === 'blogger' ? nav(`/author/${m.target}`) : setHist(m)}>
                      {m.kind === 'blogger' ? <Avatar src={m.avatar} name={m.nickname} size={28} /> : <div className="size-7 rounded-full bg-paper flex items-center justify-center"><Hash className="size-3.5" /></div>}
                      <div>
                        <div className="font-medium flex items-center gap-1.5">{m.kind === 'blogger' ? m.nickname : m.target}<PlatformBadge p={m.platform} /></div>
                        {m.kind === 'keyword' && <div className="text-xs text-mute">{m.platform === 'douyin' ? (m.params?.engine === 'search' ? '站内搜索' : '抖音指数') + ' · ' : ''}近 {m.params?.days || '不限'} 天</div>}
                      </div>
                    </button>
                  </td>
                  <td className="px-3"><Select value={m.interval_hours} onChange={(v) => patch(m.id, { interval_hours: Number(v) })} options={INTERVALS} className="h-8" /></td>
                  <td className="px-3"><Input type="number" defaultValue={m.max_items} onBlur={(e) => patch(m.id, { max_items: Number(e.target.value) })} className="w-20 h-8" /></td>
                  <td className="px-3"><Toggle checked={!!m.auto_transcribe} onChange={(v) => patch(m.id, { auto_transcribe: v })} /></td>
                  <td className="px-3 text-mute">{m.running ? <JobStatus s="running" /> : <>{ago(m.last_run)}{m.last_run ? (m.last_new ? <Badge tone="lime" className="ml-1.5">新 {m.last_new}</Badge> : <span className="ml-1.5 text-xs">无新增</span>) : null}</>}</td>
                  <td className="px-3 text-mute">{m.enabled ? until(m.next_run) : '—'}</td>
                  <td className="px-3 text-right num">{m.total_found}</td>
                  <td className="px-3 text-center"><Toggle checked={!!m.enabled} onChange={(v) => patch(m.id, { enabled: v })} /></td>
                  <td className="px-3">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setHist(m)}>记录</Button>
                      <Button size="sm" variant="ghost" disabled={m.running} onClick={() => runNow(m.id)}><Play className="size-3.5" />立即运行</Button>
                      <Button size="sm" variant="ghost" onClick={() => del(m)}><Trash2 className="size-3.5" /></Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal open={!!hist} onClose={() => setHist(null)} width={640} title={`运行记录：${hist?.kind === 'blogger' ? hist?.nickname : hist?.target} · ${PLATFORMS[hist?.platform] || ''}`}>
        {!runs?.length ? <Empty>还没运行过</Empty> : (
          <div className="divide-y divide-line -my-2">
            {runs.map((j) => (
              <Link key={j.id} to={`/jobs/${j.id}`} className="flex items-center gap-3 py-2.5 text-sm hover:bg-paper/60 rounded px-1">
                <JobStatus s={j.status} /><span className="flex-1">{j.done} 条</span>
                {j.new_count ? <Badge tone="lime">新 {j.new_count}</Badge> : <span className="text-xs text-mute">无新增</span>}
                <span className="text-xs text-mute w-24 text-right">{ago(j.created)}</span>
              </Link>
            ))}
          </div>
        )}
      </Modal>
    </div>
  )
}
