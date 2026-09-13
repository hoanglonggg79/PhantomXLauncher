import { create } from 'zustand'

import { api, describeError } from '@/lib/api'
import type { SupporterStatus } from '@/lib/types'

export type SupporterTheme = 'default' | 'cyberpunk' | 'synthwave'

interface SupporterState {
  /** Trạng thái supporter hiện tại (null = chưa load) */
  status: SupporterStatus | null
  /** Đang gọi API */
  isLoading: boolean
  /** Lỗi verify cuối cùng */
  verifyError: string | null
  /** Theme đang chọn */
  selectedTheme: SupporterTheme

  // ── Derived (computed getters sẽ được expose ra ngoài) ───────────────────
  readonly isSupporter: boolean
  readonly discordId: string | null

  // ── Actions ──────────────────────────────────────────────────────────────
  /** Gọi GET /api/supporter/status — dùng khi app startup để restore badge */
  loadStatus: () => Promise<void>
  /** Verify token từ user input — POST /api/supporter/verify */
  verifyToken: (token: string) => Promise<boolean>
  /** Xóa badge khỏi config.json cục bộ (không cần internet) */
  revoke: () => Promise<void>
  /** Đổi theme và apply ngay vào document.documentElement */
  setTheme: (theme: SupporterTheme) => void
  /** Reset lỗi verify */
  clearVerifyError: () => void
}

function applyTheme(theme: SupporterTheme) {
  if (theme === 'default') {
    delete document.documentElement.dataset.theme
  } else {
    document.documentElement.dataset.theme = theme
  }
}

export const useSupporterStore = create<SupporterState>((set, get) => ({
  status: null,
  isLoading: false,
  verifyError: null,
  selectedTheme: 'default',

  // Derived: isSupporter
  get isSupporter() {
    return get().status?.active === true
  },

  // Derived: discordId
  get discordId() {
    return get().status?.discord_id ?? null
  },

  loadStatus: async () => {
    try {
      const status = await api.getSupporterStatus()
      const theme = (status.active && status.theme) ? status.theme : 'default'
      set({ status, selectedTheme: theme })
      applyTheme(theme)
    } catch {
      // Silent fail — không làm gián đoạn startup nếu supporter endpoint lỗi
      set({ status: { active: false }, selectedTheme: 'default' })
      applyTheme('default')
    }
  },

  verifyToken: async (token: string) => {
    set({ isLoading: true, verifyError: null })
    try {
      const result = await api.verifySupporter(token)
      if (result.valid) {
        // Refresh status từ config.json sau khi persist thành công
        const status = await api.getSupporterStatus()
        const theme = (status.active && status.theme) ? status.theme : 'default'
        set({ status, selectedTheme: theme, isLoading: false, verifyError: null })
        applyTheme(theme)
        return true
      } else {
        set({
          isLoading: false,
          verifyError: result.error ?? 'Token không hợp lệ',
        })
        return false
      }
    } catch (error) {
      const msg = describeError(error)
      set({ isLoading: false, verifyError: msg })
      return false
    }
  },

  revoke: async () => {
    set({ isLoading: true })
    try {
      await api.revokeSupporter()
    } catch {
      // Best-effort
    }
    set({
      status: { active: false },
      isLoading: false,
      selectedTheme: 'default',
    })
    applyTheme('default')
  },

  setTheme: (theme: SupporterTheme) => {
    set({ selectedTheme: theme })
    applyTheme(theme)
    api.setSupporterTheme(theme).catch((err) => {
      console.warn('Failed to persist supporter theme:', err)
    })
  },

  clearVerifyError: () => set({ verifyError: null }),
}))
