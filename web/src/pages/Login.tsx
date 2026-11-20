import { useQueryClient } from '@tanstack/react-query'
import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Button, Input } from '../components/ui'

/** 网页版登录 / 邀请码注册。墨黑底 + 荧光绿，和侧栏一个气质。 */
export default function Login() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [f, setF] = useState({ username: '', password: '', code: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()
  const qc = useQueryClient()
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setErr(''); setBusy(true)
    try {
      await api(mode === 'login' ? '/auth/login' : '/auth/register', { body: f })
      qc.clear()
      nav('/', { replace: true })
    } catch (e: any) { setErr(String(e.message || e)) }
    setBusy(false)
  }
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value })
  return (
    <div className="min-h-full bg-ink flex items-center justify-center px-4">
      <div className="w-full max-w-[380px]">
        <img src="/logo-white.png" alt="观自行深" className="h-9 w-auto" />
        <div className="mt-3 flex items-center gap-2 text-[13px]">
          <span className="rounded bg-lime text-ink font-semibold px-1.5 py-0.5">监控台</span>
          <span className="text-white/45">抖音 · 小红书 · 视频号</span>
        </div>
        <form onSubmit={submit} className="mt-8 bg-white rounded-2xl p-6 space-y-3">
          <div className="flex gap-1 p-1 bg-paper rounded-lg text-sm">
            {(['login', 'register'] as const).map((m) => (
              <button key={m} type="button" onClick={() => { setMode(m); setErr('') }}
                className={`flex-1 h-8 rounded-md transition ${mode === m ? 'bg-ink text-lime font-medium' : 'text-mute'}`}>
                {m === 'login' ? '登录' : '用邀请码注册'}
              </button>
            ))}
          </div>
          {mode === 'register' && <Input placeholder="邀请码（GZ- 开头）" value={f.code} onChange={set('code')} className="w-full" autoFocus />}
          <Input placeholder="账号" value={f.username} onChange={set('username')} className="w-full" autoComplete="username" autoFocus={mode === 'login'} />
          <Input placeholder={mode === 'register' ? '密码（至少 8 位）' : '密码'} type="password" value={f.password} onChange={set('password')}
            className="w-full" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
          {err && <div className="text-[13px] text-red-600">{err}</div>}
          <Button variant="primary" type="submit" loading={busy} className="w-full h-10"
            disabled={!f.username || !f.password || (mode === 'register' && !f.code)}>
            {mode === 'login' ? '登录' : '注册并进入'}
          </Button>
          {mode === 'register' && <p className="text-xs text-mute leading-relaxed">账号可以用中文。每个账号的数据和 Key 互相看不到。</p>}
        </form>
        <p className="mt-4 text-center text-xs text-white/35">没有邀请码？找观自要一个</p>
      </div>
    </div>
  )
}
