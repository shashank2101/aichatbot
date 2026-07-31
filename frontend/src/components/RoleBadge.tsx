const ROLE_COLORS: Record<string, string> = {
  admin: 'bg-purple-100 text-purple-700',
  manager: 'bg-blue-100 text-blue-700',
  auditor: 'bg-amber-100 text-amber-700',
  viewer: 'bg-slate-100 text-slate-600',
}

export function RoleBadge({ role }: { role: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${ROLE_COLORS[role] ?? ROLE_COLORS.viewer}`}>
      {role}
    </span>
  )
}
