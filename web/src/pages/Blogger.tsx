import { useQuery } from '@tanstack/react-query'
import { BellRing, Download } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ago, api, fmtNum } from '../api'
import { JobProgress, useJob, useRunJob } from '../components/jobs'
import { Avatar, Badge, Button, Card, Empty, Input, PageHeader, PlatformBadge, Segmented, Select, Toggle } from '../components/ui'

export default function Blogger() {
  const [input, setInput] = useState('')
  const [platform, setPlatform] = useState('')
  const [limit, setLimit] = useState(20)
  const [tr, setTr] = useState(false)
  const [jobId, setJobId] = useState<number | null>(null)
  const [filter, setFilter] = useState('')
  const [q, setQ] = useState('')
  const run = useRunJob()
  const nav = useNavigate()
  const { data: job } = useJob(jobId)
  const { data: authors } = useQuery({ queryKey: ['authors', filter, q], queryFn: () => api<any[]>(`/authors?platform=${filter}&q=${encodeURIComponent(q)}`), refetchInterval: job?.status === 'running' ? 2000 : false })
  useEffect(() => {
    if (job && job.status !== 'running' && job.status !== 'queued' && job.params?.author_pk) nav(`/author/${job.params.author_pk}`)
  }, [job?.status])
  return (
    <div>
      <PageHeader title="博主" desc="粘贴博主主页链接（视频号用 sph 开头的 ID），拉最近 N 条作品；进入博主页可以加监控" />
      <Card>
        <div className="flex items-center gap-2">
          <Input value={input} onChange={(e) => setInput(e.target.value)} className="flex-1 h-10"
            placeholder="https://www.douyin.com/user/MS4wLjAB…   /   https://www.xiaohongshu.com/user/profile/…   /   sphXXXX" />
          <Button variant="primary" className="h-10" disabled={!input.trim()} onClick={() => run('blogger', { input, platform: platform || undefined, limit, transcribe: tr }, setJobId)}>拉取作品</Button>
        </div>
        <div className="mt-3 flex items-center gap-4 text-sm">
          <label className="flex items-center gap-2"><span className="text-mute">平台</span>
            <Select value={platform} onChange={setPlatform} options={[['', '自动识别'], ['douyin', '抖音'], ['xhs', '小红书'], ['sph', '视频号']]} />
          </label>
          <label className="flex items-center gap-2"><span className="text-mute">最近</span>
            <Select value={limit} onChange={(v) => setLimit(Number(v))} options={[[10, '10 条'], [20, '20 条'], [50, '50 条'], [100, '100 条'], [300, '300 条']]} />
          </label>
          <Toggle checked={tr} onChange={setTr} label="全部转逐字稿" />
          <span className="text-xs text-mute">要某个抖音博主全部历史，用 Get笔记订阅导出更省钱</span>
        </div>
      </Card>
      {job && <div className="mt-4"><JobProgress job={job} /></div>}

      <div className="mt-6 flex items-center justify-between mb-3">
        <div className="font-semibold">库里的博主</div>
        <div className="flex items-center gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜昵称" className="w-44" />
          <Segmented value={filter} onChange={setFilter} options={[['', '全部'], ['douyin', '抖音'], ['xhs', '小红书'], ['sph', '视频号']]} />
        </div>
      </div>
      {!authors?.length ? <Card><Empty>还没有博主。上面拉一个，或者关键词搜到的作者也会自动进来</Empty></Card> : (
        <div className="grid grid-cols-3 gap-3">
          {authors.map((a) => (
            <button key={a.id} onClick={() => nav(`/author/${a.id}`)} className="text-left rounded-xl border border-line bg-white p-4 hover:border-ink transition cursor-pointer">
              <div className="flex items-center gap-3">
                <Avatar src={a.avatar} name={a.nickname} size={40} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5"><span className="font-medium truncate">{a.nickname || a.author_id}</span><PlatformBadge p={a.platform} /></div>
                  <div className="text-xs text-mute mt-0.5 num">粉丝 {fmtNum(a.followers)} · 库里 {a.content_count} 条</div>
                </div>
                {a.monitor_id && <Badge tone="ink"><BellRing className="size-3" />监控</Badge>}
              </div>
              <div className="mt-2 text-xs text-mute flex justify-between">
                <span>{a.profile_fetched ? '已拉过主页' : '从内容里带进来的'}</span><span>{ago(a.last_seen)}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export { Download }
