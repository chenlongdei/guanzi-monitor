import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Play, RotateCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ago, api } from '../api'
import ContentTable from '../components/ContentTable'
import { JobProgress, useJob, useRunJob } from '../components/jobs'
import { Badge, Button, Card, PageHeader, PlatformBadge, Textarea, Toggle } from '../components/ui'

export default function Single() {
  const [text, setText] = useState('')
  const [tr, setTr] = useState(true)
  const [jobId, setJobId] = useState<number | null>(null)
  const run = useRunJob()
  const qc = useQueryClient()
  const { data: job } = useJob(jobId)
  const [parsed, setParsed] = useState<any[]>([])
  useEffect(() => {
    const t = setTimeout(async () => {
      if (!text.trim()) return setParsed([])
      // 只做本地识别预览：不跟短链，前端用正则
      const urls = text.match(/https?:\/\/[^\s，。,；;）)】\]"'<>]+/g) || text.split('\n').filter((x) => x.trim())
      setParsed(urls.map((u) => ({
        raw: u, platform: /douyin/.test(u) ? 'douyin' : /xiaohongshu|xhslink/.test(u) ? 'xhs' : /weixin\.qq/.test(u) ? 'sph' : /^\d{15,21}$/.test(u.trim()) ? 'douyin' : null,
      })))
    }, 200)
    return () => clearTimeout(t)
  }, [text])

  const running = job && ['queued', 'running'].includes(job.status)
  // 最近单条采集到的内容：直接列内容本身；有转写中的就自动刷新
  const { data: recent } = useQuery({
    queryKey: ['contents', 'single-recent', job?.status, job?.done],
    queryFn: () => api('/contents?source=single&sort=first_seen&order=desc&size=50'),
    refetchInterval: (q) => (q.state.data?.items?.some((c: any) => c.transcript_status === 'running') ? 3000 : false),
  })
  // 失败的链接：从最近的单条任务日志里取
  const { data: jobs } = useQuery({ queryKey: ['jobs', 'single', job?.status], queryFn: () => api<any[]>('/jobs?kind=single&limit=20') })
  const failedJobs = (jobs || []).filter((j) => j.failed > 0 && !['queued', 'running'].includes(j.status)).slice(0, 5)
  const { data: failedDetails } = useQuery({
    queryKey: ['jobs', 'single-failed', failedJobs.map((j) => j.id).join(',')],
    enabled: failedJobs.length > 0,
    queryFn: () => Promise.all(failedJobs.map((j) => api(`/jobs/${j.id}`))),
  })
  const failures = (failedDetails || []).flatMap((j: any) => {
    const logs = j.log || []
    const out: { job: any; link: string; reason: string }[] = []
    logs.forEach((l: any, i: number) => {
      if (l.level !== 'warn') return
      const m = l.msg.match(/^失败：(.*)$/)
      if (m) {
        const prev = logs.slice(0, i).reverse().find((x: any) => /^\[\d+\/\d+\]/.test(x.msg))
        out.push({ job: j, link: prev ? prev.msg.replace(/^\[\d+\/\d+\]\s*\S+\s*/, '') : '', reason: m[1] })
      } else if (/：/.test(l.msg) && !/转写/.test(l.msg)) {
        const [link, ...rest] = l.msg.split('：')
        out.push({ job: j, link, reason: rest.join('：') })
      }
    })
    return out
  })
  // 之后已经采成功的链接，不再算「没采到」
  const succeededLater = (link: string, afterId: number) =>
    (jobs || []).some((j) => j.id > afterId && j.done > 0 && j.failed === 0 && String(j.params?.text || '').includes(link))
  const openFailures = failures.filter((f) => !(f.link && succeededLater(f.link, f.job.id)))
  const retryLink = (link: string) => run('single', { text: link, transcribe: tr }, (id) => { setJobId(id); qc.invalidateQueries({ queryKey: ['jobs'] }) })

  const ok = parsed.filter((p) => p.platform).length
  return (
    <div>
      <PageHeader title="单条采集" desc="粘贴抖音、小红书、视频号的分享链接或分享文案，一行一条或混在一起都行" />
      <Card>
        <Textarea rows={6} value={text} onChange={(e) => setText(e.target.value)}
          placeholder={'7.82 复制打开抖音，看看【某某的作品】… https://v.douyin.com/xxxx/\nhttps://www.xiaohongshu.com/explore/xxxx\nhttps://weixin.qq.com/sph/xxxx'} />
        {parsed.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {parsed.map((p, i) => (
              <span key={i} className="inline-flex items-center gap-1.5 rounded-lg bg-paper px-2 h-7 text-xs max-w-[360px]">
                {p.platform ? <PlatformBadge p={p.platform} /> : <Badge tone="red">认不出</Badge>}
                <span className="truncate text-mute">{p.raw}</span>
              </span>
            ))}
          </div>
        )}
        <div className="mt-4 flex items-center justify-between">
          <Toggle checked={tr} onChange={setTr} label="同时转逐字稿（视频号暂不支持，图文自动跳过）" />
          <Button variant="primary" disabled={!ok} onClick={() => run('single', { text, transcribe: tr }, (id) => { setJobId(id); setText('') })}>
            <Play className="size-4" />开始采集 {ok ? `${ok} 条` : ''}
          </Button>
        </div>
      </Card>

      {job && running && <div className="mt-5"><JobProgress job={job} /></div>}

      <div className="mt-6">
        <ContentTable items={recent?.items || []} emptyText="还没有单条采集过的内容，粘贴链接开始"
          toolbar={<><span className="font-semibold">最近单条采集的内容</span>{recent?.total ? <Badge>{recent.total} 条</Badge> : null}</>} />
      </div>

      {openFailures.length > 0 && (
        <Card className="mt-4" title={<span className="flex items-center gap-2"><AlertTriangle className="size-4 text-amber-600" />没采到的链接</span>} pad={false}>
          <div className="divide-y divide-line">
            {openFailures.map((f, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="truncate">{f.link || '（链接未记录）'}</div>
                  <div className="text-xs text-red-600 truncate">{f.reason}</div>
                </div>
                <span className="text-xs text-mute shrink-0">{ago(f.job.created)}</span>
                {f.link.startsWith('http') && <Button size="sm" onClick={() => retryLink(f.link)}><RotateCcw className="size-3.5" />重试</Button>}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
