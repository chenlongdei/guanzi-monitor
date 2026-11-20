import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { api, fmtTime } from '../api'
import { Badge, Button, Card, Input, Select } from './ui'

/** 网页版设置页里的「账号」卡：改密码、给 Agent 的访问令牌、管理员发邀请码。 */
export function AccountCard() {
  const qc = useQueryClient()
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: () => api('/auth/me') })
  const [pw, setPw] = useState({ old: '', new: '' })
  const [msg, setMsg] = useState('')
  const [tok, setTok] = useState('')
  const u = me?.user
  if (!me?.server || !u) return null
  const changePw = async () => {
    setMsg('')
    try { await api('/auth/password', { body: pw }); setMsg('已修改，请重新登录'); setTimeout(() => (location.href = '/login'), 1200) }
    catch (e: any) { setMsg(String(e.message || e)) }
  }
  const newTok = async () => {
    if (u.api_token_tail && !confirm('重新生成后，旧令牌立刻失效。继续？')) return
    const r = await api('/auth/token', { method: 'POST' }); setTok(r.token); qc.invalidateQueries({ queryKey: ['me'] })
  }
  return (
    <>
      <Card title="账号" className="mb-4">
        <div className="grid grid-cols-1 gap-2 md:grid-cols-[180px_1fr] md:gap-4 py-3 border-b border-line items-start">
          <div className="text-sm font-medium">当前账号</div>
          <div className="text-sm flex items-center gap-2">{u.username}{u.is_admin && <Badge tone="lime">管理员</Badge>}</div>
        </div>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-[180px_1fr] md:gap-4 py-3 border-b border-line items-start">
          <div><div className="text-sm font-medium">修改密码</div><div className="text-xs text-mute mt-0.5">改完所有设备都要重新登录</div></div>
          <div className="flex items-center gap-2 flex-wrap">
            <Input type="password" placeholder="原密码" value={pw.old} onChange={(e) => setPw({ ...pw, old: e.target.value })} className="w-44" />
            <Input type="password" placeholder="新密码（至少 8 位）" value={pw.new} onChange={(e) => setPw({ ...pw, new: e.target.value })} className="w-52" />
            <Button disabled={!pw.old || !pw.new} onClick={changePw}>修改</Button>
            {msg && <span className="text-xs text-mute">{msg}</span>}
          </div>
        </div>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-[180px_1fr] md:gap-4 py-3 items-start">
          <div><div className="text-sm font-medium">Agent 访问令牌</div><div className="text-xs text-mute mt-0.5">让 Claude 直接帮你操作监控台</div></div>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              {u.api_token_tail ? <Badge tone="lime">已生成 · 尾号 {u.api_token_tail}</Badge> : <Badge>未生成</Badge>}
              <Button size="sm" onClick={newTok}>{u.api_token_tail ? '重新生成' : '生成令牌'}</Button>
              {u.api_token_tail && <Button size="sm" variant="ghost" onClick={async () => { await api('/auth/token', { method: 'DELETE' }); setTok(''); qc.invalidateQueries({ queryKey: ['me'] }) }}>作废</Button>}
            </div>
            {tok && (
              <div className="rounded-lg bg-paper p-3 text-xs space-y-2">
                <div className="text-amber-700">只显示这一次，复制后发给你的 Agent：</div>
                <code className="block break-all">{tok}</code>
                <Button size="sm" onClick={() => navigator.clipboard.writeText(`观自行深监控台网页版：地址 ${location.origin}，请求头 Authorization: Bearer ${tok}`)}>
                  <Copy className="size-3.5" />复制给 Agent 的话
                </Button>
              </div>
            )}
          </div>
        </div>
      </Card>
      {u.is_admin && <Invites />}
    </>
  )
}

type Inv = { code: string; note?: string; is_admin?: number; used_by?: number; used_by_name?: string; created: number; sent_to?: string; sent_at?: number; expires?: number }

function invState(v: Inv): 'used' | 'expired' | 'sent' | 'free' {
  if (v.used_by) return 'used'
  if (v.expires && v.expires * 1000 < Date.now()) return 'expired'
  return v.sent_to || v.sent_at ? 'sent' : 'free'
}

