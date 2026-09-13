import { Boxes, Loader2 } from 'lucide-react'

import { CreateInstanceDialog } from '@/components/instances/CreateInstanceDialog'
import { InstanceCard } from '@/components/instances/InstanceCard'
import { ModManagerDialog } from '@/components/instances/ModManagerDialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useAppStore } from '@/store/app-store'

export function InstanceGrid() {
  const instances = useAppStore((s) => s.instances)
  const loading = useAppStore((s) => s.instancesLoading)

  if (!instances.length) {
    return (
      <div className="grid flex-1 place-items-center px-6 py-10">
        <div className="flex max-w-sm flex-col items-center gap-3 text-center">
          <div className="grid size-14 place-items-center rounded-2xl border border-white/10 bg-white/[0.04]">
            {loading ? (
              <Loader2 className="size-6 animate-spin text-muted" />
            ) : (
              <Boxes className="size-6 text-muted" />
            )}
          </div>
          <div>
            <h2 className="text-sm font-semibold">No instances yet</h2>
            <p className="mt-1 text-xs text-muted">
              Create one to download a Minecraft version and its mod loader into an isolated
              folder.
            </p>
          </div>
          <CreateInstanceDialog />
        </div>
      </div>
    )
  }

  return (
    <>
      <ScrollArea className="flex-1">
        <div className="grid grid-cols-1 gap-3 px-6 py-5 sm:grid-cols-2 xl:grid-cols-3">
          {instances.map((instance, index) => (
            <InstanceCard key={instance.name} instance={instance} index={index} />
          ))}
        </div>
      </ScrollArea>
      {/* Single global Mod Manager dialog, driven by the Zustand store */}
      <ModManagerDialog />
    </>
  )
}
