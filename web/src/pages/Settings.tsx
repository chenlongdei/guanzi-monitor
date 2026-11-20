import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Download, XCircle } from 'lucide-react'
import { ReactNode, useEffect, useState } from 'react'
import { api } from '../api'
import { AccountCard } from '../components/Account'
import { Badge, Button, Card, Input, PageHeader, Segmented } from '../components/ui'

function Row({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[180px_1fr] gap-4 py-3 border-b border-line last:border-0 items-start">
      <div><div className="text-sm font-medium">{label}</div>{hint && <div className="text-xs text-mute mt-0.5">{hint}</div>}</div>
      <div className="flex items-center gap-2 flex-wrap">{children}</div>
    </div>
  )
}

function Secret({ k, s, placeholder, onSave }: { k: string; s: any; placeholder: string; onSave: (d: any) => Promise<void> }) {
  const [v, setV] = useState('')
  const cur = s?.[k]
  return (
    <>
      <Input type="password" value={v} onChange={(e) => setV(e.target.value)} placeholder={cur?.set ? `已填写 · 尾号 ${cur.tail}（留空不改）` : placeholder} className="w-[380px]" />
      <Button disabled={!v} onClick={async () => { await onSave({ [k]: v.trim() }); setV('') }}>保存</Button>
      {cur?.set ? <Badge tone="lime">已填</Badge> : <Badge>未填</Badge>}
    </>
  )
}

