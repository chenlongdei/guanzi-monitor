import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { JobProvider } from './components/jobs'
import Layout from './components/Layout'
import './index.css'
import AuthorDetail from './pages/AuthorDetail'
import Blogger from './pages/Blogger'
import ContentDetail from './pages/ContentDetail'
import { JobDetail, Jobs } from './pages/Jobs'
import Keyword from './pages/Keyword'
import Library from './pages/Library'
import Login from './pages/Login'
import Monitors from './pages/Monitors'
import Overview from './pages/Overview'
import Profile from './pages/Profile'
import Settings from './pages/Settings'
import Single from './pages/Single'
import StyleReport from './pages/StyleReport'
import Welcome from './pages/Welcome'

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
