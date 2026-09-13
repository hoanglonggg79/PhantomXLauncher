import { getSession } from './api'
import type {
  TaskCompleteEvent,
  TaskEvent,
  TaskLogEvent,
  TaskProgressEvent,
} from './types'

/**
 * Silence budget before the stream is declared dead (GLOBAL RULE 1).
 *
 * The sidecar emits a `heartbeat` data frame every 5s, so two missed heartbeats
 * mean the connection — not the task — is gone. Without this watchdog a sidecar
 * that OOMs or crashes mid-task leaves the UI spinning forever, because
 * EventSource silently retries instead of surfacing an error.
 */
export const HEARTBEAT_TIMEOUT_MS = 10_000

export interface TaskHandlers {
  onProgress?: (event: TaskProgressEvent) => void
  onLog?: (event: TaskLogEvent) => void
  onComplete?: (event: TaskCompleteEvent) => void
  onHeartbeat?: (timestamp: string) => void
  onError?: (message: string) => void
}

export function subscribeTask(taskId: string, handlers: TaskHandlers): () => void {
  const { port, token } = getSession()
  const url = `http://127.0.0.1:${port}/api/events/${encodeURIComponent(taskId)}?token=${encodeURIComponent(token)}`

  const source = new EventSource(url)
  let finished = false
  let watchdog: ReturnType<typeof setTimeout> | null = null

  const close = () => {
    if (watchdog !== null) {
      clearTimeout(watchdog)
      watchdog = null
    }
    if (source.readyState !== EventSource.CLOSED) source.close()
  }

  const fail = (message: string) => {
    if (finished) return
    finished = true
    close()
    handlers.onError?.(message)
  }

  // Any frame (including a heartbeat) proves the stream is alive.
  const armWatchdog = () => {
    if (finished) return
    if (watchdog !== null) clearTimeout(watchdog)
    watchdog = setTimeout(
      () =>
        fail(
          `No data from the task stream for ${HEARTBEAT_TIMEOUT_MS / 1000}s — treating the connection as dead`
        ),
      HEARTBEAT_TIMEOUT_MS
    )
  }

  source.onopen = () => armWatchdog()

  source.onmessage = (message: MessageEvent<string>) => {
    armWatchdog()

    let event: TaskEvent
    try {
      event = JSON.parse(message.data) as TaskEvent
    } catch {
      return
    }

    if (event.type === 'progress') handlers.onProgress?.(event)
    else if (event.type === 'log') handlers.onLog?.(event)
    else if (event.type === 'heartbeat') handlers.onHeartbeat?.(event.timestamp)
    else if (event.type === 'complete') {
      finished = true
      close()
      handlers.onComplete?.(event)
    }
  }

  source.onerror = () => fail('Lost connection to the task event stream')

  armWatchdog()

  return () => {
    finished = true
    close()
  }
}
