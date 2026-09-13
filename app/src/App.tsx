import { useEffect } from 'react'

import { AboutPanel } from '@/components/about/AboutPanel'
import { ConnectionGate } from '@/components/ConnectionGate'
import { TaskConsole } from '@/components/console/TaskConsole'
import { ReportBugDialog } from '@/components/feedback/ReportBugDialog'
import { CreateInstanceDialog } from '@/components/instances/CreateInstanceDialog'
import { InstanceGrid } from '@/components/instances/InstanceGrid'
import { Header } from '@/components/layout/Header'
import { Sidebar } from '@/components/layout/Sidebar'
import { MarketplaceView } from '@/components/marketplace/MarketplaceView'
import { NoticeToast } from '@/components/NoticeToast'
import { SettingsPanel } from '@/components/settings/SettingsPanel'
import { TooltipProvider } from '@/components/ui/tooltip'
import { UpdateDialog } from '@/components/update/UpdateDialog'
import { useAppStore } from '@/store/app-store'

export default function App() {
  const connection = useAppStore((s) => s.connection)
  const screen = useAppStore((s) => s.screen)
  const connect = useAppStore((s) => s.connect)
  const instanceCount = useAppStore((s) => s.instances.length)

  useEffect(() => {
    void connect()
  }, [connect])

  if (connection !== 'ready') {
    return (
      <>
        <ConnectionGate />
        <NoticeToast />
      </>
    )
  }

  return (
    <TooltipProvider delayDuration={300}>
      <div className="relative flex h-full overflow-hidden bg-void">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-40 -left-32 size-[36rem] rounded-full bg-accent/10 blur-[140px]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -right-40 -bottom-48 size-[32rem] rounded-full bg-neon/10 blur-[150px]"
        />

        <Sidebar />

        <main className="relative flex min-w-0 flex-1 flex-col">
          <Header
            actions={screen === 'instances' && instanceCount > 0 ? <CreateInstanceDialog /> : null}
          />

          {screen === 'instances' && <InstanceGrid />}
          {screen === 'marketplace' && <MarketplaceView />}
          {screen === 'settings' && <SettingsPanel />}
          {screen === 'about' && <AboutPanel />}

          <TaskConsole />
        </main>

        <ReportBugDialog />
        <UpdateDialog />
        <NoticeToast />
      </div>
    </TooltipProvider>
  )
}
