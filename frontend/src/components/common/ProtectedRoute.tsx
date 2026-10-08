import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import type { UserRole } from '../../types'

interface Props {
  children: React.ReactNode
  allowedRoles?: UserRole[]
}

export default function ProtectedRoute({ children, allowedRoles }: Props) {
  const { isAuthenticated, user } = useAuthStore()

  if (!isAuthenticated()) return <Navigate to="/login" replace />

  if (allowedRoles && user && !allowedRoles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />
  }

  return <>{children}</>
}
