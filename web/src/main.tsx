import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { JobProvider } from './components/jobs'
import Layout from './components/Layout'
import './index.css'
import Login from './pages/Login'

// 页面按需加载：图表（recharts）、Markdown 只在用到的页面才下载，首屏更快
const AuthorDetail = lazy(() => import('./pages/AuthorDetail'))
const Blogger = lazy(() => import('./pages/Blogger'))
const ContentDetail = lazy(() => import('./pages/ContentDetail'))
const Keyword = lazy(() => import('./pages/Keyword'))
const Library = lazy(() => import('./pages/Library'))
const Monitors = lazy(() => import('./pages/Monitors'))
const Overview = lazy(() => import('./pages/Overview'))
const Profile = lazy(() => import('./pages/Profile'))
const Settings = lazy(() => import('./pages/Settings'))
const Single = lazy(() => import('./pages/Single'))
const StyleReport = lazy(() => import('./pages/StyleReport'))
const Welcome = lazy(() => import('./pages/Welcome'))
const Jobs = lazy(() => import('./pages/Jobs').then((m) => ({ default: m.Jobs })))
const JobDetail = lazy(() => import('./pages/Jobs').then((m) => ({ default: m.JobDetail })))

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 2000, refetchOnWindowFocus: true } } })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <JobProvider>
          <Routes>
            <Route path="login" element={<Login />} />
            <Route element={<Layout />}>
              <Route index element={<Overview />} />
              <Route path="welcome" element={<Welcome />} />
              <Route path="single" element={<Single />} />
              <Route path="keyword" element={<Keyword />} />
              <Route path="blogger" element={<Blogger />} />
              <Route path="author/:id" element={<AuthorDetail />} />
              <Route path="content/:id" element={<ContentDetail />} />
              <Route path="style/:id" element={<StyleReport />} />
              <Route path="monitors" element={<Monitors />} />
              <Route path="library" element={<Library />} />
              <Route path="jobs" element={<Jobs />} />
              <Route path="jobs/:id" element={<JobDetail />} />
              <Route path="settings" element={<Settings />} />
              <Route path="profile" element={<Profile />} />
            </Route>
          </Routes>
        </JobProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
