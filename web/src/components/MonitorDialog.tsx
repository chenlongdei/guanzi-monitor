import { useQueryClient } from '@tanstack/react-query'
import { BellPlus } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, PLATFORMS } from '../api'
import { Button, Input, Modal, Select, Toggle } from './ui'

export const INTERVALS: [number, string][] = [[6, '每 6 小时'], [12, '每 12 小时'], [24, '每天'], [72, '每 3 天'], [168, '每周']]

export default function MonitorButton({ kind, platform, target, label, params, disabled, existing }: {
  kind: 'keyword' | 'blogger'; platform: string; target: string; label: string; params?: any; disabled?: boolean; existing?: any
}) {
  const [open, setOpen] = useState(false)
  const [interval, setInterval_] = useState(24)
  const [max, setMax] = useState(20)
  const [auto, setAuto] = useState(false)
  const [skipFirst, setSkipFirst] = useState(true)
  const [busy, setBusy] = useState(false)
  const qc = useQueryClient()
  const nav = useNavigate()
  if (existing) {
    return <Button onClick={() => nav('/monitors')}><BellPlus className="size-4" />监控中 · 管理</Button>
  }
  const save = async () => {
    setBusy(true)
    try {
      await api('/monitors', { body: { kind, platform, target, label, params, interval_hours: interval, max_items: max, auto_transcribe: auto, skip_first: skipFirst } })
      qc.invalidateQueries()
      setOpen(false)
    } catch (e: any) { alert(e.message) } finally { setBusy(false) }
  }
  return (
    <>
      <Button disabled={disabled} onClick={() => setOpen(true)}><BellPlus className="size-4" />加入{kind === 'keyword' ? '关键词' : '博主'}监控</Button>
      <Modal open={open} onClose={() => setOpen(false)} title={`监控${kind === 'keyword' ? '关键词' : '博主'}：${label}`}
        footer={<><Button onClick={() => setOpen(false)}>取消</Button><Button variant="primary" loading={busy} onClick={save}>开始监控</Button></>}>
        <div className="space-y-4 text-sm">
          <div className="text-mute">{PLATFORMS[platform]} · {kind === 'keyword' ? '定期重新搜索，第一次出现的标「新」，老内容记一次数据快照' : '定期拉最新作品，只处理库里最新一条之后发布的'}</div>
          <div className="grid grid-cols-[96px_1fr] items-center gap-3">
            <span className="text-mute">频率</span>
            <Select value={interval} onChange={(v) => setInterval_(Number(v))} options={INTERVALS} />
            <span className="text-mute">单次最多</span>
            <div className="flex items-center gap-2"><Input type="number" min={1} max={200} value={max} onChange={(e) => setMax(Number(e.target.value))} className="w-24" /><span className="text-mute">条（防止跑飞）</span></div>
            <span className="text-mute">新内容</span>
            <Toggle checked={auto} onChange={setAuto} label="自动转逐字稿" />
            <span className="text-mute">首次</span>
            <Toggle checked={skipFirst} onChange={setSkipFirst} label="刚采过，下个周期再跑" />
          </div>
          <p className="text-xs text-mute">监控在监控台开着时运行；Mac 合盖或关机期间错过的，下次打开会补跑一次。</p>
        </div>
      </Modal>
    </>
  )
}
