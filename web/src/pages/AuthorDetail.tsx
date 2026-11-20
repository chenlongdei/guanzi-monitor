import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, ExternalLink, RefreshCw, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ago, api, fmtNum, until } from '../api'
import ContentTable from '../components/ContentTable'
import { JobProgress, useJob, useRunJob } from '../components/jobs'
import MonitorButton, { INTERVALS } from '../components/MonitorDialog'
import StyleDNA from '../components/StyleDNA'
import Trend from '../components/Trend'
import { Avatar, Badge, Button, Card, PlatformBadge, Segmented, Select } from '../components/ui'

export default function AuthorDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const run = useRunJob()
  const [jobId, setJobId] = useState<number | null>(null)
  const [limit, setLimit] = useState(20)
  const [view, setView] = useState<'all' | 'hot' | 'done' | 'none'>('all')
  const { data: job } = useJob(jobId)
  const { data: a } = useQuery({ queryKey: ['author', id, job?.status], queryFn: () => api(`/authors/${id}`), refetchInterval: job?.status === 'running' ? 2000 : false })
  if (!a) return null
  const l = a.latest || {}
  const items = a.contents.filter((c: any) => view === 'all' || (view === 'hot' ? c.hot : view === 'done' ? c.transcript_status === 'done' : c.transcript_status === 'none'))
  const untranscribed = a.contents.filter((c: any) => c.transcript_status === 'none').map((c: any) => c.id)
  const m = a.monitor
  const placeholder = String(a.author_id).startsWith('nick:')
  return (
    <div>
      <button onClick={() => nav(-1)} className="flex items-center gap-1 text-sm text-mute hover:text-ink mb-4 cursor-pointer"><ArrowLeft className="size-4" />返回</button>
      <Card>
        <div className="flex items-start gap-4">
          <Avatar src={a.avatar} name={a.nickname} size={72} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold">{a.nickname || a.author_id}</h1>
              <PlatformBadge p={a.platform} />
              {a.verified ? <Badge tone="blue">认证</Badge> : null}
            </div>
            {a.bio && <p className="mt-1.5 text-sm text-mute whitespace-pre-line line-clamp-3">{a.bio}</p>}
            <div className="mt-3 flex items-center gap-5 text-sm num">
              <span><b className="text-base">{fmtNum(l.followers)}</b> <span className="text-mute">粉丝</span></span>
              <span><b className="text-base">{fmtNum(l.likes)}</b> <span className="text-mute">获赞</span></span>
              <span><b className="text-base">{fmtNum(l.posts)}</b> <span className="text-mute">作品</span></span>
              <span className="text-mute">库里 {a.stats.total} 条 · 已转写 {a.stats.transcribed}</span>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="flex gap-2">
              {a.url && <Button variant="ghost" onClick={() => window.open(a.url)}><ExternalLink className="size-4" />主页</Button>}
              <MonitorButton kind="blogger" platform={a.platform} target={String(a.id)} label={a.nickname} existing={m} />
            </div>
            {m && (
              <div className="text-xs text-mute flex items-center gap-2">
                <Badge tone={m.enabled ? 'ink' : 'gray'}>{m.enabled ? '监控中' : '已暂停'}</Badge>
                {INTERVALS.find(([h]) => h === m.interval_hours)?.[1] || `每 ${m.interval_hours} 小时`} · 上次 {ago(m.last_run)} · 下次 {until(m.next_run)}
              </div>
            )}
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-line flex items-center gap-2">
          <Select value={limit} onChange={(v) => setLimit(Number(v))} options={[[10, '最近 10 条'], [20, '最近 20 条'], [50, '最近 50 条'], [100, '最近 100 条']]} />
          <Button variant="primary" onClick={() => run('blogger', { platform: a.platform, ref: { author_id: a.author_id, sec_uid: a.sec_uid, username: a.author_id }, limit }, setJobId)}>
            <RefreshCw className="size-4" />拉取最新
          </Button>
          <Button disabled={!untranscribed.length} onClick={() => run('transcribe', { content_ids: untranscribed }, () => setTimeout(() => qc.invalidateQueries(), 1000))}>
            <Sparkles className="size-4" />全部转写（{untranscribed.length}）
          </Button>
          <Button onClick={() => window.open(`/api/contents/export?author=${a.id}`)}><Download className="size-4" />导出 xlsx</Button>
          {placeholder && <span className="text-xs text-mute ml-2">这个博主是从抖音指数带进来的，第一次拉取会先查一条作品补全主页 ID（约 $0.001）</span>}
        </div>
      </Card>

      {job && <div className="mt-4"><JobProgress job={job} /></div>}

      <div className="grid grid-cols-4 gap-3 mt-4">
        <div className="rounded-xl bg-white border border-line p-4"><div className="text-xs text-mute">近 30 天发布</div><div className="mt-1 text-2xl font-semibold num">{a.stats.recent_posts}</div><div className="text-xs text-mute">按库里已有的作品算</div></div>
        <div className="rounded-xl bg-white border border-line p-4"><div className="text-xs text-mute">近 30 天平均点赞</div><div className="mt-1 text-2xl font-semibold num">{fmtNum(a.stats.recent_avg_likes)}</div></div>
        <div className="rounded-xl bg-white border border-line p-4"><div className="text-xs text-mute">平均点赞（库里全部）</div><div className="mt-1 text-2xl font-semibold num">{fmtNum(a.stats.avg_likes)}</div></div>
        <div className="rounded-xl bg-ink p-4"><div className="text-xs text-white/60">爆款（≥ 均值 3 倍）</div><div className="mt-1 text-2xl font-semibold num text-lime">{a.stats.hot}</div></div>
      </div>

      {a.stats.baseline && a.stats.total >= 5 && (
        <div className="mt-3 rounded-xl bg-white border border-line px-4 py-3 text-sm flex items-center gap-6 flex-wrap num">
          <span className="text-mute">这个博主平时（库里作品的中位数）</span>
          <span>收藏率 <b>{a.stats.baseline.save_rate != null ? (a.stats.baseline.save_rate * 100).toFixed(0) + '%' : '—'}</b></span>
          <span>转发率 <b>{a.stats.baseline.share_rate != null ? (a.stats.baseline.share_rate * 100).toFixed(0) + '%' : '—'}</b></span>
          <span>评论率 <b>{a.stats.baseline.comment_rate != null ? (a.stats.baseline.comment_rate * 100).toFixed(1) + '%' : '—'}</b></span>
          <span>日均赞 <b>{fmtNum(a.stats.baseline.per_day)}</b></span>
          <span className="text-xs text-mute">下表「看点」里加粗的，是高出这个水平 1.5 倍以上的</span>
        </div>
      )}

      {a.snapshots.filter((s: any) => s.followers).length >= 2 && (
        <Card className="mt-4" title="粉丝走势"><Trend data={a.snapshots} keys={[['followers', '粉丝', '#111311']]} height={140} /></Card>
      )}

      <StyleDNA author={a} />

      <div className="mt-6">
        <ContentTable items={items} cols={['published_at', 'views', 'likes', 'comments', 'saves', 'shares', 'transcript']}
          toolbar={<>
            <span className="font-semibold">作品</span>
            <Segmented value={view} onChange={setView} options={[['all', `全部 ${a.contents.length}`], ['hot', `爆款 ${a.stats.hot}`], ['done', '已转写'], ['none', '未转写']]} />
          </>} />
      </div>
    </div>
  )
}
