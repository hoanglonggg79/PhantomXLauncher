import { create } from 'zustand'

import { api, describeError, initApiClient } from '@/lib/api'
import { getSidecarInfo, hideLauncher, showLauncher } from '@/lib/sidecar'
import { subscribeTask } from '@/lib/sse'
import { useElybyAuthStore } from '@/store/elyby-auth-store'
import { useSupporterStore } from '@/store/supporter-store'
import type {
  AppInfo,
  Instance,
  JavaInstall,
  JavaStatus,
  LoaderName,
  MarketplaceModItem,
  MarketplaceProjectDetail,
  MarketplaceSource,
  MarketplaceVersion,
  MinecraftVersion,
  Mod,
  Settings,
  SettingsPatch,
  SidecarInfo,
  UpdateCheckResponse,
  ModpackUploadResponse,
  ModpackInstallPayload,
  CrashAnalysisResult,
  CleanCacheResponse,
} from '@/lib/types'

export type Screen = 'instances' | 'marketplace' | 'settings' | 'about'
export type ConnectionState = 'connecting' | 'ready' | 'error'
export type TaskKind = 'install' | 'launch' | 'clone' | 'delete' | 'java_install' | 'mod_install' | 'modpack_install' | 'repair'

const MAX_LOG_LINES = 600
const POLL_INTERVAL_MS = 5000

export interface LogLine {
  id: number
  level: string
  message: string
  timestamp: string
}

export interface Task {
  id: string
  kind: TaskKind
  instanceName: string
  label: string
  current: number
  total: number
  running: boolean
  cancelling: boolean
  success: boolean | null
  logs: LogLine[]
}

export interface Notice {
  tone: 'error' | 'info' | 'success'
  message: string
}

interface AppState {
  connection: ConnectionState
  connectionError: string
  sidecar: SidecarInfo | null
  screen: Screen
  instances: Instance[]
  instancesLoading: boolean
  versions: MinecraftVersion[]
  latestRelease: string
  versionsLoading: boolean
  settings: Settings | null
  java: JavaStatus | null
  info: AppInfo | null
  tasks: Record<string, Task>
  focusedTaskId: string | null
  consoleOpen: boolean
  notice: Notice | null

  // ── Mod Manager ──────────────────────────────────────────────────────────
  modManagerOpen: boolean
  modManagerInstance: string | null
  mods: Mod[]
  modsLoading: boolean

  // ── Java Runtime Manager ─────────────────────────────────────────────────
  javaInstalls: JavaInstall[]
  javaInstallsLoading: boolean

  // ── Marketplace (Sprint 3A) ──────────────────────────────────────────────
  marketplaceSource: MarketplaceSource
  marketplaceSearchQuery: string
  marketplaceMcVersion: string
  marketplaceLoader: string
  marketplaceCategory: string
  marketplaceSort: string
  marketplaceHits: MarketplaceModItem[]
  marketplaceTotal: number
  marketplaceLoading: boolean
  marketplaceSelectedProject: MarketplaceProjectDetail | null
  marketplaceProjectLoading: boolean
  marketplaceVersions: MarketplaceVersion[]
  marketplaceVersionsLoading: boolean
  marketplaceDetailOpen: boolean

  // ── Bug Report Dialog (Sprint 3A) ────────────────────────────────────────
  bugReportOpen: boolean

  // ── Update Checker (Sprint 3A) ───────────────────────────────────────────
  updateAvailable: UpdateCheckResponse | null
  updateDismissed: boolean

