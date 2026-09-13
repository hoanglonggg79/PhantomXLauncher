import { useEffect, useMemo, useState } from 'react'
import { Loader2, Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import type { LoaderName } from '@/lib/types'
import { useShallow } from 'zustand/react/shallow'
import { useAppStore } from '@/store/app-store'

const LOADERS: { id: LoaderName; label: string }[] = [
  { id: 'vanilla', label: 'Vanilla' },
  { id: 'fabric', label: 'Fabric' },
  { id: 'forge', label: 'Forge' },
  { id: 'quilt', label: 'Quilt' },
  { id: 'neoforge', label: 'NeoForge' },
]

const LISTED_LOADERS: LoaderName[] = ['fabric', 'forge']
const AUTO = '__auto__'
const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$/

export function CreateInstanceDialog() {
  const versions = useAppStore((s) => s.versions)
  const latestRelease = useAppStore((s) => s.latestRelease)
  const versionsLoading = useAppStore((s) => s.versionsLoading)
  const loadVersions = useAppStore((s) => s.loadVersions)
  const loadLoaderVersions = useAppStore((s) => s.loadLoaderVersions)
  const createInstance = useAppStore((s) => s.createInstance)
  const settings = useAppStore((s) => s.settings)
  const existing = useAppStore(useShallow((s) => s.instances.map((i) => i.name)))

  const [open, setOpen] = useState(false)
  const [snapshots, setSnapshots] = useState(false)
  const [name, setName] = useState('')
  const [version, setVersion] = useState('')
  const [loader, setLoader] = useState<LoaderName>('vanilla')
  const [loaderVersion, setLoaderVersion] = useState(AUTO)
  const [loaderList, setLoaderList] = useState<string[]>([])
  const [loaderBusy, setLoaderBusy] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  // Sync snapshot toggle when dialog opens or settings change
  useEffect(() => {
    if (open) {
      setSnapshots(Boolean(settings?.snapshots))
    }
  }, [open, settings?.snapshots])

  useEffect(() => {
    if (open) void loadVersions(snapshots)
  }, [open, snapshots, loadVersions])

  useEffect(() => {
    if (!version && latestRelease) setVersion(latestRelease)
  }, [latestRelease, version])

  useEffect(() => {
    setLoaderVersion(AUTO)
    setLoaderList([])
    if (!open || !version || !LISTED_LOADERS.includes(loader)) return

    let cancelled = false
    setLoaderBusy(true)
    void loadLoaderVersions(loader, version)
      .then((list) => {
        if (!cancelled) setLoaderList(list)
      })
      .finally(() => {
        if (!cancelled) setLoaderBusy(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, loader, version, loadLoaderVersions])

  const nameError = useMemo(() => {
    const clean = name.trim()
    if (!clean) return ''
    if (!NAME_RE.test(clean)) return 'Letters, digits, space, dot, dash or underscore only'
    if (existing.includes(clean)) return 'An instance with that name already exists'
    return ''
  }, [name, existing])

  const needsExplicitLoader = loader === 'neoforge'
  const freeTextLoader = loader === 'quilt' || loader === 'neoforge'
  const resolvedLoaderVersion =
    loader === 'vanilla' || loaderVersion === AUTO ? '' : loaderVersion.trim()

  const canSubmit =
    !!name.trim() &&
    !nameError &&
    !!version &&
    !submitting &&
    (!needsExplicitLoader || !!resolvedLoaderVersion)

  const reset = () => {
    setName('')
    setLoader('vanilla')
    setLoaderVersion(AUTO)
    setLoaderList([])
  }

  const submit = async () => {
    setSubmitting(true)
    const ok = await createInstance({
      name: name.trim(),
      version_id: version,
      loader,
      loader_version: resolvedLoaderVersion,
    })
    setSubmitting(false)
    if (ok) {
      setOpen(false)
      reset()
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) reset()
      }}
    >
      <DialogTrigger asChild>
        <Button variant="play" size="sm">
          <Plus className="size-4" />
          New instance
        </Button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create instance</DialogTitle>
          <DialogDescription>
            Files are downloaded into its own folder under the PhantomX data directory.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="instance-name">Name</Label>
            <Input
              id="instance-name"
              value={name}
              autoFocus
              placeholder="My survival world"
              onChange={(e) => setName(e.target.value)}
            />
            {nameError && <p className="text-xs text-rose-300">{nameError}</p>}
          </div>

          <div className="grid gap-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="instance-version">Minecraft version</Label>
              <label className="flex items-center gap-2 text-[11px] text-muted normal-case">
                <Switch
                  checked={snapshots}
                  onCheckedChange={(v) => setSnapshots(v)}
                  aria-label="Include snapshots"
                />
                Snapshots
              </label>
            </div>
            <Select value={version} onValueChange={setVersion} disabled={versionsLoading}>
              <SelectTrigger id="instance-version">
                <SelectValue
                  placeholder={versionsLoading ? 'Loading versions…' : 'Select a version'}
                />
              </SelectTrigger>
              <SelectContent>
                {versions.map((v) => (
                  <SelectItem key={v.id} value={v.id}>
                    {v.id}
                    {v.type !== 'release' ? ` · ${v.type}` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="instance-loader">Mod loader</Label>
              <Select
                value={loader}
                onValueChange={(v) => setLoader(v as LoaderName)}
              >
                <SelectTrigger id="instance-loader">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LOADERS.map((l) => (
                    <SelectItem key={l.id} value={l.id}>
                      {l.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="loader-version">
                Loader build{needsExplicitLoader ? ' *' : ''}
              </Label>
              {loader === 'vanilla' ? (
                <Input id="loader-version" value="—" disabled />
              ) : freeTextLoader ? (
                <Input
                  id="loader-version"
                  value={loaderVersion === AUTO ? '' : loaderVersion}
                  placeholder={needsExplicitLoader ? '21.1.72' : 'latest'}
                  onChange={(e) => setLoaderVersion(e.target.value || AUTO)}
                />
              ) : (
                <Select
                  value={loaderVersion}
                  onValueChange={setLoaderVersion}
                  disabled={loaderBusy}
                >
                  <SelectTrigger id="loader-version">
                    <SelectValue placeholder={loaderBusy ? 'Loading…' : 'Latest'} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={AUTO}>Latest / auto</SelectItem>
                    {loaderList.map((v) => (
                      <SelectItem key={v} value={v}>
                        {v}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          </div>

          {needsExplicitLoader && (
            <p className="text-xs text-amber-300/80">
              NeoForge needs an explicit build number — the installer has no index to pick from.
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button variant="play" disabled={!canSubmit} onClick={() => void submit()}>
            {submitting && <Loader2 className="size-4 animate-spin" />}
            Create &amp; install
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
