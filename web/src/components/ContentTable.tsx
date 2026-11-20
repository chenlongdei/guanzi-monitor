import { useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowDown, ArrowUp, Download, FileText, RefreshCw, Sparkles } from 'lucide-react'
import { ReactNode, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, fmtDur, fmtNum, fmtTime } from '../api'
import { useRunJob } from './jobs'
import { Badge, Button, Cover, PlatformBadge, TranscriptBadge } from './ui'

type Col = 'rank' | 'author' | 'published_at' | 'views' | 'likes' | 'comments' | 'saves' | 'shares' | 'insight' | 'transcript' | 'source'

export default function ContentTable({ items, cols: cols0 = ['author', 'published_at', 'views', 'likes', 'comments', 'saves', 'shares', 'insight', 'transcript'],
  sortable = 'local', sort, order, onSort, toolbar, emptyText = '暂无内容', newIds, hotIds }: {
  items: any[]; cols?: Col[]; sortable?: 'local' | 'remote' | false; sort?: string; order?: 'asc' | 'desc'
  onSort?: (k: string) => void; toolbar?: ReactNode; emptyText?: string; newIds?: Set<number>; hotIds?: Set<number>
}) {
  const [sel, setSel] = useState<Set<number>>(new Set())
  const [ls, setLs] = useState<{ k: string; o: 'asc' | 'desc' } | null>(null)
  const nav = useNavigate()
  const run = useRunJob()
  const qc = useQueryClient()
  // 有点赞数据的表默认带「看点」列
  const cols: Col[] = cols0.includes('likes') && !cols0.includes('insight') ? [...cols0.slice(0, cols0.indexOf('shares') + 1 || cols0.length), 'insight', ...cols0.slice(cols0.indexOf('shares') + 1 || cols0.length)] as Col[] : cols0
  const [insSort, setInsSort] = useState('')
  const med = useMemo(() => batchMedians(items), [items])
  const rows = useMemo(() => {
    const k = insSort || (sortable === 'local' ? ls?.k : '')
    if (!k) return items
    const o = insSort ? 'desc' : ls?.o
    return [...items].sort((a, b) => ((getv(a, k) ?? -1) - (getv(b, k) ?? -1)) * (o === 'asc' ? 1 : -1))
  }, [items, ls, sortable, insSort])
  const curSort = sortable === 'local' ? ls?.k : sort
  const curOrder = sortable === 'local' ? ls?.o : order
  const clickSort = (k: string) => {
    if (sortable === 'remote') onSort?.(k)
    else if (sortable === 'local') setLs((p) => (p?.k === k ? { k, o: p.o === 'desc' ? 'asc' : 'desc' } : { k, o: 'desc' }))
  }
  const all = rows.length > 0 && rows.every((r) => sel.has(r.id))
  const toggle = (id: number) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const ids = [...sel]

  const H = ({ k, children, right = true }: { k?: string; children: ReactNode; right?: boolean }) => (
    <th className={clsx('px-3 font-medium text-mute text-xs whitespace-nowrap', right && 'text-right', k && sortable && 'cursor-pointer hover:text-ink select-none')}
      onClick={() => k && sortable && clickSort(k)}>
      <span className="inline-flex items-center gap-0.5">{children}{k && curSort === k && (curOrder === 'asc' ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}</span>
    </th>
  )

  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-3 min-h-9">
        <div className="flex items-center gap-2">{toolbar}
          {cols.includes('insight') && items.length > 1 && (
            <select value={insSort} onChange={(e) => setInsSort(e.target.value)} title="按看点指标排序（只排当前列表）"
              className="h-8 rounded-lg border border-line bg-white px-2 text-[13px] outline-none">
              <option value="">看点排序：默认</option>
              <option value="ins.save_rate">收藏率（干货度）</option>
              <option value="ins.share_rate">转发率（传播力）</option>
              <option value="ins.comment_rate">评论率（话题度）</option>
              <option value="ins.like_fan">赞粉比（破圈）</option>
              <option value="ins.multiple">超常倍数（相对博主自己）</option>
              <option value="ins.per_day">日均赞（起量速度）</option>
            </select>
          )}
        </div>
        <div className={clsx('flex items-center gap-2 transition', ids.length ? 'opacity-100' : 'opacity-0 pointer-events-none')}>
          <span className="text-sm text-mute">已选 {ids.length} 条</span>
          <Button size="sm" variant="primary" onClick={() => run('transcribe', { content_ids: ids, transcribe: true }, () => { setSel(new Set()); qc.invalidateQueries() })}>
            <Sparkles className="size-3.5" />转逐字稿
          </Button>
          <Button size="sm" onClick={() => run('refresh', { content_ids: ids }, () => setSel(new Set()))}><RefreshCw className="size-3.5" />刷新数据</Button>
          <Button size="sm" onClick={() => window.open(`/api/contents/export?ids=${ids.join(',')}`)}><Download className="size-3.5" />导出</Button>
        </div>
      </div>
      <div className="bg-white rounded-xl border border-line overflow-x-auto scroll-thin">
        <table className="w-full text-sm">
          <thead>
            <tr className="h-10 border-b border-line">
              <th className="w-10 pl-3"><input type="checkbox" checked={all} onChange={() => setSel(all ? new Set() : new Set(rows.map((r) => r.id)))} className="accent-ink" /></th>
              {cols.includes('rank') && <H k="rank" right={false}>#</H>}
              <th className="px-3 text-left font-medium text-mute text-xs">内容</th>
              {cols.includes('author') && <H right={false}>博主</H>}
              {cols.includes('published_at') && <H k="published_at">发布</H>}
              {cols.includes('views') && <H k="views">播放</H>}
              {cols.includes('likes') && <H k="likes">点赞</H>}
              {cols.includes('comments') && <H k="comments">评论</H>}
              {cols.includes('saves') && <H k="saves">收藏</H>}
              {cols.includes('shares') && <H k="shares">分享</H>}
              {cols.includes('insight') && <th className="px-3 text-left font-medium text-mute text-xs whitespace-nowrap" title={INSIGHT_HELP}>看点 ⓘ</th>}
              {cols.includes('transcript') && <H right={false}>逐字稿</H>}
              {cols.includes('source') && <H k="source_count">来源</H>}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={12} className="py-14 text-center text-mute">{emptyText}</td></tr>}
            {rows.map((c) => (
              <tr key={c.id} className={clsx('border-b border-line last:border-0 hover:bg-paper/70 cursor-pointer', sel.has(c.id) && 'bg-lime/10')}
                onClick={() => nav(`/content/${c.id}`)}>
                <td className="pl-3" onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={sel.has(c.id)} onChange={() => toggle(c.id)} className="accent-ink" /></td>
                {cols.includes('rank') && <td className="px-3 text-mute num">{c.rank ?? '—'}</td>}
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-3 min-w-[280px] max-w-[460px]">
                    <div className="relative shrink-0">
                      <Cover src={c.cover} className="w-11 h-14 rounded-md" />
                      {c.duration_s ? <span className="absolute bottom-0.5 right-0.5 text-[10px] bg-black/70 text-white rounded px-1 num">{fmtDur(c.duration_s)}</span> : null}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <PlatformBadge p={c.platform} />
                        {newIds?.has(c.id) && <Badge tone="lime">新</Badge>}
                        {(hotIds?.has(c.id) || c.hot) && <Badge tone="red">爆款</Badge>}
                        {c.seen_before > 0 && <Badge tone="gray">库里已有</Badge>}
                        {(c.extra?.index_labels || []).slice(0, 2).map((t: string) => <Badge key={t} tone="amber">{t}</Badge>)}
                      </div>
                      <div className="mt-1 line-clamp-2 leading-snug">{c.title || '（无标题）'}</div>
                    </div>
                  </div>
                </td>
                {cols.includes('author') && (
                  <td className="px-3 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                    {c.author_pk ? <Link to={`/author/${c.author_pk}`} className="hover:underline">{c.author_name || '—'}</Link> : '—'}
                  </td>
                )}
                {cols.includes('published_at') && <td className="px-3 text-right text-mute whitespace-nowrap num text-[13px]">{fmtTime(c.published_at, false)}</td>}
                {cols.includes('views') && <td className="px-3 text-right num">{fmtNum(c.views)}</td>}
                {cols.includes('likes') && <td className="px-3 text-right num font-medium">{fmtNum(c.likes)}</td>}
                {cols.includes('comments') && <td className="px-3 text-right num">{fmtNum(c.comments)}</td>}
                {cols.includes('saves') && <td className="px-3 text-right num">{fmtNum(c.saves)}</td>}
                {cols.includes('shares') && <td className="px-3 text-right num">{fmtNum(c.shares)}</td>}
                {cols.includes('insight') && <td className="px-3"><Insight c={c} med={med} /></td>}
                {cols.includes('transcript') && <td className="px-3"><TranscriptBadge s={c.transcript_status} /></td>}
                {cols.includes('source') && <td className="px-3 text-right text-mute num">{c.source_count ?? '—'}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function TranscriptIcon() { return <FileText className="size-3.5" /> }

// ---------------- 看点 ----------------
const INSIGHT_HELP = `没有播放量，所以都以点赞为分母，和这张表里其他内容比：
干货：收藏率高，看的人想留着照做
传播：转发率高，看的人愿意转给别人
讨论：评论率高，有话题或争议
破圈：点赞超过博主粉丝数，被推荐流量带起来
超常 ×N：是这个博主平时点赞的 N 倍
起量中：发布 3 天内、日均赞在这张表前 20%`

function getv(o: any, k: string) {
  return k.startsWith('ins.') ? o.ins?.[k.slice(4)] : o[k]
}

function median(v: number[]) {
  if (v.length < 5) return null
  const s = [...v].sort((a, b) => a - b)
  return s[Math.floor(s.length / 2)]
}

function batchMedians(items: any[]) {
  const pick = (k: string) => items.map((c) => c.ins?.[k]).filter((x) => typeof x === 'number')
  const pd = pick('per_day').sort((a, b) => b - a)
  return {
    save_rate: median(pick('save_rate')), share_rate: median(pick('share_rate')), comment_rate: median(pick('comment_rate')),
    per_day_top: pd.length >= 5 ? pd[Math.floor(pd.length * 0.2)] : null,
  }
}

export function insightTags(c: any, med: any): [string, 'lime' | 'amber' | 'blue' | 'red' | 'ink'][] {
  const i = c.ins || {}
  const t: [string, any][] = []
  const hi = (v: number | null, m: number | null, floor: number) => v != null && v >= Math.max((m ?? floor) * 1.5, floor)
  if (hi(i.save_rate, med.save_rate, 0.2)) t.push(['干货', 'lime'])
  if (hi(i.share_rate, med.share_rate, 0.3)) t.push(['传播', 'blue'])
  if (hi(i.comment_rate, med.comment_rate, 0.05)) t.push(['讨论', 'amber'])
  if (i.like_fan != null && i.like_fan >= 1 && (i.fans ?? 0) >= 1000) t.push(['破圈', 'red'])
  if (i.multiple != null && i.multiple >= 3) t.push([`超常 ×${i.multiple.toFixed(1)}`, 'ink'])
  if (i.age_days != null && i.age_days <= 3 && med.per_day_top != null && i.per_day >= med.per_day_top) t.push(['起量中', 'red'])
  return t
}

const pct = (v?: number | null) => (v == null ? '—' : v >= 1 ? `${v.toFixed(1)}x` : `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`)

export function Insight({ c, med }: { c: any; med: any }) {
  const i = c.ins || {}
  if (i.save_rate == null && i.like_fan == null && i.per_day == null) return <span className="text-xs text-mute">—</span>
  const tags = insightTags(c, med)
  const cell = (label: string, v: number | null, m: number | null) => (
    <span className={clsx(v != null && m != null && v >= m * 1.5 ? 'text-ink font-medium' : 'text-mute')}>{label} {pct(v)}</span>
  )
  return (
    <div className="min-w-[150px]">
      {tags.length > 0 && <div className="flex flex-wrap gap-1 mb-1">{tags.map(([l, tone]) => <Badge key={l} tone={tone}>{l}</Badge>)}</div>}
      <div className="text-[11px] leading-4 num flex flex-wrap gap-x-2">
        {i.save_rate != null && cell('藏', i.save_rate, med.save_rate)}
        {i.share_rate != null && cell('转', i.share_rate, med.share_rate)}
        {i.comment_rate != null && cell('评', i.comment_rate, med.comment_rate)}
        {i.like_fan != null && <span className="text-mute">赞粉比 {i.like_fan >= 0.01 ? i.like_fan.toFixed(2) : '<0.01'}</span>}
        {i.per_day != null && <span className="text-mute">日均赞 {fmtNum(i.per_day)}</span>}
      </div>
    </div>
  )
}