  connect: () => Promise<void>
  setScreen: (screen: Screen) => void
  notify: (notice: Notice | null) => void
  refreshInstances: () => Promise<void>
  loadVersions: (includeSnapshots?: boolean) => Promise<void>
  loadLoaderVersions: (loader: LoaderName, mcVersion: string) => Promise<string[]>
  createInstance: (payload: {
    name: string
    version_id: string
    loader: LoaderName
    loader_version?: string
  }) => Promise<boolean>
  repairInstance: (name: string) => Promise<void>
  launchInstance: (name: string) => Promise<void>
  stopInstance: (name: string) => Promise<void>
  cloneInstance: (
    name: string,
    payload: {
      new_name: string
      copy_saves?: boolean
      copy_configs?: boolean
      copy_mods?: boolean
    }
  ) => Promise<boolean>
  deleteInstance: (name: string, deleteFiles: boolean) => Promise<boolean>
  updateInstance: (name: string, payload: { name?: string; notes?: string }) => Promise<boolean>
  openInstanceFolder: (name: string, subdir?: string) => Promise<boolean>
  cancelTask: (taskId: string) => Promise<void>
  saveSettings: (patch: SettingsPatch) => Promise<void>
  focusTask: (id: string | null) => void
  setConsoleOpen: (open: boolean) => void

  // ── Mod Manager actions ───────────────────────────────────────────────────
  openModManager: (instanceName: string) => void
  closeModManager: () => void
  loadMods: (instanceName: string) => Promise<void>
  toggleMod: (instanceName: string, filename: string, enabled: boolean) => Promise<boolean>
  deleteMod: (instanceName: string, filename: string) => Promise<boolean>
  uploadMod: (instanceName: string, file: File) => Promise<boolean>
  openModsFolder: (instanceName: string) => Promise<boolean>

  // ── Java Runtime Manager actions ─────────────────────────────────────────
  loadJavaInstalls: () => Promise<void>
  installJava: (major: number) => Promise<boolean>

  // ── Marketplace actions (Sprint 3A) ──────────────────────────────────────
  setMarketplaceSource: (source: MarketplaceSource) => void
  setMarketplaceFilters: (filters: Partial<{
    query: string
    mcVersion: string
    loader: string
    category: string
    sort: string
  }>) => void
  searchMarketplace: () => Promise<void>
  openMarketplaceDetail: (source: MarketplaceSource, projectId: string) => Promise<void>
  closeMarketplaceDetail: () => void
  loadMarketplaceVersions: (
    source: MarketplaceSource,
    projectId: string,
    mcVersion?: string,
    loader?: string
  ) => Promise<void>
  installMarketplaceMod: (payload: {
    instanceName: string
    source: MarketplaceSource
    projectId: string
    projectTitle: string
    fileId: string
    downloadUrl: string
    filename: string
  }) => Promise<boolean>

  // ── Modpack actions (Sprint 3B) ──────────────────────────────────────────
  modpackInstallOpen: boolean
  modpackUploadedFile: ModpackUploadResponse | null
  modpackUploading: boolean
  setModpackInstallOpen: (open: boolean) => void
  setModpackUploadedFile: (data: ModpackUploadResponse | null) => void
  uploadModpack: (file: File) => Promise<boolean>
  installModpack: (payload: ModpackInstallPayload) => Promise<boolean>

  // ── Bug Report actions (Sprint 3A) ───────────────────────────────────────
  setBugReportOpen: (open: boolean) => void

  // ── Update Checker actions (Sprint 3A) ───────────────────────────────────
  checkForUpdate: (silent?: boolean) => Promise<void>
  dismissUpdate: () => void

  // ── Startup & Progress (Sprint 4) ─────────────────────────────────────────
  startupStep: string
  startupProgress: number

  // ── Diagnostics & Repair (Sprint 4) ───────────────────────────────────────
  repairDialogOpen: boolean
  repairDialogInstance: string | null
  repairDialogTab: 'verify' | 'crash' | 'reset'
  openRepairDialog: (instanceName: string, tab?: 'verify' | 'crash' | 'reset') => void
  closeRepairDialog: () => void
  verifyInstanceIntegrity: (name: string) => Promise<boolean>
  analyzeInstanceCrash: (name: string) => Promise<CrashAnalysisResult | null>
  resetInstanceOptions: (name: string) => Promise<boolean>
  cleanSystemCache: () => Promise<CleanCacheResponse | null>

