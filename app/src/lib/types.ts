export interface SidecarInfo {
  port: number
  token: string
}

export interface Instance {
  name: string
  version_id: string
  loader: string
  loader_version: string
  game_dir: string
  created_at: string
  last_played: string
  play_count: number
  notes: string
  mod_count: number
  installed: boolean
  running: boolean
}

export interface MinecraftVersion {
  id: string
  type: string
  release_time: string
}

export interface VersionsResponse {
  versions: MinecraftVersion[]
  count: number
  latest_release: string
}

export interface LoaderVersionsResponse {
  loader: string
  mc_version: string
  versions: string[]
  supported: boolean
}

export interface JavaStatus {
  ok: boolean
  message: string
  path: string
  major: number | null
  required_for_mc: number | null
  version_matrix: { lt_1_17: number; '1.17_to_1.20.4': number; gte_1_20_5: number } | null
  installs_count: number
}

// ── Java Runtime Management (Sprint 2) ─────────────────────────────────────

export type JavaSource = 'env_java_home' | 'system_path' | 'registry' | 'system' | 'phantomx' | 'manual'

export interface JavaInstall {
  path: string
  version_string: string
  major: number
  arch: string
  source: JavaSource
}

export interface JavaListResponse {
  installs: JavaInstall[]
  count: number
}

export interface JavaInstallTaskResponse {
  task_id: string
  major: number
}

export type AuthMode = 'offline' | 'elyby'

export interface Settings {
  username: string
  ram: number
  java_path: string
  extra_jvm: string
  snapshots: boolean
  close_on_launch: boolean
  auth_mode?: AuthMode
  bg_music_enabled?: boolean
  bg_music_volume?: number
  discord_rpc_enabled?: boolean
  [key: string]: unknown
}

export type SettingsPatch = Partial<
  Pick<
    Settings,
    | 'username'
    | 'ram'
    | 'java_path'
    | 'extra_jvm'
    | 'snapshots'
    | 'close_on_launch'
    | 'auth_mode'
    | 'bg_music_enabled'
    | 'bg_music_volume'
    | 'discord_rpc_enabled'
  >
>

export interface ElybyProfile {
  username: string
  uuid: string
}

export interface ElybyLoginResponse {
  profile: ElybyProfile
  client_token: string
}

export interface ElybyProfileResponse {
  profile: ElybyProfile | null
  logged_in: boolean
}

export interface AppInfo {
  app_name: string
  app_version: string
  app_author: string
  base_dir: string
  instances_dir: string
  log_dir: string
  qt_available: boolean
  keyring_available: boolean
  psutil_available: boolean
  java_ok: boolean
  java_status: string
}

export interface ReleaseNote {
  tag: string
  name: string
  published_at: string
  html_url: string
  body: string
  prerelease: boolean
  is_current: boolean
}

export interface ChangelogResponse {
  releases: ReleaseNote[]
  current_version: string
  has_update: boolean
  latest_version: string
  repo_url: string
  offline?: boolean
  error?: string
}

export interface TaskHandle {
  instance: Instance
  task_id: string
  username?: string
}

export interface CloneInstancePayload {
  new_name: string
  copy_saves?: boolean
  copy_configs?: boolean
  copy_mods?: boolean
}

export interface CloneInstanceResponse {
  source: string
  name: string
  path: string
  task_id: string
}

export interface UpdateInstancePayload {
  name?: string
  notes?: string
}

export interface UpdateInstanceResponse {
  instance: Instance
  changed: string[]
}

export interface DeleteInstanceResponse {
  name: string
  deleted: boolean
  task_id?: string
}

export interface OpenFolderResponse {
  name: string
  path: string
  opened: boolean
}

export type LoaderName = 'vanilla' | 'fabric' | 'forge' | 'quilt' | 'neoforge'

export interface TaskProgressEvent {
  type: 'progress'
  task_id: string
  current: number
  total: number
  label: string
  timestamp: string
}

export interface TaskLogEvent {
  type: 'log'
  task_id: string
  level: string
  message: string
  timestamp: string
}

export interface TaskCompleteEvent {
  type: 'complete'
  task_id: string
  success: boolean
  result: Record<string, unknown> | null
  timestamp: string
}

/**
 * Keep-alive frame the sidecar emits every 5s while a task is quiet. It carries
 * no payload: its only job is to reset the client watchdog so a slow task is not
 * mistaken for a dead connection.
 */
export interface TaskHeartbeatEvent {
  type: 'heartbeat'
  task_id: string
  timestamp: string
}

export type TaskEvent =
  | TaskProgressEvent
  | TaskLogEvent
  | TaskCompleteEvent
  | TaskHeartbeatEvent

// ── Mod Management ─────────────────────────────────────────────────────────

export interface Mod {
  filename: string
  display_name: string
  size: number
  enabled: boolean
}

export interface ListModsResponse {
  mods: Mod[]
  count: number
}

export interface ToggleModPayload {
  filename: string
  enabled: boolean
}

export interface ToggleModResponse {
  mod: Mod
  changed: boolean
}

