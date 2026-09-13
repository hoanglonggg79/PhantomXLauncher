import { invoke } from '@tauri-apps/api/core'
import type { SidecarInfo } from './types'

export type { SidecarInfo }

export async function getSidecarInfo(): Promise<SidecarInfo> {
  try {
    return await invoke<SidecarInfo>('get_sidecar_info')
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    throw new Error(`Failed to connect to sidecar: ${detail}`)
  }
}

export async function hideLauncher(): Promise<void> {
  try {
    await invoke('hide_launcher')
  } catch (err) {
    console.warn('Failed to hide launcher window:', err)
  }
}

export async function showLauncher(): Promise<void> {
  try {
    await invoke('show_launcher')
  } catch (err) {
    console.warn('Failed to show launcher window:', err)
  }
}

export async function closeLauncher(): Promise<void> {
  try {
    await invoke('close_launcher')
  } catch (err) {
    console.warn('Failed to close launcher window:', err)
  }
}

export async function openExternalUrl(url: string): Promise<void> {
  if (!url) return
  try {
    const { openUrl } = await import('@tauri-apps/plugin-opener')
    await openUrl(url)
  } catch (err) {
    const inTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
    if (inTauri) {
      console.error('openExternalUrl failed (check opener permissions):', err)
      return
    }
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}

