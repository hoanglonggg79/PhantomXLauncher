import { create } from 'zustand'
import { AxiosError } from 'axios'

import { api, describeError } from '@/lib/api'
import type { ElybyProfile } from '@/lib/types'

interface ElybyAuthState {
  profile: ElybyProfile | null
  clientToken: string | null
  isLoading: boolean
  error: string | null
  is2FARequired: boolean
  loginDialogOpen: boolean

  loadProfile: () => Promise<void>
  login: (username: string, password: string, totp?: string) => Promise<boolean>
  logout: () => Promise<void>
  refresh: () => Promise<boolean>
  setLoginDialogOpen: (open: boolean) => void
  clearError: () => void
}

function is2FAError(error: unknown): boolean {
  if (!(error instanceof AxiosError)) return false
  const detail = error.response?.data?.detail
  if (typeof detail === 'object' && detail !== null && 'error' in detail) {
    return (detail as { error: string }).error === '2FA_REQUIRED'
  }
  return false
}

export const useElybyAuthStore = create<ElybyAuthState>((set, get) => ({
  profile: null,
  clientToken: null,
  isLoading: false,
  error: null,
  is2FARequired: false,
  loginDialogOpen: false,

  setLoginDialogOpen: (open) => set({ loginDialogOpen: open, error: open ? get().error : null }),
  clearError: () => set({ error: null }),

  loadProfile: async () => {
    try {
      const res = await api.elybyProfile()
      set({
        profile: res.profile,
        clientToken: res.logged_in ? get().clientToken : null,
        is2FARequired: false,
      })
    } catch {
      set({ profile: null, clientToken: null })
    }
  },

  login: async (username, password, totp) => {
    set({ isLoading: true, error: null })
    try {
      const res = await api.elybyLogin({
        username,
        password,
        totp_token: totp || undefined,
        clientToken: get().clientToken || undefined,
      })
      set({
        profile: res.profile,
        clientToken: res.client_token,
        isLoading: false,
        is2FARequired: false,
        loginDialogOpen: false,
        error: null,
      })
      return true
    } catch (error) {
      if (is2FAError(error)) {
        set({
          isLoading: false,
          is2FARequired: true,
          error: 'Vui lòng nhập mã xác thực 2 bước (6 chữ số).',
        })
        return false
      }
      set({
        isLoading: false,
        error: describeError(error),
      })
      return false
    }
  },

  logout: async () => {
    set({ isLoading: true, error: null })
    try {
      await api.elybyLogout()
    } catch {
      // Local session cleared on backend even if request fails mid-flight
    }
    set({
      profile: null,
      clientToken: null,
      isLoading: false,
      is2FARequired: false,
      loginDialogOpen: false,
    })
  },

  refresh: async () => {
    set({ isLoading: true, error: null })
    try {
      const res = await api.elybyRefresh()
      set({
        profile: res.profile,
        clientToken: res.client_token,
        isLoading: false,
        error: null,
      })
      return true
    } catch (error) {
      set({
        isLoading: false,
        profile: null,
        clientToken: null,
        error: describeError(error),
      })
      return false
    }
  },
}))

export function elybyAvatarUrl(username: string, size = 32): string {
  return `https://minotar.net/avatar/${encodeURIComponent(username)}/${size}`
}
