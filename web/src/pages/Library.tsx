import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Download, Search } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import ContentTable from '../components/ContentTable'
import { Button, Input, PageHeader, Segmented, Select } from '../components/ui'

export default function Library() {
  const [platform, setPlatform] = useState('')
  const [q, setQ] = useState('')
  const [qq, setQq] = useState('')
  const [source, setSource] = useState('')
  const [transcript, setTranscript] = useState('')
  const [sort, setSort] = useState('first_seen')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(1)
  const size = 50
  const params = new URLSearchParams({ platform, q: qq, source, transcript, sort, order, page: String(page), size: String(size) })
  const { data } = useQuery({ queryKey: ['contents', params.toString()], queryFn: () => api(`/contents?${params}`), placeholderData: keepPreviousData })
  const pages = Math.max(1, Math.ceil((data?.total || 0) / size))
  const reset = (f: () => void) => { f(); setPage(1) }
  return (
    <div>
      <PageHeader title="内容库" desc={`所有采集过的内容，一条只存一份 · 共 ${data?.total ?? 0} 条`}
        extra={<Button onClick={() => window.open(`/api/contents/export?platform=${platform}`)}><Download className="size-4" />导出 xlsx</Button>} />
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <div className="relative">
          <Search className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-mute" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && reset(() => setQq(q))} placeholder="搜标题、文案、博主、逐字稿" className="pl-9 w-72" />
        </div>
        <Segmented value={platform} onChange={(v) => reset(() => setPlatform(v))} options={[['', '全部'], ['douyin', '抖音'], ['xhs', '小红书'], ['sph', '视频号']]} />
        <Select value={source} onChange={(v) => reset(() => setSource(v))} options={[['', '全部来源'], ['single', '单条采集'], ['keyword', '关键词'], ['blogger', '博主']]} />
        <Select value={transcript} onChange={(v) => reset(() => setTranscript(v))} options={[['', '逐字稿：全部'], ['done', '已转写'], ['none', '未转写'], ['failed', '转写失败'], ['na', '图文']]} />
      </div>
      <ContentTable items={data?.items || []} sortable="remote" sort={sort} order={order}
        cols={['author', 'published_at', 'views', 'likes', 'comments', 'saves', 'shares', 'transcript', 'source']}
        onSort={(k) => reset(() => { if (k === sort) setOrder(order === 'desc' ? 'asc' : 'desc'); else { setSort(k); setOrder('desc') } })}
        emptyText="没有符合条件的内容" />
      {pages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-4 text-sm">
          <Button size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</Button>
          <span className="text-mute num">{page} / {pages}</span>
          <Button size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>下一页</Button>
        </div>
      )}
    </div>
  )
}
