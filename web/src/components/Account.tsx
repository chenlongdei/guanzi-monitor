import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Plus } from 'lucide-react'
import { useState } from 'react'
import { api, fmtTime } from '../api'
import { Badge, Button, Card, Input } from './ui'

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
        <div className="grid grid-cols-[180px_1fr] gap-4 py-3 border-b border-line items-start">
          <div className="text-sm font-medium">当前账号</div>
          <div className="text-sm flex items-center gap-2">{u.username}{u.is_admin && <Badge tone="lime">管理员</Badge>}</div>
        </div>
        <div className="grid grid-cols-[180px_1fr] gap-4 py-3 border-b border-line items-start">
          <div><div className="text-sm font-medium">修改密码</div><div className="text-xs text-mute mt-0.5">改完所有设备都要重新登录</div></div>
          <div className="flex items-center gap-2 flex-wrap">
            <Input type="password" placeholder="原密码" value={pw.old} onChange={(e) => setPw({ ...pw, old: e.target.value })} className="w-44" />
            <Input type="password" placeholder="新密码（至少 8 位）" value={pw.new} onChange={(e) => setPw({ ...pw, new: e.target.value })} className="w-52" />
            <Button disabled={!pw.old || !pw.new} onClick={changePw}>修改</Button>
            {msg && <span className="text-xs text-mute">{msg}</span>}
          </div>
        </div>
        <div className="grid grid-cols-[180px_1fr] gap-4 py-3 items-start">
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

function Invites() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['invites'], queryFn: () => api('/admin/invites') })
  const [note, setNote] = useState('')
  const add = async () => { await api('/admin/invites', { body: { note } }); setNote(''); qc.invalidateQueries({ queryKey: ['invites'] }) }
  return (
    <Card title={`邀请码 · 已有 ${data?.users?.length ?? 0} 个账号`} className="mb-4">
      <div className="flex items-center gap-2 mb-3">
        <Input placeholder="备注：给谁的" value={note} onChange={(e) => setNote(e.target.value)} className="w-56" />
        <Button onClick={add}><Plus className="size-4" />生成邀请码</Button>
      </div>
      <div className="divide-y divide-line text-sm">
        {data?.invites?.map((v: any) => (
          <div key={v.code} className="flex items-center gap-3 py-2">
            <code className="font-semibold w-28">{v.code}</code>
            <span className="w-32 truncate text-mute">{v.note || '—'}</span>
            {v.used_by ? <Badge>已用 · {v.used_by_name}</Badge> : <Badge tone="lime">未用</Badge>}
            <span className="text-xs text-mute flex-1">{fmtTime(v.created)}</span>
            {!v.used_by && <Button size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(`观自行深监控台：打开 ${location.origin} → 用邀请码注册 → 邀请码 ${v.code}`)}>
              <Copy className="size-3.5" />复制邀请话术</Button>}
          </div>
        ))}
      </div>
    </Card>
  )
}
