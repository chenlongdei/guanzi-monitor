import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Loader2, Square } from 'lucide-react'
import { createContext, ReactNode, useCallback, useContext, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ago } from '../api'
import { Button, JobStatus, Modal } from './ui'

type Kind = 'single' | 'keyword' | 'blogger' | 'transcribe' | 'refresh' | 'style'
type Run = (kind: Kind, body: any, onStarted?: (jobId: number) => void) => void

const Ctx = createContext<Run>(() => {})
export const useRunJob = () => useContext(Ctx)

/** 计费前先报数：先调 /estimate，超过阈值弹窗确认，再建任务。 */
export function JobProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<{ kind: Kind; body: any; est: any; cb?: (id: number) => void } | null>(null)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState<{ id: number; text: string } | null>(null)
  const qc = useQueryClient()
  const nav = useNavigate()

  const start = useCallback(async (kind: Kind, body: any, cb?: (id: number) => void) => {
    setBusy(true)
    try {
      const r = await api<{ job_id: number }>(`/jobs/${kind}`, { body })
      qc.invalidateQueries({ queryKey: ['jobs-running'] })
      cb?.(r.job_id)
      if (!cb) {
        setToast({ id: r.job_id, text: '任务已开始' })
        setTimeout(() => setToast(null), 5000)
      }
    } catch (e: any) {
      alert(e.message)
    } finally {
      setBusy(false)
      setPending(null)
    }
  }, [qc])

  const run: Run = useCallback(async (kind, body, cb) => {
    if (kind === 'refresh' || kind === 'transcribe') {
      const est = { items: body.content_ids?.length || 0, need_confirm: (body.content_ids?.length || 0) > 20, kind }
      if (est.need_confirm) return setPending({ kind, body, est, cb })
      return start(kind, body, cb)
    }
    try {
      const est = await api('/estimate', { body: { kind, ...body } })
      if (est.need_confirm) setPending({ kind, body, est, cb })
      else start(kind, body, cb)
    } catch (e: any) { alert(e.message) }
  }, [start])

  const e = pending?.est
  return (
    <Ctx.Provider value={run}>
      {children}
      <Modal open={!!pending} onClose={() => setPending(null)} title={e?.kind === 'style' ? '确认文风分析' : '确认费用'}
        footer={<><Button onClick={() => setPending(null)}>取消</Button><Button variant="primary" loading={busy} onClick={() => pending && start(pending.kind, pending.body, pending.cb)}>确认开始</Button></>}>
        {e && e.kind === 'style' && (
          <div className="space-y-3 text-sm">
            <p>把 <b className="num">{e.items}</b> 条内容（其中有逐字稿 {e.with_transcript} 条，约 {Math.round(e.chars / 1000)}k 字）交给 {e.provider} 做文风 DNA 分析。</p>
            {e.cut > 0 && <p className="text-amber-700">材料太长，只装入最新的 {e.items} 条，另有 {e.cut} 条较早的不装入。</p>}
            <div className="rounded-lg bg-paper p-3 space-y-1.5 num">
              <div className="flex justify-between"><span className="text-mute">AI 分析（输入约 {Math.round(e.in_tokens / 1000)}k token，输出按 30k 估）</span><span>约 ${e.usd}</span></div>
              {e.to_transcribe > 0 && <div className="flex justify-between"><span className="text-mute">先转写 {e.to_transcribe} 条（按每条 90 秒估）</span><span>约 ¥{e.asr_cny}</span></div>}
              <div className="flex justify-between font-semibold border-t border-line pt-1.5"><span>合计约</span><span>¥{e.total_cny}</span></div>
            </div>
            <p className="text-mute">通常 2–6 分钟出报告，可以离开这个页面。</p>
          </div>
        )}
        {e && e.kind !== 'style' && (
          <div className="space-y-3 text-sm">
            <p>这次一共 <b className="num">{e.items}</b> 条，超过了「先确认」的阈值。</p>
            {e.calls !== undefined && (
              <div className="rounded-lg bg-paper p-3 space-y-1.5 num">
                <div className="flex justify-between"><span className="text-mute">接口调用（{e.provider}）</span><span>约 {e.calls} 次 · ${e.usd}</span></div>
                {e.asr_cny > 0 && <div className="flex justify-between"><span className="text-mute">转写（按每条 90 秒估）</span><span>约 ¥{e.asr_cny}</span></div>}
                <div className="flex justify-between font-semibold border-t border-line pt-1.5"><span>合计约</span><span>¥{e.total_cny}</span></div>
              </div>
            )}
            {pending?.kind === 'transcribe' && <p className="text-mute">已有逐字稿的会直接复用，不重复计费。</p>}
          </div>
        )}
      </Modal>
      {toast && (
        <div className="fixed bottom-5 right-5 z-50 bg-ink text-white rounded-xl px-4 py-3 shadow-xl flex items-center gap-3 text-sm">
          <Loader2 className="size-4 animate-spin text-lime" />{toast.text}
          <button className="text-lime underline cursor-pointer" onClick={() => { nav(`/jobs/${toast.id}`); setToast(null) }}>查看</button>
        </div>
      )}
    </Ctx.Provider>
  )
}

export function useJob(id?: number | null) {
  return useQuery({
    queryKey: ['job', id], enabled: !!id,
    queryFn: () => api(`/jobs/${id}`),
    refetchInterval: (q) => (q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 1200 : false),
  })
}

/** 任务进度条 + 最新日志。 */
export function JobProgress({ job }: { job: any }) {
  const qc = useQueryClient()
  if (!job) return null
  const running = ['queued', 'running'].includes(job.status)
  const pct = job.total ? Math.min(100, Math.round(((job.done + job.failed) / job.total) * 100)) : running ? 5 : 100
  const last = job.log?.[job.log.length - 1]
  return (
    <div className="rounded-xl border border-line bg-white p-4">
      <div className="flex items-center gap-3">
        {running ? <Loader2 className="size-4 animate-spin text-sky-600" /> : job.status === 'failed' ? <AlertTriangle className="size-4 text-red-500" /> : <CheckCircle2 className="size-4 text-lime-2" />}
        <div className="font-medium">{job.title}</div>
        <JobStatus s={job.status} />
        <div className="ml-auto flex items-center gap-4 text-xs text-mute num">
          <span>成功 {job.done}</span>
          {job.failed > 0 && <span className="text-red-600">失败 {job.failed}</span>}
          <span>新入库 {job.new_count}</span>
          <span>${job.cost_usd?.toFixed(4)}{job.cost_cny ? ` + ¥${job.cost_cny.toFixed(3)}` : ''}</span>
          {running && <Button size="sm" variant="ghost" onClick={async () => { await api(`/jobs/${job.id}/cancel`, { method: 'POST' }); qc.invalidateQueries() }}><Square className="size-3" />停止</Button>}
        </div>
      </div>
      <div className="mt-3 h-1.5 rounded-full bg-black/5 overflow-hidden">
        <div className={`h-full transition-all ${job.status === 'failed' ? 'bg-red-400' : running ? 'bg-sky-500' : 'bg-lime-2'}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-2 text-xs text-mute flex justify-between">
        <span className={last?.level === 'error' || job.error ? 'text-red-600' : last?.level === 'warn' ? 'text-amber-700' : ''}>{job.error || last?.msg || '等待开始…'}</span>
        <span>{ago(job.created)}</span>
      </div>
    </div>
  )
}