export interface DeleteModResponse {
  filename: string
  deleted: boolean
}

export interface OpenModsFolderResponse {
  name: string
  path: string
  opened: boolean
}

export interface UploadModResponse {
  mod: Mod
  uploaded: boolean
}

// ── Mod Marketplace (Sprint 3A) ─────────────────────────────────────────────

export type MarketplaceSource = 'modrinth' | 'curseforge'

export interface MarketplaceModItem {
  id: string
  slug: string
  title: string
  description: string
  author: string
  icon_url: string
  raw_icon_url: string
  downloads: number
  follows: number
  categories: string[]
  loaders: string[]
  versions: string[]
  source: MarketplaceSource
  web_url: string
}

export interface MarketplaceSearchResponse {
  source: MarketplaceSource
  hits: MarketplaceModItem[]
  total: number
  offset: number
  limit: number
  error?: string
}

export interface MarketplaceGalleryImage {
  url: string
  raw_url: string
  title: string
  description: string
  featured?: boolean
}

export interface MarketplaceProjectDetail {
  source: MarketplaceSource
  id: string
  slug: string
  title: string
  description: string
  body: string
  author: string
  icon_url: string
  raw_icon_url: string
  downloads: number
  followers: number
  categories: string[]
  loaders: string[]
  game_versions?: string[]
  gallery: MarketplaceGalleryImage[]
  web_url: string
  source_url?: string
  issues_url?: string
  wiki_url?: string
}

export interface MarketplaceVersionFile {
  id: string
  filename: string
  size: number
  download_url: string
  primary: boolean
}

export interface MarketplaceVersion {
  id: string
  name: string
  version_number: string
  game_versions: string[]
  loaders: string[]
  release_type: string
  date_published: string
  downloads: number
  files: MarketplaceVersionFile[]
}

export interface InstallMarketplaceModPayload {
  instance_name: string
  source: MarketplaceSource
  project_id: string
  project_title: string
  file_id: string
  download_url: string
  filename: string
}

export interface InstallMarketplaceModResponse {
  task_id: string
  instance_name: string
  filename: string
  project_title: string
}

// ── Diagnostics & GDPR Bug Report (Sprint 3A) ──────────────────────────────

export interface SystemSpecs {
  os: string
  cpu: string
  ram: string
  gpu: string
  java_version: string
}

export interface DiagnosticsContext {
  app_version: string
  specs: SystemSpecs
  log_snippet: string
  log_file_name: string
  has_log_file: boolean
}

export interface BugReportPayload {
  title: string
  description: string
  steps?: string
  include_specs: boolean
  include_log: boolean
  website?: string
}

export interface BugReportResponse {
  status: 'success' | 'error'
  message: string
}

// ── Update Checker (Sprint 3A) ─────────────────────────────────────────────

export interface UpdateCheckResponse {
  current_version: string
  latest_version: string
  has_update: boolean
  repo_url: string
  releases_url: string
  error?: string | null
}

// ── Supporter Badge System (Sprint 3A++) ─────────────────────────────────────

export interface SupporterVerifyResponse {
  valid: boolean
  badge?: 'supporter'
  discord_id?: string
  error?: string
}

export interface SupporterStatus {
  active: boolean
  badge?: 'supporter'
  discord_id?: string
  redeemed_at?: string
  theme?: 'default' | 'cyberpunk' | 'synthwave'
}

// ── Modpack Installation (Sprint 3B) ─────────────────────────────────────────

export type ModpackFormat = 'curseforge' | 'modrinth' | 'unknown'

export interface ModpackUploadResponse {
  temp_path: string
  filename: string
  format: ModpackFormat
  detected_name?: string
  mc_version?: string
  loader?: string
  loader_version?: string
  mod_count?: number
}

export interface ModpackInstallPayload {
  name: string
  source: 'modrinth' | 'curseforge' | 'local'
  project_id?: string
  file_id?: string
  local_path?: string
}

export interface ModpackInstallResponse {
  task_id: string
  name: string
}

// ── Diagnostics & Repair (Sprint 4) ──────────────────────────────────────────

export interface RepairTaskResponse {
  task_id: string
  instance: string
}

export interface CrashAnalysisResult {
  has_crash: boolean
  source_file: string
  full_path: string
  category: 'oom' | 'mod_conflict' | 'java_mismatch' | 'unknown' | 'none'
  title: string
  suggestion: string
  matched_detail: string
  raw_snippet: string
  full_log: string
}

export interface ResetOptionsResponse {
  success: boolean
  instance: string
  path: string
  backup?: string | null
  message: string
}

export interface CleanCacheResponse {
  cleaned_items: number
  cleaned_bytes: number
  cleaned_mb: number
  message: string
}

export interface DiscordRpcUpdatePayload {
  status: 'idle' | 'marketplace' | 'in_game'
  instance_name?: string
  loader?: string
  mc_version?: string
  is_supporter?: boolean
}

export interface ThemeStatusResponse {
  downloaded: boolean
  path: string
}

