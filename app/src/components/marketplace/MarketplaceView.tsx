import { useEffect, useState } from 'react'
import {
  Download,
  Flame,
  FolderDown,
  Globe,
  Loader2,
  Package,
  Search,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { MarketplaceSource } from '@/lib/types'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/app-store'

import { ModDetailModal } from './ModDetailModal'
import { ModpackView } from './ModpackView'


const COMMON_MC_VERSIONS = [
  '1.21.4',
  '1.21.1',
  '1.20.4',
  '1.20.1',
  '1.19.4',
  '1.19.2',
  '1.18.2',
  '1.16.5',
  '1.12.2',
]

const LOADERS = [
  { id: '', label: 'Tất cả Loader' },
  { id: 'fabric', label: 'Fabric' },
  { id: 'forge', label: 'Forge' },
  { id: 'quilt', label: 'Quilt' },
  { id: 'neoforge', label: 'NeoForge' },
]

const SORTS = [
  { id: 'downloads', label: 'Lượt tải nhiều nhất' },
  { id: 'popularity', label: 'Phổ biến nhất' },
  { id: 'updated', label: 'Mới cập nhật' },
  { id: 'newest', label: 'Mới nhất' },
]

function formatDownloads(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}M`
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(1)}K`
  }
  return count.toString()
}

