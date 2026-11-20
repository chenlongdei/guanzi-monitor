import { useQuery } from '@tanstack/react-query'
import { History, Search } from 'lucide-react'
import { useState } from 'react'
import { ago, api, PLATFORMS } from '../api'
import ContentTable from '../components/ContentTable'
import { JobProgress, useJob, useRunJob } from '../components/jobs'
import MonitorButton from '../components/MonitorDialog'
import { Badge, Button, Card, Input, PageHeader, PlatformBadge, Segmented, Select, Toggle } from '../components/ui'

const DAYS: Record<string, [number, string][]> = {
  douyin_index: [[0, '不限'], [3, '近 3 天'], [7, '近 7 天'], [30, '近 30 天']],
  douyin: [[0, '不限'], [1, '近 1 天'], [7, '近 7 天'], [180, '近半年']],
  xhs: [[0, '不限'], [1, '近 1 天'], [7, '近 7 天'], [30, '近 30 天']],
  sph: [[0, '不限'], [1, '近 1 天'], [7, '近 7 天'], [180, '近半年']],
}

export default function Keyword() {
  const { data: s } = useQuery({ queryKey: ['settings'], queryFn: () => api('/settings') })
  const [platform, setPlatform] = useState<'douyin' | 'xhs' | 'sph'>('douyin')
  const [kw, setKw] = useState('')
  const [sort, setSort] = useState('relevance')
  const [days, setDays] = useState(7)
  const [limit, setLimit] = useState(20)
  const [tr, setTr] = useState(false)
  const [engine, setEngine] = useState<string>('')
  const [label, setLabel] = useState('0')
  const [enrich, setEnrich] = useState(true)
  const [jobId, setJobId] = useState<number | null>(null)
  const run = useRunJob()
  const { data: job } = useJob(jobId)
  const { data: hist } = useQuery({ queryKey: ['jobs', 'keyword', jobId], queryFn: () => api<any[]>('/jobs?kind=keyword&limit=12') })
  const { data: monitors } = useQuery({ queryKey: ['monitors'], queryFn: () => api<any[]>('/monitors?kind=keyword') })
  const eng = engine || s?.douyin_search_engine || 'index'
  const isIndex = platform === 'douyin' && eng === 'index'
  const dayOpts = DAYS[isIndex ? 'douyin_index' : platform]
  const start = () => {
    if (!kw.trim()) return
    const opts: any = {}
    if (platform === 'douyin') { opts.engine = eng; if (isIndex && label !== '0') opts.label_type = Number(label) }
    if (isIndex || platform === 'sph') opts.enrich = enrich
    run('keyword', { platform, keyword: kw.trim(), sort, days, limit, transcribe: tr, opts }, setJobId)
  }
  const p = job?.params || {}
  const existing = monitors?.find((m) => m.platform === p.platform && m.target === p.keyword)
  const newIds = new Set<number>((job?.results || []).filter((r: any) => !r.seen_before).map((r: any) => r.id))
  return (
    <div>
      <PageHeader title="关键词" desc="按关键词搜一批内容，看数据、挑几条转逐字稿；值得长期盯的，加入关键词监控" />
      <Card>
        <div className="flex items-center gap-3 flex-wrap">
          <Segmented value={platform} onChange={(v) => { setPlatform(v); setDays(7) }} options={[['douyin', '抖音'], ['xhs', '小红书'], ['sph', '视频号']]} />
          {platform === 'douyin' && (
            <Segmented value={eng} onChange={setEngine} options={[['index', '抖音指数'], ['search', '站内搜索']]} />
          )}
        </div>
        <div className="mt-3 flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-mute" />
            <Input value={kw} onChange={(e) => setKw(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && start()} placeholder="输入关键词，比如：AI 办公" className="w-full pl-9 h-10" />
          </div>
          <Button variant="primary" className="h-10" disabled={!kw.trim()} onClick={start}>搜索</Button>
        </div>
        <div className="mt-3 flex items-center gap-4 flex-wrap text-sm">
          <label className="flex items-center gap-2"><span className="text-mute">排序</span>
            <Select value={sort} onChange={setSort} options={isIndex ? [['relevance', '指数排名'], ['likes', '点赞最多'], ['newest', '最新发布']] : [['relevance', '综合'], ['likes', '最热'], ['newest', '最新']]} />
          </label>
          <label className="flex items-center gap-2"><span className="text-mute">时间</span>
            <Select value={days} onChange={(v) => setDays(Number(v))} options={dayOpts} />
          </label>
          {isIndex && (
            <label className="flex items-center gap-2"><span className="text-mute">类型</span>
              <Select value={label} onChange={setLabel} options={[['0', '不限'], ['1', '低粉爆款'], ['2', '高完播率'], ['3', '高涨粉率'], ['4', '高点赞率']]} />
            </label>
          )}
          <label className="flex items-center gap-2"><span className="text-mute">条数</span>
            <Select value={limit} onChange={(v) => setLimit(Number(v))} options={[[10, '10'], [20, '20'], [30, '30'], [50, '50'], [100, '100']]} />
          </label>
          <Toggle checked={tr} onChange={setTr} label="同时转逐字稿" />
          {(isIndex || platform === 'sph') && (
            <Toggle checked={enrich} onChange={setEnrich}
              label={<span>补全评论/收藏/分享 <span className="text-mute text-xs">（每条约 {platform === 'sph' ? '$0.01' : '$0.0012'}，并行跑）</span></span>} />
          )}
          {platform === 'xhs' && <span className="text-xs text-mute">小红书搜索不支持按时间筛，取回来后本地过滤</span>}
          {isIndex && <span className="text-xs text-mute">抖音指数：带播放量、视频指数和爆款标签，一次 $0.001</span>}
        </div>
      </Card>

      {job ? (
        <div className="mt-5 space-y-3">
          <JobProgress job={job} />
          <ContentTable items={job.results || []} cols={['rank', 'author', 'published_at', 'views', 'likes', 'comments', 'saves', 'shares', 'transcript']}
            newIds={newIds} emptyText="搜索中…"
            toolbar={<>
              <PlatformBadge p={p.platform} /><span className="font-medium">「{p.keyword}」</span>
              <Badge>{(job.results || []).length} 条</Badge>
              {newIds.size > 0 && <Badge tone="lime">新入库 {newIds.size}</Badge>}
              <MonitorButton kind="keyword" platform={p.platform} target={p.keyword} label={p.keyword}
                params={{ sort: p.sort, days: p.days, ...(p.opts || {}) }} disabled={job.status === 'running'} existing={existing} />
            </>} />
        </div>
      ) : hist && hist.length > 0 && (
        <Card className="mt-5" title={<span className="flex items-center gap-2"><History className="size-4" />搜索记录</span>} pad={false}>
          <div className="divide-y divide-line">
            {hist.map((j) => (
              <button key={j.id} onClick={() => setJobId(j.id)} className="w-full flex items-center gap-3 px-4 h-11 hover:bg-paper/70 text-sm text-left cursor-pointer">
                <PlatformBadge p={j.platform} />
                <span className="flex-1">{j.params.keyword}{j.monitor_id ? <span className="text-mute"> · 监控</span> : null}</span>
                <span className="text-xs text-mute">{j.params.opts?.engine === 'search' ? '站内搜索 · ' : j.platform === 'douyin' ? '抖音指数 · ' : ''}{j.done} 条 · 新 {j.new_count}</span>
                <span className="text-xs text-mute w-20 text-right">{ago(j.created)}</span>
              </button>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

export { PLATFORMS }
