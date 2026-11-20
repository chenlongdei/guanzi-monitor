import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, CheckCircle2, ExternalLink, XCircle } from 'lucide-react'
import { ReactNode, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Button, Card, Input } from '../components/ui'

/** 第一次打开：填 Key → 测试 → 试采一条。填好数据渠道 Key 之前，其他页面都会先跳到这里。 */
function Step({ n, title, done, children, hint }: { n: number; title: string; done?: boolean; children: ReactNode; hint?: ReactNode }) {
  return (
    <Card className="mt-3">
      <div className="flex gap-4">
        <div className={`size-8 shrink-0 rounded-full flex items-center justify-center font-semibold text-sm ${done ? 'bg-lime text-ink' : 'bg-ink text-white'}`}>
          {done ? <CheckCircle2 className="size-4" /> : n}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold">{title}</div>
          {hint && <div className="text-xs text-mute mt-1 leading-relaxed">{hint}</div>}
          <div className="mt-3">{children}</div>
        </div>
      </div>
    </Card>
  )
}

function KeyInput({ k, test, placeholder, s, onDone }: { k: string; test: string; placeholder: string; s: any; onDone?: () => void }) {
  const qc = useQueryClient()
  const [v, setV] = useState('')
  const [r, setR] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const go = async () => {
    setBusy(true); setR(null)
    try {
      if (v.trim()) await api('/settings', { method: 'PUT', body: { [k]: v.trim() } })
      const res = await api('/settings/test', { body: { name: test } })
      setR(res); if (res.ok) { setV(''); onDone?.() }
      qc.invalidateQueries({ queryKey: ['settings'] })
    } catch (e: any) { setR({ ok: false, msg: String(e.message || e) }) }
    setBusy(false)
  }
  const cur = s?.[k]
  return (
    <div>
      <div className="flex gap-2">
        <Input type="password" value={v} onChange={(e) => setV(e.target.value)} className="flex-1"
          placeholder={cur?.set ? `已填写 · 尾号 ${cur.tail}（要换就重新粘贴）` : placeholder} />
        <Button variant="primary" loading={busy} disabled={!v.trim() && !cur?.set} onClick={go}>{v.trim() ? '保存并测试' : '测试'}</Button>
      </div>
      {r && (r.ok
        ? <div className="mt-2 text-sm text-green-700 flex items-center gap-1.5"><CheckCircle2 className="size-4" />可以用了{r.balance_usd != null ? `，余额 $${r.balance_usd}` : ''}</div>
        : <div className="mt-2 text-sm text-red-600 flex items-start gap-1.5"><XCircle className="size-4 mt-0.5 shrink-0" />{r.msg}</div>)}
    </div>
  )
}

export default function Welcome() {
  const { data: s } = useQuery({ queryKey: ['settings'], queryFn: () => api('/settings') })
  const nav = useNavigate()
  if (!s) return null
  const monid = s.monid_token?.set, ds = s.dashscope_api_key?.set
  return (
    <div className="max-w-[760px] mx-auto">
      <div className="rounded-2xl bg-ink text-white px-7 py-7">
        <img src="/logo-white.png" alt="观自行深" className="h-8 w-auto" />
        <div className="mt-4 text-xl font-semibold">欢迎使用监控台</div>
        <p className="mt-2 text-sm text-white/60 leading-relaxed">
          把抖音、小红书、视频号上的内容变成你自己的素材库：粘链接采单条、按关键词找热门、盯住对标博主，视频自动转成逐字稿。
          <br />先花 3 分钟填两个 Key，就能开始用。所有数据和 Key 都只存在你自己的电脑上。
        </p>
      </div>

      <Step n={1} title="填数据接口的 Key（Monid）" done={monid}
        hint={<>用来从平台拿内容和数据。去 <a className="underline inline-flex items-center gap-0.5" href="https://app.monid.ai" target="_blank">app.monid.ai <ExternalLink className="size-3" /></a> 注册 → 充值（$5 一般够用一两个月）→ 复制以 <code>monid_live_</code> 开头的 Key 粘到这里。</>}>
        <KeyInput k="monid_token" test="monid" placeholder="monid_live_…" s={s} />
      </Step>

      <Step n={2} title="填转逐字稿的 Key（阿里云百炼，可以先跳过）" done={ds}
        hint={<>视频转文字用。去 <a className="underline inline-flex items-center gap-0.5" href="https://bailian.console.aliyun.com/" target="_blank">阿里云百炼 <ExternalLink className="size-3" /></a> 开通 → 「API-KEY」里创建一个，以 <code>sk-</code> 开头。按音频时长计费，1 小时约 ¥0.29。不填也能采集，只是不能转逐字稿。</>}>
        <KeyInput k="dashscope_api_key" test="dashscope" placeholder="sk-…" s={s} />
      </Step>

      <Step n={3} title="试采一条" hint={s.server ? <>采到的内容、逐字稿都存在你的账号里，随时能在内容库查看、下载、导出 Excel。</> : <>采到的内容、逐字稿保存在：<code className="break-all">{s.data_root}</code>（设置里可以改）</>}>
        <Button variant="primary" disabled={!monid} onClick={() => nav('/single')}>
          去粘一条抖音或小红书链接 <ArrowRight className="size-4" />
        </Button>
        {!monid && <span className="ml-3 text-xs text-mute">先完成第 1 步</span>}
      </Step>

      <p className="mt-5 text-xs text-mute text-center">花钱的操作都会先报价；超过 20 条会先问你确认。</p>
    </div>
  )
}
