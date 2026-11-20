import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Dna, FileText } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ago, api } from '../api'
import { JobProgress, useJob, useRunJob } from './jobs'
import { Button, Card, Select, Toggle } from './ui'

export const SCORE_KEYS = ['真实性', '权力', '情感', '逻辑', '具体', '行动']

/** 博主页里的「文风 DNA」：选条数 → 估费确认 → 后台跑 → 历次报告列表。 */
export default function StyleDNA({ author }: { author: any }) {
  const run = useRunJob()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [limit, setLimit] = useState(30)
  const [transcribe, setTranscribe] = useState(true)
  const [jobId, setJobId] = useState<number | null>(null)
  const { data: job } = useJob(jobId)
  const { data: reports = [] } = useQuery({ queryKey: ['style-reports', author.id], queryFn: () => api<any[]>(`/authors/${author.id}/style-reports`) })
  const total = author.stats.total
  const untranscribed = author.contents.slice(0, limit || undefined).filter((c: any) => c.transcript_status !== 'done' && c.type !== 'image' && c.platform !== 'sph').length

  useEffect(() => {
    if (job && !['queued', 'running'].includes(job.status)) qc.invalidateQueries({ queryKey: ['style-reports', author.id] })
  }, [job?.status])

  return (
    <Card className="mt-4" title={<span className="flex items-center gap-2"><Dna className="size-4" />文风 DNA</span>}
      extra={<span className="text-xs text-mute">本体论 / 认识论 / 意识形态 / 修辞 / 六维评分 / 仿写提示词</span>}>
      <div className="flex items-center gap-3 flex-wrap">
        <Select value={limit} onChange={(v) => setLimit(Number(v))}
          options={[[10, '最近 10 条'], [30, '最近 30 条'], [50, '最近 50 条'], [100, '最近 100 条'], [0, `全部（库里 ${total} 条）`]]} />
        <Toggle checked={transcribe} onChange={setTranscribe} label={`先转写没逐字稿的${untranscribed ? `（${untranscribed} 条）` : ''}`} />
        <Button variant="primary" disabled={!total}
          onClick={() => run('style', { author_pk: author.id, limit, transcribe_missing: transcribe && untranscribed > 0 }, setJobId)}>
          <Dna className="size-4" />开始分析
        </Button>
        {!total && <span className="text-xs text-mute">先「拉取最新」把作品拉进库</span>}
        {total > 0 && limit > total && <span className="text-xs text-mute">库里只有 {total} 条，想分析更多先拉取更多作品</span>}
      </div>
      <p className="mt-2 text-xs text-mute">逐字稿优先，没有逐字稿的用文案。条数越多结论越稳，建议至少 20 条。</p>

      {job && <div className="mt-3"><JobProgress job={job} /></div>}

      {reports.length > 0 && (
        <div className="mt-4 divide-y divide-line border-t border-line">
          {reports.map((r) => (
            <button key={r.id} onClick={() => nav(`/style/${r.id}`)} className="w-full text-left py-3 flex items-center gap-4 hover:bg-paper/60 cursor-pointer px-1 rounded">
              <FileText className="size-4 text-mute shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{r.summary || '文风 DNA 报告'}</div>
                <div className="text-xs text-mute mt-0.5 num">{r.n_items} 条 · {r.model} · ${r.cost_usd} · {ago(r.created)}</div>
              </div>
              <div className="flex gap-1.5 shrink-0">
                {SCORE_KEYS.map((k) => r.scores?.[k] !== undefined && (
                  <div key={k} className="text-center w-9">
                    <div className="text-[10px] text-mute">{k}</div>
                    <div className="text-sm font-semibold num">{r.scores[k]}</div>
                  </div>
                ))}
              </div>
            </button>
          ))}
        </div>
      )}
    </Card>
  )
}
