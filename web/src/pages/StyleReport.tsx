import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Check, Copy, Trash2 } from 'lucide-react'
import { useState } from 'react'
import Markdown from 'react-markdown'
import { useNavigate, useParams } from 'react-router-dom'
import remarkGfm from 'remark-gfm'
import { api, fmtTime } from '../api'
import { SCORE_KEYS } from '../components/StyleDNA'
import { Avatar, Button, Card, PlatformBadge } from '../components/ui'

/** 取「## 8. 仿写风格提示词」下面第一个代码块。 */
function stylePrompt(md: string): string {
  const sec = md.split(/\n## /).find((s) => s.startsWith('8'))
  const m = sec?.match(/```[a-z]*\n([\s\S]*?)```/)
  return (m?.[1] || sec?.replace(/^.*\n/, '') || '').trim()
}

function CopyBtn({ text, label }: { text: string; label: string }) {
  const [ok, setOk] = useState(false)
  return (
    <Button disabled={!text} onClick={() => { navigator.clipboard.writeText(text); setOk(true); setTimeout(() => setOk(false), 1500) }}>
      {ok ? <Check className="size-4" /> : <Copy className="size-4" />}{ok ? '已复制' : label}
    </Button>
  )
}

export default function StyleReport() {
  const { id } = useParams()
  const nav = useNavigate()
  const { data: r } = useQuery({ queryKey: ['style-report', id], queryFn: () => api(`/style-reports/${id}`) })
  if (!r) return null
  const body = r.report.replace(/```json\s*\{[\s\S]*?\}\s*```\s*$/, '').trim()
  const st = r.stats || {}
  const dist: [string, number][] = Object.entries(st.sent_dist || {}) as any
  const maxD = Math.max(1, ...dist.map(([, v]) => v))
  return (
    <div className="max-w-[960px]">
      <button onClick={() => nav(-1)} className="flex items-center gap-1 text-sm text-mute hover:text-ink mb-4 cursor-pointer"><ArrowLeft className="size-4" />返回</button>

      <div className="rounded-xl bg-ink text-white p-6">
        <div className="flex items-center gap-3">
          {r.author && <Avatar src={r.author.avatar} name={r.author.nickname} size={40} />}
          <div>
            <div className="flex items-center gap-2">
              <button className="font-semibold hover:underline cursor-pointer" onClick={() => r.author && nav(`/author/${r.author.id}`)}>{r.author?.nickname}</button>
              {r.author && <PlatformBadge p={r.author.platform} className="!bg-white/10" />}
              <span className="text-xs text-white/50">文风 DNA</span>
            </div>
            <div className="text-xs text-white/50 num mt-0.5">
              {r.n_items} 条{r.n_cut ? `（另 ${r.n_cut} 条太长未装入）` : ''} · {r.model} · 输入 {Math.round(r.in_tokens / 1000)}k / 输出 {Math.round(r.out_tokens / 1000)}k token · ${r.cost_usd} · {fmtTime(r.created)}
            </div>
          </div>
        </div>
        {r.summary && <div className="mt-5 text-2xl font-semibold leading-snug text-lime">{r.summary}</div>}
        {SCORE_KEYS.some((k) => r.scores?.[k] !== undefined) && (
          <div className="mt-6 grid grid-cols-6 gap-3">
            {SCORE_KEYS.map((k) => {
              const v = Number(r.scores?.[k] ?? 0)
              return (
                <div key={k}>
                  <div className="flex justify-between text-xs"><span className="text-white/60">{k}</span><span className="num font-semibold">{v}</span></div>
                  <div className="mt-1.5 h-1.5 rounded-full bg-white/10 overflow-hidden"><div className="h-full bg-lime" style={{ width: `${v * 10}%` }} /></div>
                </div>
              )
            })}
          </div>
        )}
        {r.meta?.authors?.length > 0 && <div className="mt-4 text-xs text-white/50">对比作者：{r.meta.authors.join(' · ')}</div>}
      </div>

      <div className="mt-4 flex items-center gap-2">
        <CopyBtn text={stylePrompt(r.report)} label="复制仿写提示词" />
        <CopyBtn text={r.report} label="复制全文 Markdown" />
        <span className="text-xs text-mute ml-2 truncate flex-1" title={r.path}>{r.path}</span>
        <Button variant="danger" onClick={async () => { if (confirm('删除这份报告？（本地 md 文件保留）')) { await api(`/style-reports/${r.id}`, { method: 'DELETE' }); nav(-1) } }}>
          <Trash2 className="size-4" />删除
        </Button>
      </div>

      {st.sentences > 0 && (
        <Card className="mt-4" title="量化底稿" extra={<span className="text-xs text-mute">程序统计，报告里的数字以此为准</span>}>
          <div className="grid grid-cols-[1fr_1.3fr] gap-6 text-sm">
            <div className="space-y-1.5 num">
              <div><span className="text-mute">材料</span> {st.items} 条 · 有逐字稿 {st.with_transcript} 条 · 约 {st.chars} 字</div>
              <div><span className="text-mute">句长</span> 均值 {st.sent_len.mean} · 中位数 {st.sent_len.median} · P90 {st.sent_len.p90}</div>
              <div><span className="text-mute">问号</span> 每千字 {st.question_per_k}</div>
              {st.top4?.length > 0 && <div><span className="text-mute">高频串</span> {st.top4.slice(0, 8).map(([g, c]: any) => `${g}×${c}`).join('，')}</div>}
            </div>
            <div className="space-y-1">
              {dist.map(([k, v]) => (
                <div key={k} className="flex items-center gap-2 text-xs">
                  <span className="w-16 text-mute shrink-0">{k}</span>
                  <div className="flex-1 h-3 bg-black/5 rounded"><div className="h-full bg-ink rounded" style={{ width: `${(v / maxD) * 100}%` }} /></div>
                  <span className="w-10 text-right num">{Math.round((v * 100) / st.sentences)}%</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}

      <Card className="mt-4">
        <article className="md"><Markdown remarkPlugins={[remarkGfm]}>{body}</Markdown></article>
      </Card>
    </div>
  )
}
