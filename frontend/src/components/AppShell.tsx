import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  MessageSquare,
  LayoutDashboard,
  Bell,
  FileText,
  Activity,
  LogOut,
  Package,
  ChevronLeft,
  ChevronRight,
  UploadCloud,
} from 'lucide-react'
import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { RoleBadge } from './RoleBadge'

// `roles` omitted = visible to every logged-in role. Present = only those roles see it.
const NAV: { to: string; label: string; icon: typeof MessageSquare; roles?: string[] }[] = [
  { to: '/app/chat', label: 'Chat', icon: MessageSquare },
  { to: '/app/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/app/alerts', label: 'Alerts', icon: Bell },
  { to: '/app/audit-reports', label: 'Audit Reports', icon: FileText },
  { to: '/app/data-upload', label: 'Data Upload', icon: UploadCloud, roles: ['admin', 'manager'] },
  { to: '/app/observability', label: 'Observability', icon: Activity, roles: ['admin'] },
]

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-slate-50">
      <aside
        className={`flex flex-col border-r border-slate-200 bg-white transition-all duration-200 ${
          collapsed ? 'w-16' : 'w-60'
        }`}
      >
        <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-4">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white">
            <Package className="h-5 w-5" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-900">Inventory Audit</p>
              <p className="truncate text-xs text-slate-500">Assistant</p>
            </div>
          )}
        </div>

        <nav className="flex-1 space-y-1 p-2">
          {NAV.filter((item) => !item.roles || (user && item.roles.includes(user.role))).map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                  isActive
                    ? 'bg-indigo-50 text-indigo-700'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`
              }
            >
              <Icon className="h-5 w-5 shrink-0" />
              {!collapsed && label}
            </NavLink>
          ))}
        </nav>

        <button
          onClick={() => setCollapsed(!collapsed)}
          className="mx-2 mb-2 flex items-center justify-center rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
          <div />
          <div className="flex items-center gap-3">
            <div className="text-right">
              <p className="text-sm font-medium text-slate-900">{user?.full_name}</p>
              <div className="flex items-center justify-end gap-2">
                <RoleBadge role={user?.role ?? 'viewer'} />
                {user?.region && (
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{user.region}</span>
                )}
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
              title="Logout"
            >
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