export default function Settings() {
  const qc = useQueryClient()
  const { data: s } = useQuery({ queryKey: ['settings'], queryFn: () => api('/settings') })
  const [test, setTest] = useState<Record<string, any>>({})
  const [local, setLocal] = useState<any>({})
  useEffect(() => { if (s) setLocal({ usd_cny: s.usd_cny, confirm_over_items: s.confirm_over_items, default_limit: s.default_limit, data_root: s.data_root }) }, [s])
  const save = async (d: any) => { await api('/settings', { method: 'PUT', body: d }); qc.invalidateQueries({ queryKey: ['settings'] }) }
  const runTest = async (name: string) => { setTest((t) => ({ ...t, [name]: { loading: true } })); const r = await api('/settings/test', { body: { name } }); setTest((t) => ({ ...t, [name]: r })) }
  const T = ({ name }: { name: string }) => {
    const r = test[name]
    return (
      <>
        <Button variant="ghost" loading={r?.loading} onClick={() => runTest(name)}>测试连接</Button>
        {r && !r.loading && (r.ok ? <span className="text-xs text-lime-2 flex items-center gap-1"><CheckCircle2 className="size-3.5" />可用{r.balance_usd !== undefined && r.balance_usd !== null ? ` · 余额 $${r.balance_usd}` : ''}</span>
          : <span className="text-xs text-red-600 flex items-center gap-1"><XCircle className="size-3.5" />{r.msg}</span>)}
      </>
    )
  }
  if (!s) return null
  return (
    <div>
      <PageHeader title="设置" desc={`${s.server ? '凭证只存在你自己的账号空间里，别人看不到' : '凭证只存在本机数据库里'} · 版本 ${s.version || ''}`} extra={s.has_dei_capture &&
        <Button onClick={async () => { const r = await api('/settings/import-dei-capture', { method: 'POST' }); alert(`已导入：${r.imported.join('、') || '无'}`); qc.invalidateQueries() }}>
          <Download className="size-4" />从 dei-capture 导入凭证
        </Button>} />
      {s.demo && <div className="mb-4 rounded-xl bg-amber-50 text-amber-800 text-sm px-4 py-3">现在是演示模式：所有采集都是假数据，不联网、不花钱，数据存在独立的 demo.db。正式用时去掉 --demo 启动。</div>}

      <AccountCard />

      <Card title="数据渠道">
        <Row label="采集用哪家" hint="切换后，所有采集和监控都走这家">
          <Segmented value={s.provider} onChange={(v) => save({ provider: v })} options={[['monid', 'Monid（主力）'], ['tikhub', 'TikHub（备用）']]} />
        </Row>
        <Row label="抖音关键词" hint="默认用哪种搜索，关键词页也能临时切换">
          <Segmented value={s.douyin_search_engine || 'index'} onChange={(v) => save({ douyin_search_engine: v })} options={[['index', '抖音指数（视频）'], ['search', '站内搜索']]} />
          <div className="w-full text-xs text-mute mt-1">抖音指数：一次 $0.001 返回几百条，按热度排，带爆款标签；没有作者主页 ID。站内搜索：每页约 $0.012，更贴近关键词，带视频直链和作者。</div>
        </Row>
        <Row label="Monid Token" hint="monid_live_ 开头"><Secret k="monid_token" s={s} placeholder="monid_live_…" onSave={save} /><T name="monid" /></Row>
        <Row label="TikHub Token" hint="备用；也用于以后补播放量"><Secret k="tikhub_token" s={s} placeholder="TikHub API Token" onSave={save} /><T name="tikhub" /></Row>
      </Card>

      <Card title="转写" className="mt-4">
        <Row label="阿里云百炼 Key" hint="sk- 开头；Paraformer 约 ¥0.29/小时"><Secret k="dashscope_api_key" s={s} placeholder="sk-…" onSave={save} /><T name="dashscope" /></Row>
        <Row label="大圣去水印" hint="直链失效时的兜底">
          <Input defaultValue={s.dasheng_uid} onBlur={(e) => e.target.value !== s.dasheng_uid && save({ dasheng_uid: e.target.value })} placeholder="uid" className="w-40" />
          <Secret k="dasheng_key" s={s} placeholder="key" onSave={save} />
        </Row>
      </Card>

      <Card title="AI 分析" className="mt-4">
        <Row label="Anthropic API Key" hint={<>sk-ant- 开头；博主页「文风 DNA」用。<a className="underline" href="https://platform.claude.com/settings/keys" target="_blank">去申请</a></>}>
          <Secret k="anthropic_api_key" s={s} placeholder="sk-ant-…" onSave={save} /><T name="anthropic" />
        </Row>
        <Row label="分析用的模型" hint="一份 30 条的报告：Opus 约 $0.7，Sonnet 约 $0.35">
          <Segmented value={s.style_model} onChange={(v) => save({ style_model: v })} options={[['claude-opus-5-5', 'Opus 5.5（推荐）'], ['claude-sonnet-5-5', 'Sonnet 5.5（便宜一半）'], ['claude-fable-5-2', 'Fable 5.2（最强，2 倍价）']]} />
        </Row>
        <Row label="思考深度" hint="越深越细，也越慢越贵">
          <Segmented value={s.style_effort} onChange={(v) => save({ style_effort: v })} options={[['medium', '中'], ['high', '高（推荐）'], ['xhigh', '很高'], ['max', '最大']]} />
        </Row>
      </Card>

      <Card title="保存与费用" className="mt-4">
        {!s.server && <Row label="采集结果保存位置" hint="逐字稿 md 和数据库都在这里；改了要重启监控台">
          <Input value={local.data_root || ''} onChange={(e) => setLocal({ ...local, data_root: e.target.value })} className="w-[460px]" />
          <Button disabled={local.data_root === s.data_root} onClick={() => save({ data_root: local.data_root })}>保存</Button>
          <div className="w-full text-xs text-mute">数据库：{s.db_path}</div>
        </Row>}
        <Row label="超过多少条先确认" hint="计费前先报数">
          <Input type="number" value={local.confirm_over_items ?? ''} onChange={(e) => setLocal({ ...local, confirm_over_items: Number(e.target.value) })} onBlur={() => save({ confirm_over_items: local.confirm_over_items })} className="w-24" /><span className="text-sm text-mute">条</span>
        </Row>
        <Row label="美元汇率" hint="用来把接口花费折成人民币">
          <Input type="number" step="0.01" value={local.usd_cny ?? ''} onChange={(e) => setLocal({ ...local, usd_cny: Number(e.target.value) })} onBlur={() => save({ usd_cny: local.usd_cny })} className="w-24" />
        </Row>
      </Card>
    </div>
  )
}
