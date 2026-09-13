import { motion } from 'framer-motion'
import { Boxes, Info, Settings2, ShoppingBag, Zap } from 'lucide-react'

import { cn } from '@/lib/utils'
import { useAppStore, type Screen } from '@/store/app-store'

const NAV: { id: Screen; label: string; icon: typeof Boxes }[] = [
  { id: 'instances', label: 'Instances', icon: Boxes },
  { id: 'marketplace', label: 'Chợ Mod & Modpack', icon: ShoppingBag },
  { id: 'settings', label: 'Settings', icon: Settings2 },
  { id: 'about', label: 'About', icon: Info },
]

export function Sidebar() {
  const screen = useAppStore((s) => s.screen)
  const setScreen = useAppStore((s) => s.setScreen)
  const connection = useAppStore((s) => s.connection)
  const sidecar = useAppStore((s) => s.sidecar)
  const running = useAppStore((s) => s.instances.filter((i) => i.running).length)

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-white/10 bg-white/[0.04] backdrop-blur-md">
      <div className="flex items-center gap-2.5 px-4 py-5">
        <div className="grid size-8 place-items-center rounded-lg border border-accent/30 bg-accent/10">
          <Zap className="size-4 text-accent" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-wide">PhantomX</div>
          <div className="text-[10px] tracking-[0.18em] text-muted uppercase">Launcher</div>
        </div>
      </div>

      <nav className="flex flex-col gap-1 px-2">
        {NAV.map(({ id, label, icon: Icon }) => {
          const active = screen === id
          return (
            <button
              key={id}
              onClick={() => setScreen(id)}
              className={cn(
                'relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors',
                active ? 'text-ink' : 'text-muted hover:bg-white/[0.05] hover:text-ink'
              )}
            >
              {active && (
                <motion.span
                  layoutId="nav-active"
                  transition={{ type: 'spring', stiffness: 420, damping: 34 }}
                  className="absolute inset-0 rounded-lg border border-white/10 bg-white/[0.07]"
                />
              )}
              <Icon className={cn('relative size-4', active && 'text-accent')} />
              <span className="relative font-medium">{label}</span>
              {id === 'instances' && running > 0 && (
                <span className="relative ml-auto rounded-md bg-accent/15 px-1.5 text-[10px] font-semibold text-accent">
                  {running}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      <div className="mt-auto px-4 pb-4 text-[10px] text-muted">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'size-1.5 rounded-full',
              connection === 'ready'
                ? 'bg-accent shadow-[0_0_8px_rgba(16,185,129,0.9)]'
                : connection === 'connecting'
                  ? 'bg-amber-400'
                  : 'bg-rose-500'
            )}
          />
          <span className="tracking-wide uppercase">
            {connection === 'ready' ? 'Core online' : connection}
          </span>
        </div>
        {sidecar && <div className="mt-1 font-mono opacity-60">127.0.0.1:{sidecar.port}</div>}
      </div>
    </aside>
  )
}
