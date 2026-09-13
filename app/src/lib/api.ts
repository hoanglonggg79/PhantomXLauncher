import axios, { AxiosError, type AxiosInstance } from 'axios'
import type {
  AppInfo,
  ChangelogResponse,
  CloneInstancePayload,
  CloneInstanceResponse,
  DeleteInstanceResponse,
  DeleteModResponse,
  Instance,
  JavaInstall,
  JavaInstallTaskResponse,
  JavaListResponse,
  JavaStatus,
  ListModsResponse,
  LoaderName,
  LoaderVersionsResponse,
  Mod,
  OpenFolderResponse,
  OpenModsFolderResponse,
  Settings,
  SettingsPatch,
  SidecarInfo,
  SupporterStatus,
  SupporterVerifyResponse,
  TaskHandle,
  ToggleModPayload,
  ToggleModResponse,
  UpdateInstancePayload,
  UpdateInstanceResponse,
  UploadModResponse,
  VersionsResponse,
  BugReportPayload,
  BugReportResponse,
  DiagnosticsContext,
  InstallMarketplaceModPayload,
  InstallMarketplaceModResponse,
  MarketplaceProjectDetail,
  MarketplaceSearchResponse,
  MarketplaceSource,
  MarketplaceVersion,
  UpdateCheckResponse,
  ElybyLoginResponse,
  ElybyProfileResponse,
  AuthMode,
  ModpackUploadResponse,
  ModpackInstallPayload,
  ModpackInstallResponse,
  RepairTaskResponse,
  CrashAnalysisResult,
  ResetOptionsResponse,
  CleanCacheResponse,
  DiscordRpcUpdatePayload,
  ThemeStatusResponse,
} from './types'

const TOKEN_HEADER = 'X-PhantomX-Token'

let client: AxiosInstance | null = null
let session: SidecarInfo | null = null

export function initApiClient(info: SidecarInfo): AxiosInstance {
  session = info
  client = axios.create({
    baseURL: `http://127.0.0.1:${info.port}`,
    timeout: 30000,
    headers: { 'Content-Type': 'application/json' },
  })

  client.interceptors.request.use((config) => {
    config.headers[TOKEN_HEADER] = info.token
    return config
  })

  return client
}

export function getApiClient(): AxiosInstance {
  if (!client) throw new Error('API client not initialized. Call initApiClient first.')
  return client
}

export function getSession(): SidecarInfo {
  if (!session) throw new Error('Sidecar session unavailable.')
  return session
}

export function describeError(error: unknown): string {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'object' && detail !== null && 'message' in detail) {
      return String((detail as { message: string }).message)
    }
    if (typeof detail === 'string') return detail
    if (error.code === 'ECONNABORTED') return 'Request timed out'
    return error.message
  }
  return error instanceof Error ? error.message : String(error)
}

