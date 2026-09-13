import { useEffect, useState } from 'react'
import {
  AlertCircle,
  Calendar,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  History,
  Loader2,
  RefreshCw,
  Sparkles,
  Tag,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { api, describeError } from '@/lib/api'
import { openExternalUrl } from '@/lib/sidecar'
import type { ChangelogResponse, ReleaseNote } from '@/lib/types'

function formatReleaseDate(dateStr: string): string {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return dateStr
  }
}

function MarkdownBody({ content }: { content: string }) {
  const lines = content.split('\n')

  return (
    <div className="space-y-1.5 text-xs text-ink/80 leading-relaxed font-sans">
      {lines.map((rawLine, idx) => {
        const line = rawLine.trim()

        if (!line) {
          return <div key={idx} className="h-1" />
        }

        if (line.startsWith('### ')) {
          return (
            <h4 key={idx} className="mt-2.5 mb-1 font-semibold text-xs text-neon tracking-wide">
              {line.slice(4)}
            </h4>
          )
        }
        if (line.startsWith('## ')) {
          return (
            <h3 key={idx} className="mt-3 mb-1 font-semibold text-sm text-ink border-b border-white/5 pb-1">
              {line.slice(3)}
            </h3>
          )
        }
        if (line.startsWith('# ')) {
          return (
            <h2 key={idx} className="mt-3 mb-1 font-bold text-sm text-ink">
              {line.slice(2)}
            </h2>
          )
        }

        if (line.startsWith('* ') || line.startsWith('- ')) {
          const text = line.slice(2)
          return (
            <div key={idx} className="flex items-start gap-2 pl-1 py-0.5">
              <span className="mt-1.5 size-1 shrink-0 rounded-full bg-accent/70" />
              <p className="min-w-0 flex-1">{renderInlineStyles(text)}</p>
            </div>
          )
        }

        return (
          <p key={idx} className="py-0.5">
            {renderInlineStyles(line)}
          </p>
        )
      })}
    </div>
  )
}

function renderInlineStyles(text: string) {
  const codeParts = text.split(/(`[^`]+`)/g)
  return codeParts.map((part, i) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code
          key={i}
          className="rounded bg-slate-800/80 px-1 py-0.5 font-mono text-[11px] text-neon/90 border border-white/5"
        >
          {part.slice(1, -1)}
        </code>
      )
    }

    const boldParts = part.split(/(\*\*[^*]+\*\*)/g)
    return boldParts.map((bPart, j) => {
      if (bPart.startsWith('**') && bPart.endsWith('**') && bPart.length > 4) {
        return (
          <strong key={j} className="font-semibold text-ink">
            {bPart.slice(2, -2)}
          </strong>
        )
      }
      return bPart
    })
  })
}

function ReleaseCard({
  release,
  defaultExpanded,
}: {
  release: ReleaseNote
  defaultExpanded: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div
      className={`rounded-lg border transition-all ${release.is_current
        ? 'border-accent/30 bg-accent/[0.03]'
        : 'border-white/5 bg-slate-900/60 hover:border-white/10'
        }`}
    >
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 p-3 text-left focus-visible:outline-none"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
      >
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          <Badge
            variant={release.is_current ? 'accent' : 'neon'}
            className="font-mono text-[11px] px-2 py-0.5"
          >
            <Tag className="mr-1 size-3" />
            {release.tag}
          </Badge>

          {release.is_current && (
            <Badge variant="accent" className="text-[10px] h-4.5">
              Current Version
            </Badge>
          )}

          {release.prerelease && (
            <Badge variant="warn" className="text-[10px] h-4.5">
              Pre-release
            </Badge>
          )}

          <span className="truncate text-xs font-semibold text-ink">
            {release.name}
          </span>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {release.published_at && (
            <span className="flex items-center gap-1 text-[10px] text-muted">
              <Calendar className="size-3" />
              {formatReleaseDate(release.published_at)}
            </span>
          )}

          {expanded ? (
            <ChevronDown className="size-4 text-muted" />
          ) : (
            <ChevronRight className="size-4 text-muted" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-white/5 px-4 py-3">
          <MarkdownBody content={release.body} />

          <div className="mt-3 pt-2 flex items-center justify-end border-t border-white/5">
            <button
              type="button"
              onClick={() => void openExternalUrl(release.html_url)}
              className="inline-flex items-center gap-1 text-[11px] text-neon/80 hover:text-neon transition-colors"
            >
              <span>Xem Release trên GitHub</span>
              <ExternalLink className="size-3" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export function ChangelogSection() {
  const [data, setData] = useState<ChangelogResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchChangelog = async (forceRefresh = false) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.getChangelog(forceRefresh)
      setData(res)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchChangelog()
  }, [])

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History className="size-4 text-neon" />
            <CardTitle>Changelog & Updates</CardTitle>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon-sm"
              className="size-7 text-muted hover:text-ink"
              disabled={loading}
              onClick={() => void fetchChangelog(true)}
              aria-label="Refresh changelog"
              id="btn-refresh-changelog"
            >
              <RefreshCw className={`size-3.5 ${loading ? 'animate-spin' : ''}`} />
            </Button>

            {data?.repo_url && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs gap-1.5"
                onClick={() => void openExternalUrl(`${data.repo_url}/releases`)}
              >
                <span>Releases</span>
                <ExternalLink className="size-3" />
              </Button>
            )}
          </div>
        </div>
        <CardDescription>
          Release notes và lịch sử phiên bản được lấy từ GitHub Releases API.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* New Version Alert Banner */}
        {data?.has_update && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-accent/40 bg-accent/10 p-3 text-xs">
            <div className="flex items-center gap-2 min-w-0">
              <Sparkles className="size-4 shrink-0 text-accent animate-pulse" />
              <div>
                <p className="font-semibold text-accent-bright">
                  Có phiên bản mới: v{data.latest_version}
                </p>
                <p className="text-[11px] text-muted">
                  Bạn đang sử dụng phiên bản v{data.current_version}. Truy cập GitHub Release để tải phiên bản mới nhất.
                </p>
              </div>
            </div>
            <Button
              variant="play"
              size="sm"
              className="shrink-0 h-7 text-xs gap-1"
              onClick={() =>
                void openExternalUrl(`${data.repo_url}/releases/tag/${data.latest_version}`)
              }
            >
              <span>Get v{data.latest_version}</span>
              <ExternalLink className="size-3" />
            </Button>
          </div>
        )}

        {/* Error / Offline Alert */}
        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-amber-400/20 bg-amber-400/5 p-3 text-xs text-amber-300">
            <AlertCircle className="size-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="font-medium">Không thể tải release notes</p>
              <p className="text-[11px] text-muted">{error}</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="h-6 text-[10px]"
              onClick={() => void fetchChangelog(true)}
            >
              Retry
            </Button>
          </div>
        )}

        {/* Loading Spinner */}
        {loading && !data && (
          <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted">
            <Loader2 className="size-4 animate-spin text-neon" />
            Đang tải release notes từ GitHub…
          </div>
        )}

        {/* Releases list */}
        {data && data.releases.length > 0 && (
          <div className="space-y-2">
            {data.releases.map((release, index) => (
              <ReleaseCard
                key={release.tag || index}
                release={release}
                defaultExpanded={index === 0 || release.is_current}
              />
            ))}
          </div>
        )}

        {data && data.releases.length === 0 && !loading && (
          <p className="py-6 text-center text-xs text-muted">
            Không tìm thấy release trên GitHub.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
