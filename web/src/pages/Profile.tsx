import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { Avatar, Button, Card, Input, PageHeader, Stat, Textarea } from '../components/ui'

export default function Profile() {
  const qc = useQueryClient()
  const { data: p } = useQuery({ queryKey: ['profile'], queryFn: () => api('/profile') })
  const [f, setF] = useState({ profile_name: '', profile_avatar: '', profile_bio: '' })
  useEffect(() => { if (p) setF({ profile_name: p.name || '', profile_avatar: p.avatar || '', profile_bio: p.bio || '' }) }, [p])
  if (!p) return null
  const save = async () => { await api('/settings', { method: 'PUT', body: f }); qc.invalidateQueries() }
  return (
    <div>
      <PageHeader title="个人信息" />
      <div className="grid grid-cols-[1fr_1fr] gap-4">
        <Card title="资料">
          <div className="flex items-center gap-4 mb-4">
            <Avatar src={f.profile_avatar} name={f.profile_name} size={64} />
            <div className="text-sm text-mute">头像填图片链接即可</div>
          </div>
          <div className="space-y-3">
            <label className="block"><div className="text-xs text-mute mb-1">昵称</div><Input value={f.profile_name} onChange={(e) => setF({ ...f, profile_name: e.target.value })} className="w-full" /></label>
            <label className="block"><div className="text-xs text-mute mb-1">头像链接</div><Input value={f.profile_avatar} onChange={(e) => setF({ ...f, profile_avatar: e.target.value })} className="w-full" placeholder="https://…" /></label>
            <label className="block"><div className="text-xs text-mute mb-1">简介</div><Textarea rows={3} value={f.profile_bio} onChange={(e) => setF({ ...f, profile_bio: e.target.value })} /></label>
            <Button variant="primary" onClick={save}>保存</Button>
          </div>
        </Card>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Stat accent label={`${p.provider === 'tikhub' ? 'TikHub' : p.provider === 'demo' ? '演示' : 'Monid'} 余额`} value={p.balance_usd === null || p.balance_usd === undefined ? '—' : `$${p.balance_usd}`} sub="实时查询" />
            <Stat label="库里内容 / 博主" value={`${p.contents} / ${p.authors}`} />
          </div>
          <Card title="每月花费" pad={false}>
            <table className="w-full text-sm">
              <thead><tr className="h-9 border-b border-line text-xs text-mute"><th className="text-left px-4 font-medium">月份</th><th className="text-right px-3 font-medium">任务</th><th className="text-right px-3 font-medium">接口</th><th className="text-right px-3 font-medium">转写</th><th className="text-right px-4 font-medium">合计</th></tr></thead>
              <tbody>
                {p.months.map((m: any) => (
                  <tr key={m.m} className="h-10 border-b border-line last:border-0 num">
                    <td className="px-4">{m.m}</td><td className="px-3 text-right">{m.jobs}</td>
                    <td className="px-3 text-right">${(m.usd || 0).toFixed(3)}</td><td className="px-3 text-right">¥{(m.cny || 0).toFixed(2)}</td>
                    <td className="px-4 text-right font-semibold">¥{m.total_cny}</td>
                  </tr>
                ))}
                {!p.months.length && <tr><td colSpan={5} className="text-center text-mute py-8">还没有花费</td></tr>}
              </tbody>
            </table>
          </Card>
        </div>
      </div>
    </div>
  )
}