export const api = {
  async health(): Promise<Record<string, unknown>> {
    const { data } = await getApiClient().get('/health')
    return data
  },

  async listInstances(): Promise<Instance[]> {
    const { data } = await getApiClient().get<{ instances: Instance[]; count: number }>(
      '/api/instances'
    )
    return data.instances
  },

  async getInstance(name: string): Promise<Instance> {
    const { data } = await getApiClient().get<{ instance: Instance }>(
      `/api/instances/${encodeURIComponent(name)}`
    )
    return data.instance
  },

  async createInstance(payload: {
    name: string
    version_id: string
    loader: LoaderName
    loader_version?: string
  }): Promise<TaskHandle> {
    const { data } = await getApiClient().post<TaskHandle>('/api/instances/create', {
      loader_version: '',
      ...payload,
    })
    return data
  },

  async installInstance(name: string): Promise<TaskHandle> {
    const { data } = await getApiClient().post<TaskHandle>(
      `/api/instances/${encodeURIComponent(name)}/install`
    )
    return data
  },

  async launchInstance(
    name: string,
    body: { username?: string; ram?: number } = {}
  ): Promise<TaskHandle> {
    const { data } = await getApiClient().post<TaskHandle>(
      `/api/instances/${encodeURIComponent(name)}/launch`,
      body
    )
    return data
  },

  async stopInstance(name: string): Promise<{ name: string; stopped: boolean }> {
    const { data } = await getApiClient().post(
      `/api/instances/${encodeURIComponent(name)}/stop`
    )
    return data
  },

  async deleteInstance(
    name: string,
    deleteFiles = false
  ): Promise<DeleteInstanceResponse> {
    const { data } = await getApiClient().delete<DeleteInstanceResponse>(
      `/api/instances/${encodeURIComponent(name)}`,
      { params: { delete_files: deleteFiles } }
    )
    return data
  },

  async cloneInstance(
    name: string,
    payload: CloneInstancePayload
  ): Promise<CloneInstanceResponse> {
    const { data } = await getApiClient().post<CloneInstanceResponse>(
      `/api/instances/${encodeURIComponent(name)}/clone`,
      payload
    )
    return data
  },

  async updateInstance(
    name: string,
    payload: UpdateInstancePayload
  ): Promise<UpdateInstanceResponse> {
    const { data } = await getApiClient().patch<UpdateInstanceResponse>(
      `/api/instances/${encodeURIComponent(name)}`,
      payload
    )
    return data
  },

  async openInstanceFolder(
    name: string,
    subdir = ''
  ): Promise<OpenFolderResponse> {
    const { data } = await getApiClient().post<OpenFolderResponse>(
      `/api/instances/${encodeURIComponent(name)}/open-folder`,
      { subdir }
    )
    return data
  },

  /** Flag a running task as cancelled; the SSE stream still ends with `complete`. */
  async cancelTask(taskId: string): Promise<{ task_id: string; cancelled: boolean }> {
    const { data } = await getApiClient().delete(
      `/api/tasks/${encodeURIComponent(taskId)}/cancel`
    )
    return data
  },

  async listVersions(includeSnapshots = false): Promise<VersionsResponse> {
    const { data } = await getApiClient().get<VersionsResponse>('/api/minecraft/versions', {
      params: { include_snapshots: includeSnapshots },
    })
    return data
  },

  async listLoaderVersions(
    loader: LoaderName,
    mcVersion: string
  ): Promise<LoaderVersionsResponse> {
    const { data } = await getApiClient().get<LoaderVersionsResponse>(
      `/api/minecraft/loaders/${loader}/${encodeURIComponent(mcVersion)}`
    )
    return data
  },

  async javaStatus(): Promise<JavaStatus> {
    const { data } = await getApiClient().get<JavaStatus>('/api/minecraft/java')
    return data
  },

  async readSettings(): Promise<Settings> {
    const { data } = await getApiClient().get<Settings>('/api/settings')
    return data
  },

  async writeSettings(patch: SettingsPatch): Promise<Settings> {
    const { data } = await getApiClient().put<Settings>('/api/settings', patch)
    return data
  },

  async appInfo(): Promise<AppInfo> {
    const { data } = await getApiClient().get<AppInfo>('/api/settings/info')
    return data
  },

  // ── Mod Management ────────────────────────────────────────────────────────

  async listMods(name: string): Promise<Mod[]> {
    const { data } = await getApiClient().get<ListModsResponse>(
      `/api/instances/${encodeURIComponent(name)}/mods`
    )
    return data.mods
  },

  async toggleMod(
    name: string,
    payload: ToggleModPayload
  ): Promise<ToggleModResponse> {
    const { data } = await getApiClient().post<ToggleModResponse>(
      `/api/instances/${encodeURIComponent(name)}/mods/toggle`,
      payload
    )
    return data
  },

  async deleteMod(name: string, filename: string): Promise<DeleteModResponse> {
    const { data } = await getApiClient().delete<DeleteModResponse>(
      `/api/instances/${encodeURIComponent(name)}/mods/${encodeURIComponent(filename)}`
    )
    return data
  },

  async openModsFolder(name: string): Promise<OpenModsFolderResponse> {
    const { data } = await getApiClient().post<OpenModsFolderResponse>(
      `/api/instances/${encodeURIComponent(name)}/mods/open-folder`
    )
    return data
  },

  async uploadMod(name: string, file: File): Promise<UploadModResponse> {
    const form = new FormData()
    form.append('file', file, file.name)
    const { data } = await getApiClient().post<UploadModResponse>(
      `/api/instances/${encodeURIComponent(name)}/mods/upload`,
      form,
      // Let the browser set Content-Type with the correct multipart boundary
      { headers: { 'Content-Type': undefined } }
    )
    return data
  },

  // ── Java Runtime Management ───────────────────────────────────────────────

  async listJavaInstalls(): Promise<JavaInstall[]> {
    const { data } = await getApiClient().get<JavaListResponse>('/api/system/java/list')
    return data.installs
  },

  async installJava(major: number): Promise<JavaInstallTaskResponse> {
    const { data } = await getApiClient().post<JavaInstallTaskResponse>(
      '/api/system/java/install',
      { major }
    )
    return data
  },

  // ── Changelog & Releases ──────────────────────────────────────────────────

  async getChangelog(forceRefresh = false): Promise<ChangelogResponse> {
    const { data } = await getApiClient().get<ChangelogResponse>('/api/settings/changelog', {
      params: { refresh: forceRefresh },
    })
    return data
  },

  // ── Marketplace (Sprint 3A) ───────────────────────────────────────────────

  async marketplaceSearch(params: {
    q?: string
    source?: MarketplaceSource
    mc_version?: string
    loader?: string
    category?: string
    sort?: string
    page?: number
    page_size?: number
  }): Promise<MarketplaceSearchResponse> {
    const { data } = await getApiClient().get<MarketplaceSearchResponse>(
      '/api/marketplace/search',
      { params }
    )
    return data
  },

  async marketplaceProject(
    source: MarketplaceSource,
    projectId: string
  ): Promise<MarketplaceProjectDetail> {
    const { data } = await getApiClient().get<MarketplaceProjectDetail>(
      `/api/marketplace/project/${source}/${encodeURIComponent(projectId)}`
    )
    return data
  },

  async marketplaceVersions(
    source: MarketplaceSource,
    projectId: string,
    params?: { mc_version?: string; loader?: string }
  ): Promise<MarketplaceVersion[]> {
    const { data } = await getApiClient().get<MarketplaceVersion[]>(
      `/api/marketplace/versions/${source}/${encodeURIComponent(projectId)}`,
      { params }
    )
    return data
  },

  async marketplaceInstall(
    payload: InstallMarketplaceModPayload
  ): Promise<InstallMarketplaceModResponse> {
    const { data } = await getApiClient().post<InstallMarketplaceModResponse>(
      '/api/marketplace/install',
      payload
    )
    return data
  },

  // ── System Diagnostics & GDPR Bug Report (Sprint 3A) ──────────────────────

  async getDiagnostics(): Promise<DiagnosticsContext> {
    const { data } = await getApiClient().get<DiagnosticsContext>('/api/system/diagnostics')
    return data
  },

  async reportBug(payload: BugReportPayload): Promise<BugReportResponse> {
    const { data } = await getApiClient().post<BugReportResponse>(
      '/api/system/report-bug',
      payload
    )
    return data
  },

  // ── Update Checker (Sprint 3A) ─────────────────────────────────────────────

  async checkUpdate(): Promise<UpdateCheckResponse> {
    const { data } = await getApiClient().get<UpdateCheckResponse>('/api/settings/check-update')
    return data
  },

  // ── Ely.by Authentication ────────────────────────────────────────────────

  async elybyLogin(payload: {
    username: string
    password: string
    totp_token?: string
    clientToken?: string
  }): Promise<ElybyLoginResponse> {
    const { data } = await getApiClient().post<ElybyLoginResponse>(
      '/api/auth/elyby/login',
      {
        clientToken: crypto.randomUUID(),
        ...payload,
      }
    )
    return data
  },

  async elybyRefresh(): Promise<ElybyLoginResponse> {
    const { data } = await getApiClient().post<ElybyLoginResponse>('/api/auth/elyby/refresh', {})
    return data
  },

  async elybyProfile(): Promise<ElybyProfileResponse> {
    const { data } = await getApiClient().get<ElybyProfileResponse>('/api/auth/elyby/profile')
    return data
  },

  async elybyLogout(): Promise<void> {
    await getApiClient().post('/api/auth/elyby/logout')
  },

  async setAuthMode(mode: AuthMode): Promise<Settings> {
    const { data } = await getApiClient().put<Settings>('/api/settings', { auth_mode: mode })
    return data
  },

  // ── Supporter Badge System (Sprint 3A++) ────────────────────────────────

  async verifySupporter(token: string): Promise<SupporterVerifyResponse> {
    const { data } = await getApiClient().post<SupporterVerifyResponse>(
      '/api/supporter/verify',
      { token }
    )
    return data
  },

  async getSupporterStatus(): Promise<SupporterStatus> {
    const { data } = await getApiClient().get<SupporterStatus>('/api/supporter/status')
    return data
  },

  async revokeSupporter(): Promise<{ active: boolean; revoked: boolean }> {
    const { data } = await getApiClient().delete('/api/supporter/revoke')
    return data
  },

  async setSupporterTheme(theme: string): Promise<{ ok: boolean; theme: string }> {
    const { data } = await getApiClient().put<{ ok: boolean; theme: string }>(
      '/api/supporter/theme',
      { theme }
    )
    return data
  },

  // ── Modpack System (Sprint 3B) ─────────────────────────────────────────────

  async modpackUpload(file: File): Promise<ModpackUploadResponse> {
    const formData = new FormData()
    formData.append('file', file)
    const { data } = await getApiClient().post<ModpackUploadResponse>(
      '/api/marketplace/modpack/upload',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return data
  },

  async modpackInstall(payload: ModpackInstallPayload): Promise<ModpackInstallResponse> {
    const { data } = await getApiClient().post<ModpackInstallResponse>(
      '/api/marketplace/modpack/install',
      payload
    )
    return data
  },

  // ── Diagnostics & Repair (Sprint 4) ────────────────────────────────────────

  async verifyIntegrity(instanceName: string): Promise<RepairTaskResponse> {
    const { data } = await getApiClient().post<RepairTaskResponse>(
      `/api/repair/${encodeURIComponent(instanceName)}/verify-integrity`
    )
    return data
  },

  async analyzeCrash(instanceName: string): Promise<CrashAnalysisResult> {
    const { data } = await getApiClient().get<CrashAnalysisResult>(
      `/api/repair/${encodeURIComponent(instanceName)}/analyze-crash`
    )
    return data
  },

  async resetOptions(instanceName: string): Promise<ResetOptionsResponse> {
    const { data } = await getApiClient().post<ResetOptionsResponse>(
      `/api/repair/${encodeURIComponent(instanceName)}/reset-options`
    )
    return data
  },

  async cleanCache(): Promise<CleanCacheResponse> {
    const { data } = await getApiClient().post<CleanCacheResponse>('/api/repair/clean-cache')
    return data
  },

  // ── Discord Rich Presence & Theme Music (Sprint 4) ─────────────────────────

  async updateDiscordRpc(
    payload: DiscordRpcUpdatePayload
  ): Promise<{ status: string; rpc_enabled: boolean }> {
    const { data } = await getApiClient().post<{ status: string; rpc_enabled: boolean }>(
      '/api/system/discord_rpc',
      payload
    )
    return data
  },

  async prepareThemeAudio(): Promise<{ ready: boolean; message?: string; error?: string }> {
    const { data } = await getApiClient().post<{ ready: boolean; message?: string; error?: string }>(
      '/api/system/theme/prepare'
    )
    return data
  },

  async getThemeAudioStatus(): Promise<ThemeStatusResponse> {
    const { data } = await getApiClient().get<ThemeStatusResponse>('/api/system/theme/status')
    return data
  },
}

export function getThemeAudioUrl(): string {
  if (!session) return ''
  return `http://127.0.0.1:${session.port}/api/system/theme/audio?token=${encodeURIComponent(session.token)}`
}