function Invites() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['invites'], queryFn: () => api<{ invites: Inv[]; users: any[] }>('/admin/invites') })
  const [note, setNote] = useState('')
  const [count, setCount] = useState(1)
  const [days, setDays] = useState(0)
  const [filter, setFilter] = useState<'free' | 'sent' | 'used' | 'all'>('free')
  const [msg, setMsg] = useState('')
  const refresh = () => qc.invalidateQueries({ queryKey: ['invites'] })
  const add = async () => {
    const r = await api<{ codes: string[] }>('/admin/invites', { body: { note, count, days: days || undefined } })
    setNote(''); setMsg(`已生成 ${r.codes.length} 个`); setFilter('free'); refresh()
  }
  const patch = async (code: string, body: any) => { await api(`/admin/invites/${code}`, { method: 'PATCH', body }); refresh() }
  const revoke = async (code: string) => { await api(`/admin/invites/${code}`, { method: 'DELETE' }); refresh() }
  const copy = async (v: Inv) => {
    const text = `观自行深监控台：打开 ${location.origin} → 用邀请码注册 → 邀请码 ${v.code}`
    try { await navigator.clipboard.writeText(text); setMsg(`已复制 ${v.code} 的邀请话术`) } catch { setMsg(text) }
    patch(v.code, { mark_sent: true })
  }
  const all = data?.invites || []
  const n = { free: 0, sent: 0, used: 0, expired: 0 } as Record<string, number>
  all.forEach((v) => n[invState(v)]++)
  const list = all.filter((v) => filter === 'all' || invState(v) === filter)
  const STATE: Record<string, [string, any]> = { used: ['已注册', 'gray'], expired: ['已过期', 'red'], sent: ['已发出', 'amber'], free: ['未发', 'lime'] }
  return (
    <Card title={`邀请码 · ${data?.users?.length ?? 0} 个账号`} className="mb-4">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <Input placeholder="备注（批次或给谁）" value={note} onChange={(e) => setNote(e.target.value)} className="w-48" />
        <Select value={count} onChange={(v) => setCount(Number(v))} options={[[1, '1 个'], [5, '5 个'], [10, '10 个'], [20, '20 个']]} />
        <Select value={days} onChange={(v) => setDays(Number(v))} options={[[0, '不过期'], [7, '7 天有效'], [30, '30 天有效']]} />
        <Button onClick={add}><Plus className="size-4" />生成</Button>
        {msg && <span className="text-xs text-mute">{msg}</span>}
      </div>
      <div className="flex flex-wrap gap-1.5 mb-2 text-xs">
        {([['free', `未发 ${n.free}`], ['sent', `已发未注册 ${n.sent}`], ['used', `已注册 ${n.used}`], ['all', `全部 ${all.length}`]] as const).map(([k, l]) => (
          <button key={k} onClick={() => setFilter(k)} className={`px-2.5 py-1 rounded-full border ${filter === k ? 'bg-ink text-white border-ink' : 'border-line text-mute'}`}>{l}</button>
        ))}
      </div>
      <div className="divide-y divide-line text-sm">
        {list.map((v) => {
          const st = invState(v)
          return (
            <div key={v.code} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <code className="font-semibold w-24">{v.code}</code>
              <Badge tone={STATE[st][1]}>{STATE[st][0]}{st === 'used' && ` · ${v.used_by_name}`}</Badge>
              <span className="w-28 truncate text-mute text-xs" title={v.note}>{v.note || '—'}</span>
              {st === 'used'
                ? <span className="w-32 truncate text-xs text-mute">{v.sent_to ? `发给 ${v.sent_to}` : ''}</span>
                : <Input key={v.code + (v.sent_to || '')} defaultValue={v.sent_to || ''} placeholder="发给谁" className="w-32 h-8"
                    onBlur={(e) => e.target.value !== (v.sent_to || '') && patch(v.code, { sent_to: e.target.value })} />}
              <span className="text-xs text-mute flex-1 min-w-24">
                {v.sent_at ? `发出 ${fmtTime(v.sent_at, false)}` : `生成 ${fmtTime(v.created, false)}`}
                {v.expires ? ` · ${st === 'expired' ? '已过期' : '到期 ' + fmtTime(v.expires, false)}` : ''}
              </span>
              {st !== 'used' && st !== 'expired' && <Button size="sm" variant="ghost" onClick={() => copy(v)}><Copy className="size-3.5" />复制话术</Button>}
              {st !== 'used' && <Button size="sm" variant="ghost" onClick={() => revoke(v.code)}><Trash2 className="size-3.5" />作废</Button>}
            </div>
          )
        })}
        {!list.length && <div className="py-6 text-center text-mute text-xs">这一栏没有邀请码</div>}
      </div>
    </Card>
  )
}