export function MarketplaceView() {
  const source = useAppStore((s) => s.marketplaceSource)
  const setSource = useAppStore((s) => s.setMarketplaceSource)
  const hits = useAppStore((s) => s.marketplaceHits)
  const total = useAppStore((s) => s.marketplaceTotal)
  const loading = useAppStore((s) => s.marketplaceLoading)
  const query = useAppStore((s) => s.marketplaceSearchQuery)
  const mcVersion = useAppStore((s) => s.marketplaceMcVersion)
  const loader = useAppStore((s) => s.marketplaceLoader)
  const sort = useAppStore((s) => s.marketplaceSort)
  const setFilters = useAppStore((s) => s.setMarketplaceFilters)
  const search = useAppStore((s) => s.searchMarketplace)
  const openDetail = useAppStore((s) => s.openMarketplaceDetail)

  const [localQuery, setLocalQuery] = useState(query)
  const [marketplaceTab, setMarketplaceTab] = useState<'mods' | 'modpacks'>('mods')

  // Trigger initial search if empty
  useEffect(() => {
    if (hits.length === 0 && !loading) {
      void search()
    }
  }, [])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFilters({ query: localQuery })
    void search()
  }

  const handleSourceChange = (newSource: MarketplaceSource) => {
    setSource(newSource)
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Top Segmented Navigation: Mods vs Modpacks */}
      <div className="flex items-center justify-between border-b border-white/10 bg-white/[0.015] px-6 py-2.5">
        <div className="flex items-center gap-1.5 p-1 bg-surface-muted/50 rounded-lg border border-border/40">
          <button
            type="button"
            onClick={() => setMarketplaceTab('mods')}
            className={cn(
              'px-3.5 py-1 text-xs font-semibold rounded-md transition-all flex items-center gap-1.5',
              marketplaceTab === 'mods'
                ? 'bg-accent text-accent-foreground shadow-sm'
                : 'text-muted hover:text-ink'
            )}
          >
            <Package className="size-3.5" />
            <span>Khám Phá Mods</span>
          </button>
          <button
            type="button"
            onClick={() => setMarketplaceTab('modpacks')}
            className={cn(
              'px-3.5 py-1 text-xs font-semibold rounded-md transition-all flex items-center gap-1.5',
              marketplaceTab === 'modpacks'
                ? 'bg-accent text-accent-foreground shadow-sm'
                : 'text-muted hover:text-ink'
            )}
          >
            <FolderDown className="size-3.5" />
            <span>Cài đặt Modpack Tự Động</span>
          </button>
        </div>

        <div className="text-[11px] text-muted">
          {marketplaceTab === 'mods'
            ? `${source === 'modrinth' ? 'Modrinth' : 'CurseForge'} Marketplace`
            : 'CurseForge .zip / Modrinth .mrpack'}
        </div>
      </div>

      {marketplaceTab === 'modpacks' ? (
        <div className="flex-1 overflow-y-auto p-6">
          <ModpackView />
        </div>
      ) : (
        <>
          {/* Search and Filters Header */}
          <div className="border-b border-white/10 bg-white/[0.02] p-6 pb-4">

            {/* Source Switcher */}
            <div className="flex flex-wrap items-center justify-between gap-4 pb-4">
              <div className="flex items-center gap-2">
                <Button
                  variant={source === 'modrinth' ? 'play' : 'outline'}
                  size="sm"
                  onClick={() => handleSourceChange('modrinth')}
                  className="gap-1.5"
                >
                  <Globe className="size-3.5" />
                  <span>Modrinth</span>
                </Button>
                <Button
                  variant={source === 'curseforge' ? 'neon' : 'outline'}
                  size="sm"
                  onClick={() => handleSourceChange('curseforge')}
                  className="gap-1.5"
                >
                  <Flame className="size-3.5" />
                  <span>CurseForge</span>
                </Button>
              </div>

              <div className="text-xs text-muted">
                Tìm thấy <strong className="text-ink">{total.toLocaleString()}</strong> mods
              </div>
            </div>

            {/* Filter controls row */}
            <form onSubmit={handleSearchSubmit} className="flex flex-wrap items-center gap-3">
              <div className="relative min-w-[240px] flex-1">
                <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
                <Input
                  type="text"
                  placeholder={`Tìm mod trên ${source === 'modrinth' ? 'Modrinth' : 'CurseForge'}…`}
                  value={localQuery}
                  onChange={(e) => setLocalQuery(e.target.value)}
                  className="h-9 pl-9 text-xs"
                />
              </div>

              {/* MC Version Filter */}
              <Select
                value={mcVersion || 'all'}
                onValueChange={(val) => {
                  const v = val === 'all' ? '' : val
                  setFilters({ mcVersion: v })
                  setTimeout(() => void search(), 50)
                }}
              >
                <SelectTrigger className="h-9 w-36 text-xs">
                  <SelectValue placeholder="Phiên bản MC" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all" className="text-xs">
                    Mọi phiên bản
                  </SelectItem>
                  {COMMON_MC_VERSIONS.map((v) => (
                    <SelectItem key={v} value={v} className="text-xs">
                      Minecraft {v}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Loader Filter */}
              <Select
                value={loader || 'all'}
                onValueChange={(val) => {
                  const l = val === 'all' ? '' : val
                  setFilters({ loader: l })
                  setTimeout(() => void search(), 50)
                }}
              >
                <SelectTrigger className="h-9 w-36 text-xs">
                  <SelectValue placeholder="Mod Loader" />
                </SelectTrigger>
                <SelectContent>
                  {LOADERS.map((ldr) => (
                    <SelectItem key={ldr.id || 'all'} value={ldr.id || 'all'} className="text-xs">
                      {ldr.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* Sort Filter */}
              <Select
                value={sort}
                onValueChange={(val) => {
                  setFilters({ sort: val })
                  setTimeout(() => void search(), 50)
                }}
              >
                <SelectTrigger className="h-9 w-44 text-xs">
                  <SelectValue placeholder="Sắp xếp" />
                </SelectTrigger>
                <SelectContent>
                  {SORTS.map((s) => (
                    <SelectItem key={s.id} value={s.id} className="text-xs">
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Button type="submit" variant="neon" size="sm" className="h-9 gap-1.5" disabled={loading}>
                {loading ? <Loader2 className="size-3.5 animate-spin" /> : <Search className="size-3.5" />}
                <span>Tìm kiếm</span>
              </Button>
            </form>
          </div>

          {/* Mod Grid */}
          <div className="flex-1 overflow-y-auto p-6">
            {loading ? (
              <div className="flex h-64 flex-col items-center justify-center gap-3">
                <Loader2 className="size-8 animate-spin text-accent" />
                <p className="text-xs text-muted">Đang tìm kiếm mods…</p>
              </div>
            ) : hits.length === 0 ? (
              <div className="flex h-64 flex-col items-center justify-center gap-2 text-center">
                <Package className="size-10 text-muted opacity-40" />
                <h3 className="text-sm font-semibold text-ink">Không tìm thấy mod nào</h3>
                <p className="max-w-sm text-xs text-muted">
                  Thử thay đổi từ khóa tìm kiếm hoặc bỏ bớt bộ lọc phiên bản / loader.
                </p>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {hits.map((mod) => (
                  <Card
                    key={`${mod.source}-${mod.id}`}
                    onClick={() => void openDetail(mod.source, mod.id)}
                    className="group relative cursor-pointer overflow-hidden border-white/10 bg-white/[0.03] transition-all hover:-translate-y-0.5 hover:border-accent/40 hover:bg-white/[0.06] hover:shadow-lg"
                  >
                    <CardContent className="flex flex-col gap-3 p-4">
                      <div className="flex items-start gap-3">
                        {/* Mod Icon */}
                        <div className="size-12 shrink-0 overflow-hidden rounded-xl border border-white/10 bg-white/5 p-1">
                          <img
                            src={mod.icon_url || '/icon.png'}
                            alt={mod.title}
                            className="size-full rounded-lg object-contain transition-transform group-hover:scale-105"
                            onError={(e) => {
                              ; (e.target as HTMLImageElement).src = '/icon.png'
                            }}
                          />
                        </div>

                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <h4 className="truncate text-xs font-bold text-ink group-hover:text-accent-bright">
                              {mod.title}
                            </h4>
                          </div>
                          <p className="truncate text-[11px] text-muted">
                            by {mod.author}
                          </p>
                          <div className="mt-1 flex items-center gap-2 text-[10px] text-muted">
                            <span className="flex items-center gap-0.5">
                              <Download className="size-3 text-neon" />
                              {formatDownloads(mod.downloads)}
                            </span>
                            <Badge
                              variant={mod.source === 'modrinth' ? 'accent' : 'warn'}
                              className="px-1 py-0 text-[9px] uppercase"
                            >
                              {mod.source}
                            </Badge>
                          </div>
                        </div>
                      </div>

                      <p className="line-clamp-2 text-[11px] text-muted/90">
                        {mod.description}
                      </p>

                      {/* Categories Tags */}
                      <div className="mt-auto flex flex-wrap gap-1">
                        {mod.loaders.map((ldr) => (
                          <span
                            key={ldr}
                            className="rounded bg-accent/10 px-1.5 py-0.5 text-[9px] font-medium text-accent"
                          >
                            {ldr}
                          </span>
                        ))}
                        {mod.categories.slice(0, 2).map((cat) => (
                          <span
                            key={cat}
                            className="rounded bg-white/5 px-1.5 py-0.5 text-[9px] text-muted"
                          >
                            {cat}
                          </span>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>

          {/* Mod Detail Modal */}
          <ModDetailModal />
        </>
      )}
    </div>
  )
}

