import { useEffect } from 'react'
import {
  Coffee,
  Download,
  HardDrive,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { JavaInstall, JavaSource } from '@/lib/types'
import { useAppStore } from '@/store/app-store'

const SOURCE_LABEL: Record<JavaSource, string> = {
  env_java_home: 'JAVA_HOME',
  system_path: 'System PATH',
  registry: 'Registry',
  system: 'System',
  phantomx: 'PhantomX',
  manual: 'Manual',
}

const SOURCE_VARIANT: Record<JavaSource, 'neon' | 'accent' | 'muted'> = {
  env_java_home: 'neon',
  system_path: 'accent',
  registry: 'muted',
  system: 'muted',
  phantomx: 'accent',
  manual: 'muted',
}

const MAJOR_LABEL: Record<number, string> = {
  8: 'Java 8  (MC < 1.17)',
  17: 'Java 17 (MC 1.17–1.20.4)',
  21: 'Java 21 (MC ≥ 1.20.5)',
}

const REQUIRED_MAJORS = [8, 17, 21] as const

function JreRow({ install }: { install: JavaInstall }) {
  const isPhantomX = install.source === 'phantomx'
  const settings = useAppStore((s) => s.settings)
  const saveSettings = useAppStore((s) => s.saveSettings)
  const java = useAppStore((s) => s.java)

  const currentPath = (settings?.java_path || java?.path || '').toLowerCase()
  const isActive = currentPath === install.path.toLowerCase()

  return (
    <div
      className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors ${isActive
        ? 'border-accent/40 bg-accent/5'
        : 'border-white/5 bg-slate-900/60 hover:border-white/10'
        }`}
    >
      <Coffee className={`size-4 shrink-0 ${isActive ? 'text-accent' : 'text-muted'}`} />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-xs font-medium text-ink" title={install.version_string}>
            {install.version_string}
          </p>
          {isActive && (
            <Badge variant="accent" className="h-4 px-1.5 py-0 text-[9px] font-semibold">
              Active
            </Badge>
          )}
        </div>
        <p className="mt-0.5 truncate font-mono text-[10px] text-muted" title={install.path}>
          {install.path}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-1.5">
        <Badge variant="muted" className="text-[10px]">
          {install.arch}
        </Badge>
        <Badge variant={SOURCE_VARIANT[install.source]} className="text-[10px]">
          {SOURCE_LABEL[install.source]}
        </Badge>
        {isPhantomX && (
          <Tooltip>
            <TooltipTrigger asChild>
              <ShieldCheck className="size-3.5 text-accent" />
            </TooltipTrigger>
            <TooltipContent>Managed by PhantomX</TooltipContent>
          </Tooltip>
        )}
        {!isActive && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-[10px] text-muted hover:bg-accent/10 hover:text-accent"
            onClick={() => void saveSettings({ java_path: install.path })}
          >
            Select
          </Button>
        )}
      </div>
    </div>
  )
}

function DownloadButton({ major }: { major: (typeof REQUIRED_MAJORS)[number] }) {
  const installJava = useAppStore((s) => s.installJava)
  const javaInstalls = useAppStore((s) => s.javaInstalls)
  const tasks = useAppStore((s) => s.tasks)

  const alreadyInstalled = javaInstalls.some((j) => j.major === major && j.source === 'phantomx')
  const isDownloading = Object.values(tasks).some(
    (t) => t.running && t.kind === 'java_install' && t.instanceName === `Java ${major}`
  )

  const label = alreadyInstalled ? `Re-download Java ${major}` : `Download Java ${major}`
  const hint = MAJOR_LABEL[major] ?? `Java ${major}`

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          disabled={isDownloading}
          onClick={() => void installJava(major)}
          id={`btn-java-download-${major}`}
          aria-label={label}
        >
          {isDownloading ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Download className="size-3.5" />
          )}
          {isDownloading ? 'Downloading…' : `Java ${major}`}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{hint}</TooltipContent>
    </Tooltip>
  )
}

export function JavaManagerSection() {
  const javaInstalls = useAppStore((s) => s.javaInstalls)
  const javaInstallsLoading = useAppStore((s) => s.javaInstallsLoading)
  const loadJavaInstalls = useAppStore((s) => s.loadJavaInstalls)
  const java = useAppStore((s) => s.java)

  useEffect(() => {
    void loadJavaInstalls()
  }, [])

  return (
    <div className="grid gap-4">
      {/* Current status banner */}
      {java && (
        <div
          className={`flex items-start gap-3 rounded-lg border p-3 text-xs ${java.ok
            ? 'border-accent/20 bg-accent/5 text-ink'
            : 'border-amber-400/20 bg-amber-400/5 text-amber-300'
            }`}
        >
          <Coffee className={`mt-0.5 size-4 shrink-0 ${java.ok ? 'text-accent' : 'text-amber-300'}`} />
          <div className="min-w-0">
            <p className="font-medium">{java.ok ? 'Java detected' : 'Java not found'}</p>
            <p className="mt-0.5 text-muted">{java.message}</p>
            {java.path && (
              <p className="mt-1 break-all font-mono text-[10px] text-muted">{java.path}</p>
            )}
          </div>
          {java.major && (
            <Badge variant="accent" className="ml-auto shrink-0 text-[10px]">
              Java {java.major}
            </Badge>
          )}
        </div>
      )}

      {/* Version mapping info */}
      <div className="rounded-lg border border-white/5 bg-slate-950/40 px-3 py-2">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted">
          Required by Minecraft version
        </p>
        <div className="grid grid-cols-3 gap-2 text-[11px]">
          {(
            [
              { label: 'MC < 1.17', java: 8 },
              { label: 'MC 1.17 – 1.20.4', java: 17 },
              { label: 'MC ≥ 1.20.5', java: 21 },
            ] as const
          ).map(({ label, java: maj }) => (
            <div
              key={maj}
              className="flex flex-col items-center gap-1 rounded-md border border-white/5 bg-slate-900/60 p-2"
            >
              <span className="font-mono text-xs font-semibold text-neon">Java {maj}</span>
              <span className="text-center text-[10px] text-muted">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Installed JREs list */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <HardDrive className="size-3.5 text-muted" />
            <span className="text-xs font-semibold text-ink">
              Detected installations
            </span>
            {javaInstalls.length > 0 && (
              <Badge variant="muted" className="text-[10px]">
                {javaInstalls.length}
              </Badge>
            )}
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            className="size-6 text-muted hover:text-ink"
            onClick={() => void loadJavaInstalls()}
            disabled={javaInstallsLoading}
            aria-label="Refresh Java list"
            id="btn-java-refresh"
          >
            <RefreshCw className={`size-3.5 ${javaInstallsLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        <div className="grid gap-1.5">
          {javaInstallsLoading && javaInstalls.length === 0 && (
            <div className="flex items-center justify-center gap-2 py-6 text-xs text-muted">
              <Loader2 className="size-4 animate-spin" />
              Scanning for Java installations…
            </div>
          )}

          {!javaInstallsLoading && javaInstalls.length === 0 && (
            <div className="rounded-lg border border-amber-400/20 bg-amber-400/5 py-5 text-center">
              <p className="text-xs font-medium text-amber-300">No Java installations found</p>
              <p className="mt-1 text-[11px] text-muted">
                Download a managed runtime below or install Java manually.
              </p>
            </div>
          )}

          {javaInstalls.map((install) => (
            <JreRow key={install.path} install={install} />
          ))}
        </div>
      </div>

      {/* Download section */}
      <div>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted">
          Download managed runtime (Eclipse Temurin)
        </p>
        <p className="mb-3 text-xs text-muted">
          PhantomX sẽ tự động cài đặt và quản lý JRE bên trong thư mục data của nó.
          Progress được hiển thị trong bảng điều khiển tác vụ.
        </p>
        <div className="flex flex-wrap gap-2">
          {REQUIRED_MAJORS.map((major) => (
            <DownloadButton key={major} major={major} />
          ))}
        </div>
      </div>
    </div>
  )
}
