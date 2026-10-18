import { BrowserRouter, Routes, Route, Navigate, useLocation, useParams } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import LandingPage from './pages/LandingPage'
import AuthPage from './pages/AuthPage'
import TodayPage from './pages/TodayPage'
import StudyPage from './pages/StudyPage'
import NotFoundPage from './pages/NotFoundPage'
import ClassPage from './pages/ClassPage'
import CalendarPage from './pages/CalendarPage'
import CampusPage from './pages/CampusPage'
import MarketplacePage from './pages/MarketplacePage'
import OrdersPage from './pages/OrdersPage'
import SettingsPage from './pages/SettingsPage'
import MessagesPage from './pages/MessagesPage'
import OnboardingPage from './pages/OnboardingPage'
import AppShell from './components/AppShell'

function ClassRedirect() {
  const { id } = useParams()
  return <Navigate to={`/study/${id}`} replace />
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { loading, user } = useAuth()
  const location = useLocation()
  if (loading) return <main style={{ padding: '2rem' }}><p style={{ color: 'var(--muted)' }}>Loading…</p></main>
  if (!user) {
    try { sessionStorage.setItem('sos:return', location.pathname + location.search) } catch { /* storage unavailable */ }
    return <Navigate to="/auth?mode=signin" state={{ from: location }} replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/auth" element={<AuthPage />} />
                    <Route path="/agents" element={<Navigate to="/study" replace />} />
          <Route path="/class/:id" element={<ClassRedirect />} />
          <Route element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
            <Route path="/today" element={<TodayPage />} />
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route path="/study" element={<StudyPage />} />
            <Route path="/study/:id" element={<ClassPage />} />
            <Route path="/calendar" element={<CalendarPage />} />
            <Route path="/marketplace" element={<MarketplacePage />} />
            <Route path="/marketplace/:section" element={<MarketplacePage />} />
            <Route path="/orders" element={<OrdersPage />} />
            <Route path="/orders/:id" element={<OrdersPage />} />
            <Route path="/books" element={<Navigate to="/marketplace" replace />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/messages" element={<MessagesPage />} />
            <Route path="/tutoring" element={<Navigate to="/study" replace />} />
            <Route path="/campus" element={<CampusPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