  // ── Background Music & Discord RPC (Sprint 4) ─────────────────────────────
  bgMusicMuted: boolean
  bgMusicVolume: number
  setBgMusicMuted: (muted: boolean) => void
  setBgMusicVolume: (volume: number) => void
  updateDiscordStatus: (
    status: 'idle' | 'marketplace' | 'in_game',
    instanceName?: string,
    loader?: string,
    mcVersion?: string
  ) => Promise<void>
}

const subscriptions = new Map<string, () => void>()
let logSeq = 0
let pollTimer: ReturnType<typeof setInterval> | null = null

export const useAppStore = create<AppState>((set, get) => {
  const patchTask = (id: string, patch: Partial<Task>) =>
    set((state) => {
      const task = state.tasks[id]
      if (!task) return state
      return { tasks: { ...state.tasks, [id]: { ...task, ...patch } } }
    })

  const appendLog = (id: string, level: string, message: string, timestamp: string) =>
    set((state) => {
      const task = state.tasks[id]
      if (!task) return state
      const logs = [...task.logs, { id: ++logSeq, level, message, timestamp }]
      return {
        tasks: {
          ...state.tasks,
          [id]: {
            ...task,
            logs: logs.length > MAX_LOG_LINES ? logs.slice(-MAX_LOG_LINES) : logs,
          },
        },
      }
    })

  const syncPolling = () => {
    const active = Object.values(get().tasks).some((t) => t.running)
    if (active && pollTimer === null) {
      pollTimer = setInterval(() => void get().refreshInstances(), POLL_INTERVAL_MS)
    } else if (!active && pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  const track = (taskId: string, kind: TaskKind, instanceName: string, label: string) => {
    set((state) => ({
      tasks: {
        ...state.tasks,
        [taskId]: {
          id: taskId,
          kind,
          instanceName,
          label,
          current: 0,
          total: 0,
          running: true,
          cancelling: false,
          success: null,
          logs: [],
        },
      },
      focusedTaskId: taskId,
      consoleOpen: true,
    }))
    const stop = subscribeTask(taskId, {
      onProgress: (event) => {
        patchTask(taskId, {
          current: event.current,
          total: event.total,
          label: event.label || label,
        })
        if (kind === 'launch' && event.current >= 3 && get().settings?.close_on_launch) {
          void hideLauncher()
        }
      },
      onLog: (event) => {
        appendLog(taskId, event.level, event.message, event.timestamp)
        if (
          kind === 'launch' &&
          event.message.includes('Game started') &&
          get().settings?.close_on_launch
        ) {
          void hideLauncher()
        }
      },
      onComplete: (event) => {
        subscriptions.delete(taskId)
        const cancelled = event.result?.cancelled === true
        patchTask(taskId, {
          running: false,
          cancelling: false,
          success: event.success,
          label: event.success ? 'Finished' : cancelled ? 'Cancelled' : 'Failed',
        })
        if (!event.success && !cancelled) {
          const detail = (event.result?.error as string) || 'Task failed'
          get().notify({ tone: 'error', message: detail })
        }

        // If launcher was hidden on launch, restore it when game exits
        if (kind === 'launch' && get().settings?.close_on_launch) {
          void showLauncher()
        }

        // When Java install finishes successfully, auto-refresh settings and Java status
        if (event.success && kind === 'java_install') {
          void get().loadJavaInstalls()
          void api.readSettings().then((settings) => set({ settings })).catch(() => undefined)
          void api.javaStatus().then((java) => set({ java })).catch(() => undefined)
          const major = event.result?.major
          get().notify({
            tone: 'success',
            message: `Java ${major ?? ''} installed and configured as active runtime!`,
          })
        }

        // When mod install finishes successfully
        if (event.success && kind === 'mod_install') {
          get().notify({
            tone: 'success',
            message: `Cài đặt mod thành công vào instance ${instanceName}!`,
          })
          void get().refreshInstances()
        }

        // When modpack install finishes successfully
        if (event.success && kind === 'modpack_install') {
          get().notify({
            tone: 'success',
            message: `Cài đặt Modpack thành công! Instance '${instanceName}' đã sẵn sàng khởi chạy.`,
          })
          void get().refreshInstances()
        }

        // When repair finishes
        if (event.success && kind === 'repair') {
          get().notify({
            tone: 'success',
            message: `Kiểm tra và sửa chữa toàn vẹn cho '${instanceName}' hoàn tất!`,
          })
          void get().refreshInstances()
        }

        // When launch exits with error / crash
        if (kind === 'launch' && event.result && typeof event.result.exit_code === 'number' && event.result.exit_code !== 0) {
          get().notify({
            tone: 'error',
            message: `Minecraft '${instanceName}' dừng với mã lỗi ${event.result.exit_code}. Mở Sửa chữa & Chẩn đoán để xem chi tiết.`,
          })
          get().openRepairDialog(instanceName, 'crash')
        }

        void get().refreshInstances()
        syncPolling()
      },
      onError: (message) => {
        subscriptions.delete(taskId)
        appendLog(taskId, 'error', message, new Date().toISOString())
        patchTask(taskId, {
          running: false,
          cancelling: false,
          success: false,
          label: 'Disconnected',
        })
        get().notify({ tone: 'error', message })
        if (kind === 'launch' && get().settings?.close_on_launch) {
          void showLauncher()
        }
        syncPolling()
      },
    })

    subscriptions.set(taskId, stop)
    syncPolling()
    setTimeout(() => void get().refreshInstances(), 1200)
  }

  return {
    connection: 'connecting',
    connectionError: '',
    sidecar: null,
    screen: 'instances',
    instances: [],
    instancesLoading: false,
    versions: [],
    latestRelease: '',
    versionsLoading: false,
    settings: null,
    java: null,
    info: null,
    tasks: {},
    focusedTaskId: null,
    consoleOpen: false,
    notice: null,

    // Mod manager
    modManagerOpen: false,
    modManagerInstance: null,
    mods: [],
    modsLoading: false,

    // Java runtime manager
    javaInstalls: [],
    javaInstallsLoading: false,

    // Marketplace (Sprint 3A)
    marketplaceSource: 'modrinth',
    marketplaceSearchQuery: '',
    marketplaceMcVersion: '',
    marketplaceLoader: '',
    marketplaceCategory: '',
    marketplaceSort: 'downloads',
    marketplaceHits: [],
    marketplaceTotal: 0,
    marketplaceLoading: false,
    marketplaceSelectedProject: null,
    marketplaceProjectLoading: false,
    marketplaceVersions: [],
    marketplaceVersionsLoading: false,
    marketplaceDetailOpen: false,

    // Bug Report Dialog (Sprint 3A)
    bugReportOpen: false,

    // Update Checker (Sprint 3A)
    updateAvailable: null,
    updateDismissed: false,

    // Sprint 4 States
    startupStep: 'Khởi tạo PhantomX Core & Sidecar Handshake...',
    startupProgress: 10,
    repairDialogOpen: false,
    repairDialogInstance: null,
    repairDialogTab: 'verify',
    bgMusicMuted: false,
    bgMusicVolume: 0.7,

    setScreen: (screen) => {
      set({ screen })
      const isGameRunning = Object.values(get().tasks).some((t) => t.kind === 'launch' && t.running)
      if (!isGameRunning) {
        if (screen === 'marketplace') {
          void get().updateDiscordStatus('marketplace')
        } else {
          void get().updateDiscordStatus('idle')
        }
      }
    },
    notify: (notice) => set({ notice }),
    focusTask: (focusedTaskId) => set({ focusedTaskId }),
    setConsoleOpen: (consoleOpen) => set({ consoleOpen }),

    connect: async () => {
      set({
        connection: 'connecting',
        connectionError: '',
        startupStep: 'Khởi tạo PhantomX Core & Sidecar Handshake...',
        startupProgress: 20,
      })
      try {
        const info = await getSidecarInfo()
        initApiClient(info)
        await api.health()

        set({
          sidecar: info,
          startupStep: 'Nạp cấu hình và các Instances...',
          startupProgress: 50,
        })

        const [instances, settings] = await Promise.all([
          api.listInstances(),
          api.readSettings(),
        ])

        const isMuted = settings.bg_music_enabled === false
        const vol = typeof settings.bg_music_volume === 'number' ? settings.bg_music_volume : 0.7

        set({
          instances,
          settings,
          bgMusicMuted: isMuted,
          bgMusicVolume: vol,
          startupStep: 'Khôi phục tài khoản Ely.by & huy hiệu Supporter...',
          startupProgress: 75,
        })

        void api
          .appInfo()
          .then((appInfo) => set({ info: appInfo }))
          .catch(() => undefined)
        void api
          .javaStatus()
          .then((java) => set({ java }))
          .catch(() => undefined)

        // Restore Ely.by session if previously logged in (fire-and-forget, non-blocking)
        void useElybyAuthStore.getState().loadProfile()

        // Restore Supporter badge from config.json (fire-and-forget, non-blocking)
        void useSupporterStore.getState().loadStatus()

        set({
          startupStep: 'Chuẩn bị nhạc nền PhantomX Theme...',
          startupProgress: 90,
        })
        void api.prepareThemeAudio().catch(() => undefined)

        // Automatic update check upon launch
        void get().checkForUpdate(true)

        // Initial Discord RPC
        void get().updateDiscordStatus('idle')

        set({
          startupStep: 'Sẵn sàng!',
          startupProgress: 100,
        })

        // Slight micro-yield so user sees the 100% completion before smooth fade-out
        await new Promise((r) => setTimeout(r, 120))
        set({ connection: 'ready' })
      } catch (error) {
        set({ connection: 'error', connectionError: describeError(error) })
      }
    },

    refreshInstances: async () => {
      set({ instancesLoading: true })
      try {
        set({ instances: await api.listInstances() })
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
      } finally {
        set({ instancesLoading: false })
      }
    },

    loadVersions: async (includeSnapshots?: boolean) => {
      const withSnapshots = includeSnapshots ?? Boolean(get().settings?.snapshots)
      if (get().versionsLoading) return
      set({ versionsLoading: true })
      try {
        const data = await api.listVersions(withSnapshots)
        set({ versions: data.versions, latestRelease: data.latest_release })
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
      } finally {
        set({ versionsLoading: false })
      }
    },

    loadLoaderVersions: async (loader, mcVersion) => {
      try {
        const data = await api.listLoaderVersions(loader, mcVersion)
        return data.supported ? data.versions : []
      } catch {
        return []
      }
    },

    createInstance: async (payload) => {
      try {
        const handle = await api.createInstance(payload)
        track(handle.task_id, 'install', handle.instance.name, 'Preparing install')
        set((state) => ({ instances: [...state.instances, handle.instance] }))
        return true
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
        return false
      }
    },

    repairInstance: async (name) => {
      try {
        const handle = await api.installInstance(name)
        track(handle.task_id, 'install', name, 'Repairing install')
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
      }
    },

    launchInstance: async (name) => {
      try {
        const handle = await api.launchInstance(name)
        track(handle.task_id, 'launch', name, 'Starting game')
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
      }
    },

    stopInstance: async (name) => {
      try {
        await api.stopInstance(name)
        set({ notice: { tone: 'info', message: `Stopped ${name}` } })
        await get().refreshInstances()
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
      }
    },

    cloneInstance: async (name, payload) => {
      try {
        const handle = await api.cloneInstance(name, payload)
        track(handle.task_id, 'clone', handle.name, `Cloning ${name} → ${handle.name}`)
        return true
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
        return false
      }
    },

    deleteInstance: async (name, deleteFiles) => {
      try {
        const res = await api.deleteInstance(name, deleteFiles)
        if (res.task_id) {
          track(res.task_id, 'delete', name, `Deleting files for ${name}`)
        } else {
          set({
            instances: get().instances.filter((i) => i.name !== name),
            notice: { tone: 'info', message: `Removed ${name} from list` },
          })
        }
        return true
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
        return false
      }
    },

    updateInstance: async (name, payload) => {
      try {
        const res = await api.updateInstance(name, payload)
        set({
          notice: { tone: 'success', message: `Updated ${res.instance.name}` },
        })
        await get().refreshInstances()
        return true
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
        return false
      }
    },

    openInstanceFolder: async (name, subdir) => {
      try {
        await api.openInstanceFolder(name, subdir)
        return true
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
        return false
      }
    },

    /**
     * Ask the sidecar to cancel a running task (GLOBAL RULE 1).
     *
     * Cancellation is cooperative: the worker only stops at its next
     * `check_cancelled()`, so we mark the task `cancelling` and let the SSE
     * `complete` frame flip `running` to false. Never clear `running` here —
     * doing so would re-enable Play while the worker is still touching files.
     */
    cancelTask: async (taskId) => {
      const task = get().tasks[taskId]
      if (!task || !task.running || task.cancelling) return
      patchTask(taskId, { cancelling: true, label: 'Cancelling…' })
      appendLog(taskId, 'warning', 'Cancellation requested', new Date().toISOString())
      try {
        await api.cancelTask(taskId)
      } catch (error) {
        const message = describeError(error)
        patchTask(taskId, { cancelling: false, label: task.label })
        appendLog(taskId, 'error', `Cancel failed: ${message}`, new Date().toISOString())
        set({ notice: { tone: 'error', message } })
      }
    },

    saveSettings: async (patch) => {
      try {
        const settings = await api.writeSettings(patch)
        set({ settings, notice: { tone: 'success', message: 'Settings saved' } })
        if (patch.java_path !== undefined) {
          void api
            .javaStatus()
            .then((java) => set({ java }))
            .catch(() => undefined)
        }
        if (patch.snapshots !== undefined) {
          void get().loadVersions(Boolean(patch.snapshots))
        }
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
      }
    },

    // ── Mod Manager ────────────────────────────────────────────────────────

    openModManager: (instanceName) => {
      set({ modManagerOpen: true, modManagerInstance: instanceName, mods: [] })
      void get().loadMods(instanceName)
    },

    closeModManager: () =>
      set({ modManagerOpen: false, modManagerInstance: null, mods: [] }),

    loadMods: async (instanceName) => {
      set({ modsLoading: true })
      try {
        const mods = await api.listMods(instanceName)
        set({ mods })
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
      } finally {
        set({ modsLoading: false })
      }
    },

    toggleMod: async (instanceName, filename, enabled) => {
      try {
        await api.toggleMod(instanceName, { filename, enabled })
        await get().loadMods(instanceName)
        // Refresh instance list to update mod_count badge
        void get().refreshInstances()
        return true
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
        return false
      }
    },

    deleteMod: async (instanceName, filename) => {
      try {
        await api.deleteMod(instanceName, filename)
        await get().loadMods(instanceName)
        void get().refreshInstances()
        return true
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
        return false
      }
    },

    uploadMod: async (instanceName, file) => {
      try {
        await api.uploadMod(instanceName, file)
        await get().loadMods(instanceName)
        void get().refreshInstances()
        return true
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
        return false
      }
    },

    openModsFolder: async (instanceName) => {
      try {
        await api.openModsFolder(instanceName)
        return true
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
        return false
      }
    },

    // ── Java Runtime Manager ───────────────────────────────────────────────

    loadJavaInstalls: async () => {
      set({ javaInstallsLoading: true })
      try {
        const installs = await api.listJavaInstalls()
        set({ javaInstalls: installs })
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
      } finally {
        set({ javaInstallsLoading: false })
      }
    },

    installJava: async (major) => {
      try {
        const handle = await api.installJava(major)
        track(handle.task_id, 'java_install', `Java ${major}`, `Downloading Java ${major}…`)
        return true
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
        return false
      }
    },

    // ── Marketplace Actions (Sprint 3A) ────────────────────────────────────

    setMarketplaceSource: (source) => {
      set({ marketplaceSource: source, marketplaceHits: [], marketplaceTotal: 0 })
      void get().searchMarketplace()
    },

    setMarketplaceFilters: (filters) => {
      set((state) => ({
        marketplaceSearchQuery:
          filters.query !== undefined ? filters.query : state.marketplaceSearchQuery,
        marketplaceMcVersion:
          filters.mcVersion !== undefined ? filters.mcVersion : state.marketplaceMcVersion,
        marketplaceLoader:
          filters.loader !== undefined ? filters.loader : state.marketplaceLoader,
        marketplaceCategory:
          filters.category !== undefined ? filters.category : state.marketplaceCategory,
        marketplaceSort:
          filters.sort !== undefined ? filters.sort : state.marketplaceSort,
      }))
    },

    searchMarketplace: async () => {
      const state = get()
      set({ marketplaceLoading: true })
      try {
        const res = await api.marketplaceSearch({
          q: state.marketplaceSearchQuery,
          source: state.marketplaceSource,
          mc_version: state.marketplaceMcVersion,
          loader: state.marketplaceLoader,
          category: state.marketplaceCategory,
          sort: state.marketplaceSort,
          page: 1,
          page_size: 24,
        })
        set({
          marketplaceHits: res.hits,
          marketplaceTotal: res.total,
        })
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
      } finally {
        set({ marketplaceLoading: false })
      }
    },

    openMarketplaceDetail: async (source, projectId) => {
      set({
        marketplaceDetailOpen: true,
        marketplaceSelectedProject: null,
        marketplaceProjectLoading: true,
        marketplaceVersions: [],
        marketplaceVersionsLoading: true,
      })
      try {
        const project = await api.marketplaceProject(source, projectId)
        set({ marketplaceSelectedProject: project, marketplaceProjectLoading: false })

        // Auto-fetch versions using current filter if any
        const { marketplaceMcVersion, marketplaceLoader } = get()
        void get().loadMarketplaceVersions(source, projectId, marketplaceMcVersion, marketplaceLoader)
      } catch (error) {
        set({
          marketplaceProjectLoading: false,
          marketplaceVersionsLoading: false,
          notice: { tone: 'error', message: describeError(error) }
        })
      }
    },

    closeMarketplaceDetail: () => {
      set({
        marketplaceDetailOpen: false,
        marketplaceSelectedProject: null,
        marketplaceVersions: [],
      })
    },

    loadMarketplaceVersions: async (source, projectId, mcVersion = '', loader = '') => {
      set({ marketplaceVersionsLoading: true })
      try {
        const versions = await api.marketplaceVersions(source, projectId, {
          mc_version: mcVersion,
          loader,
        })
        set({ marketplaceVersions: versions })
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
      } finally {
        set({ marketplaceVersionsLoading: false })
      }
    },

    installMarketplaceMod: async (payload) => {
      // Instance State Guard: check if game is currently running
      const instance = get().instances.find((i) => i.name === payload.instanceName)
      if (instance?.running) {
        get().notify({
          tone: 'error',
          message: `Instance '${payload.instanceName}' đang chạy game. Vui lòng tắt Minecraft trước khi cài đặt mod!`,
        })
        return false
      }

      try {
        const handle = await api.marketplaceInstall({
          instance_name: payload.instanceName,
          source: payload.source,
          project_id: payload.projectId,
          project_title: payload.projectTitle,
          file_id: payload.fileId,
          download_url: payload.downloadUrl,
          filename: payload.filename,
        })
        track(
          handle.task_id,
          'mod_install',
          payload.instanceName,
          `Installing ${payload.projectTitle || payload.filename}…`
        )
        return true
      } catch (error) {
        set({ notice: { tone: 'error', message: describeError(error) } })
        return false
      }
    },

    // ── Bug Report Actions (Sprint 3A) ─────────────────────────────────────

    setBugReportOpen: (open) => set({ bugReportOpen: open }),

    // ── Update Checker Actions (Sprint 3A) ─────────────────────────────────

    checkForUpdate: async (silent = false) => {
      try {
        const res = await api.checkUpdate()
        if (res.has_update) {
          set({ updateAvailable: res })
        } else if (!silent) {
          get().notify({
            tone: 'info',
            message: `Bạn đang dùng phiên bản mới nhất (v${res.current_version}).`,
          })
        }
      } catch (error) {
        if (!silent) {
          set({ notice: { tone: 'error', message: describeError(error) } })
        }
      }
    },

    dismissUpdate: () => set({ updateDismissed: true, updateAvailable: null }),

    // ── Modpack Actions (Sprint 3B) ────────────────────────────────────────
    modpackInstallOpen: false,
    modpackUploadedFile: null,
    modpackUploading: false,
    setModpackInstallOpen: (open) => set({ modpackInstallOpen: open }),
    setModpackUploadedFile: (data) => set({ modpackUploadedFile: data }),
    uploadModpack: async (file: File) => {
      set({ modpackUploading: true })
      try {
        const res = await api.modpackUpload(file)
        set({ modpackUploadedFile: res, modpackUploading: false })
        return true
      } catch (error) {
        set({ modpackUploading: false })
        get().notify({ tone: 'error', message: describeError(error) })
        return false
      }
    },
    installModpack: async (payload: ModpackInstallPayload) => {
      try {
        const handle = await api.modpackInstall(payload)
        track(
          handle.task_id,
          'modpack_install',
          payload.name,
          `Đang cài đặt modpack ${payload.name}…`
        )
        set({ modpackInstallOpen: false, modpackUploadedFile: null })
        return true
      } catch (error) {
        get().notify({ tone: 'error', message: describeError(error) })
        return false
      }
    },

    // ── Diagnostics & Repair Actions (Sprint 4) ────────────────────────────
    openRepairDialog: (instanceName, tab = 'verify') =>
      set({
        repairDialogOpen: true,
        repairDialogInstance: instanceName,
        repairDialogTab: tab,
      }),

    closeRepairDialog: () =>
      set({
        repairDialogOpen: false,
      }),

    verifyInstanceIntegrity: async (name) => {
      try {
        const handle = await api.verifyIntegrity(name)
        track(handle.task_id, 'repair', name, 'Kiểm tra & Sửa chữa toàn vẹn')
        get().notify({
          tone: 'info',
          message: `Đã bắt đầu kiểm tra toàn vẹn cho '${name}'. Theo dõi tiến trình trong Console!`,
        })
        return true
      } catch (error) {
        get().notify({ tone: 'error', message: describeError(error) })
        return false
      }
    },

    analyzeInstanceCrash: async (name) => {
      try {
        return await api.analyzeCrash(name)
      } catch (error) {
        get().notify({ tone: 'error', message: describeError(error) })
        return null
      }
    },

    resetInstanceOptions: async (name) => {
      try {
        const res = await api.resetOptions(name)
        get().notify({
          tone: 'success',
          message: res.message || 'Đã đặt lại options.txt thành công!',
        })
        return true
      } catch (error) {
        get().notify({ tone: 'error', message: describeError(error) })
        return false
      }
    },

    cleanSystemCache: async () => {
      try {
        const res = await api.cleanCache()
        get().notify({
          tone: 'success',
          message: res.message,
        })
        return res
      } catch (error) {
        get().notify({ tone: 'error', message: describeError(error) })
        return null
      }
    },

    // ── Background Music & Discord RPC Actions (Sprint 4) ──────────────────
    setBgMusicMuted: (muted) => {
      set({ bgMusicMuted: muted })
      void api.writeSettings({ bg_music_enabled: !muted }).catch(() => undefined)
    },

    setBgMusicVolume: (volume) => {
      set({ bgMusicVolume: volume })
      void api.writeSettings({ bg_music_volume: volume }).catch(() => undefined)
    },

    updateDiscordStatus: async (status, instanceName, loader, mcVersion) => {
      const isSupporter = useSupporterStore.getState().isSupporter
      void api.updateDiscordRpc({
        status,
        instance_name: instanceName,
        loader,
        mc_version: mcVersion,
        is_supporter: isSupporter,
      }).catch(() => undefined)
    },
  }
})

