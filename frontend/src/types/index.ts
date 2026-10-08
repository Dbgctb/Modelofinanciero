export type UserRole = 'admin' | 'gestor' | 'lector'

export interface User {
  id: string
  username: string
  email: string
  full_name: string
  role: UserRole
  must_change_password: boolean
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
}
