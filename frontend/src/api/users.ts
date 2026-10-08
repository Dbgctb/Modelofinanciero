import api from './client'

export type UserRole = 'admin' | 'gestor' | 'lector'

export interface AppUser {
  id: string
  email: string
  username: string
  full_name: string
  role: UserRole
  is_active: boolean
  last_login: string | null
  created_at: string
}

export interface UserCreateInput {
  email: string
  username: string
  full_name: string
  role: UserRole
  password: string
}

export interface UserUpdateInput {
  full_name?: string
  role?: UserRole
  is_active?: boolean
}

export interface AuditEntry {
  id: string
  username: string | null
  action: string
  resource: string | null
  resource_id: string | null
  detail: string | null
  ip_address: string | null
  created_at: string
}

export const usersApi = {
  listar: () =>
    api.get<AppUser[]>('/users/'),

  crear: (data: UserCreateInput) =>
    api.post<AppUser>('/users/', data),

  actualizar: (id: string, data: UserUpdateInput) =>
    api.patch<AppUser>(`/users/${id}`, data),

  desactivar: (id: string) =>
    api.delete(`/users/${id}`),

  resetPassword: (id: string, new_password: string) =>
    api.post(`/users/${id}/reset-password`, { new_password }),

  auditLog: (limit = 100, offset = 0) =>
    api.get<{ total: number; items: AuditEntry[] }>('/users/audit-log', {
      params: { limit, offset },
    }),
}
