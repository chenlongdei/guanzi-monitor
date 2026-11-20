import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Copy, ExternalLink, FileText, Hash, Link2, RefreshCw, Sparkles, Users } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, engagement, fmtDur, fmtNum, fmtTime, PLATFORMS } from '../api'
import { useRunJob } from '../components/jobs'
import MonitorButton from '../components/MonitorDialog'
import Trend from '../components/Trend'
import { Avatar, Badge, Button, Card, Cover, Empty, PlatformBadge, TranscriptBadge } from '../components/ui'

const SRC_ICON: Record<string, any> = { keyword: Hash, blogger: Users, single: Link2, refresh: RefreshCw }

function mmss(s: number) { return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}` }

export default function ContentDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const run = useRunJob()
  const [copied, setCopied] = useState(false)
  const { data: c } = useQuery({
    queryKey: ['content', id], queryFn: () => api(`/contents/${id}`),
    refetchInterval: (q) => (q.state.data?.transcript_status === 'running' ? 2000 : false),
  })
  if (!c) return null
  const a = c.author
  const cues: [number, string][] = c.transcript || []
  const hook = cues.filter(([s]) => s < 5).map(([, t]) => t).join('')
  const ending = cues.length > 3 ? cues.slice(-2).map(([, t]) => t).join('') : ''
  const fullText = cues.map(([, t]) => t).join('')
  const er = engagement(c)
  const metrics: [string, number | null][] = [['播放', c.views], ['点赞', c.likes], ['评论', c.comments], ['收藏', c.saves], ['分享', c.shares]]
  const copy = () => { navigator.clipboard.writeText(fullText); setCopied(true); setTimeout(() => setCopied(false), 1500) }
  const refresh = () => run('refresh', { content_ids: [c.id] }, () => setTimeout(() => qc.invalidateQueries({ queryKey: ['content', id] }), 4000))
  const transcribe = (force = false) => run('transcribe', { content_ids: [c.id], force }, () => setTimeout(() => qc.invalidateQueries({ queryKey: ['content', id] }), 800))

  return (
    <div>
      <button onClick={() => nav(-1)} className="flex items-center gap-1 text-sm text-mute hover:text-ink mb-4 cursor-pointer"><ArrowLeft className="size-4" />返回</button>

      <div className="flex items-start justify-between gap-4 mb-5">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <PlatformBadge p={c.platform} />
            <Badge>{c.type === 'image' ? '图文' : '视频'}</Badge>
            {(c.extra?.index_labels || []).map((t: string) => <Badge key={t} tone="amber">{t}</Badge>)}
            {c.extra?.index && <Badge tone="ink">视频指数 {fmtNum(c.extra.index)}</Badge>}
            {c.extra?.no_voice && <Badge tone="gray">可能无口播</Badge>}
          </div>
          <h1 className="text-xl font-semibold leading-snug">{c.title || '（无标题）'}</h1>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button onClick={refresh}><RefreshCw className="size-4" />刷新数据</Button>
          {c.url && <Button onClick={() => window.open(c.url)}><ExternalLink className="size-4" />打开原链接</Button>}
        </div>
      </div>

      <div className="grid grid-cols-[260px_1fr] gap-4">
        <div>
          <Cover src={c.cover} className="w-full aspect-[3/4] rounded-xl" />
          <div className="mt-3 text-sm space-y-1.5 text-mute">
            <div className="flex justify-between"><span>发布</span><span className="text-ink num">{fmtTime(c.published_at)}</span></div>
            <div className="flex justify-between"><span>时长</span><span className="text-ink num">{fmtDur(c.duration_s)}</span></div>
            <div className="flex justify-between"><span>首次采集</span><span className="text-ink num">{fmtTime(c.first_seen)}</span></div>
            <div className="flex justify-between"><span>最近更新</span><span className="text-ink num">{fmtTime(c.last_seen)}</span></div>
            <div className="flex justify-between"><span>渠道</span><span className="text-ink">{c.provider}</span></div>
          </div>
        </div>

        <div className="space-y-4 min-w-0">
          {a && (
            <Card>
              <div className="flex items-center gap-3">
                <Avatar src={a.avatar} name={a.nickname} size={44} />
                <div className="flex-1 min-w-0">
                  <div className="font-medium">{a.nickname}</div>
                  <div className="text-xs text-mute num">{PLATFORMS[a.platform]} · 粉丝 {fmtNum(a.snap?.followers ?? c.extra?.author_fans)}{a.snap?.posts ? ` · 作品 ${a.snap.posts}` : ''}</div>
                </div>
                <Link to={`/author/${a.id}`}><Button>进入主页</Button></Link>
                <MonitorButton kind="blogger" platform={a.platform} target={String(a.id)} label={a.nickname} existing={a.monitor} />
              </div>
            </Card>
          )}

          <div className="grid grid-cols-6 gap-2">
            {metrics.map(([l, v]) => (
              <div key={l} className="rounded-xl bg-white border border-line p-3">
                <div className="text-xs text-mute">{l}</div>
                <div className="mt-1 text-lg font-semibold num">{fmtNum(v)}</div>
              </div>
            ))}
            <div className="rounded-xl bg-ink p-3">
              <div className="text-xs text-white/60">互动率</div>
              <div className="mt-1 text-lg font-semibold num text-lime">{er === null ? '—' : (er * 100).toFixed(1) + '%'}</div>
            </div>
          </div>
          {c.views === null && c.platform === 'douyin' && <p className="text-xs text-mute -mt-2">抖音的这几个接口都不返回播放量，所以显示「—」，不是 0。</p>}

          {c.snapshots.length >= 2 && (
            <Card title="数据走势" extra={<span className="text-xs text-mute">{c.snapshots.length} 次快照</span>}>
              <Trend data={c.snapshots} keys={[['likes', '点赞', '#111311'], ['saves', '收藏', '#7cb305'], ['comments', '评论', '#f59a23']]} />
            </Card>
          )}

          <Card title={<span className="flex items-center gap-2"><FileText className="size-4" />逐字稿 <TranscriptBadge s={c.transcript_status} /></span>}
            extra={<>
              {cues.length > 0 && <Button size="sm" onClick={copy}><Copy className="size-3.5" />{copied ? '已复制' : '复制'}</Button>}
              {c.transcript_path && <a href={`/api/contents/${c.id}/transcript.md`} download><Button size="sm" variant="ghost">下载 md</Button></a>}
              {c.transcript_status === 'done' && <Button size="sm" variant="ghost" onClick={() => transcribe(true)}>重新转写</Button>}
            </>}>
            {c.transcript_status === 'done' && cues.length > 0 ? (
              <div className="space-y-4">
                {c.extra?.no_voice && <div className="rounded-lg bg-paper text-sm text-mute px-3 py-2">转写出来的字很少，多半是纯音乐或画面类视频，没有口播。</div>}
                {hook && <div><div className="text-xs text-mute mb-1">前 5 秒钩子</div><div className="rounded-lg bg-lime/40 px-3 py-2 font-medium">{hook}</div></div>}
                <div>
                  <div className="text-xs text-mute mb-1">正文</div>
                  <div className="text-[15px] leading-7 space-y-1">
                    {cues.map(([s, t], i) => (
                      <p key={i} className="flex gap-3"><span className="text-xs text-mute num w-10 shrink-0 pt-1">{mmss(s)}</span><span>{t}</span></p>
                    ))}
                  </div>
                </div>
                {ending && <div><div className="text-xs text-mute mb-1">结尾</div><div className="rounded-lg bg-paper px-3 py-2">{ending}</div></div>}
              </div>
            ) : c.type === 'image' ? (
              <div className="whitespace-pre-wrap text-[15px] leading-7">{c.caption || '（无正文）'}</div>
            ) : c.transcript_status === 'running' ? <Empty>转写中，通常 10—60 秒…</Empty> : (
              <div className="text-center py-8">
                {c.transcript_error && <p className="text-sm text-red-600 mb-3">{c.transcript_error}</p>}
                <Button variant="primary" disabled={c.platform === 'sph'} onClick={() => transcribe()}><Sparkles className="size-4" />转逐字稿</Button>
                {c.platform === 'sph' && <p className="text-xs text-mute mt-2">视频号的视频文件是加密的，第一期暂不支持转写</p>}
              </div>
            )}
          </Card>

          {c.caption && c.type !== 'image' && (
            <Card title="文案"><div className="whitespace-pre-wrap text-sm leading-6">{c.caption}</div>
              {c.tags?.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{c.tags.map((t: string) => <Badge key={t}>#{t}</Badge>)}</div>}
            </Card>
          )}

          <Card title="来源" extra={<span className="text-xs text-mute">一条内容只存一份，每次从哪来都记在这里</span>} pad={false}>
            <div className="divide-y divide-line">
              {c.sources.map((s: any) => {
                const Icon = SRC_ICON[s.kind] || Link2
                return (
                  <div key={s.id} className="flex items-center gap-3 px-4 h-11 text-sm">
                    <Icon className="size-4 text-mute" />
                    <span className="flex-1">{s.label}{s.rank ? <span className="text-mute"> · 第 {s.rank} 名</span> : null}{s.monitor_id ? <Badge className="ml-2" tone="ink">监控</Badge> : null}</span>
                    {s.job_id && <Link to={`/jobs/${s.job_id}`} className="text-xs text-mute hover:text-ink">任务 #{s.job_id}</Link>}
                    <span className="text-xs text-mute num w-32 text-right">{fmtTime(s.ts)}</span>
                  </div>
                )
              })}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
