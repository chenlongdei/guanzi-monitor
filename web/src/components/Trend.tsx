import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtNum, fmtTime } from '../api'

/** 快照走势：只有两次以上快照才画。 */
export default function Trend({ data, keys, height = 160 }: { data: any[]; keys: [string, string, string][]; height?: number }) {
  const rows = data.map((d) => ({ ...d, t: fmtTime(d.ts).slice(5) }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#eceee8" vertical={false} />
        <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#6b7068' }} tickLine={false} axisLine={false} minTickGap={24} />
        <YAxis tick={{ fontSize: 11, fill: '#6b7068' }} tickLine={false} axisLine={false} width={44} tickFormatter={(v) => fmtNum(v)} />
        <Tooltip formatter={(v: any, n: any) => [fmtNum(v), n]} contentStyle={{ borderRadius: 8, border: '1px solid #e4e6df', fontSize: 12 }} />
        {keys.map(([k, name, color]) => <Line key={k} type="monotone" dataKey={k} name={name} stroke={color} strokeWidth={2} dot={{ r: 2.5 }} connectNulls />)}
      </LineChart>
    </ResponsiveContainer>
  )
}
