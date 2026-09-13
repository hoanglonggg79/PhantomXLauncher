import * as React from 'react'
import * as SwitchPrimitive from '@radix-ui/react-switch'

import { cn } from '@/lib/utils'

function Switch({
  className,
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      className={cn(
        'peer inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-white/10 transition-colors',
        'data-[state=unchecked]:bg-black/45 data-[state=checked]:border-accent/50 data-[state=checked]:bg-accent/70',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        className={cn(
          'pointer-events-none block size-3.5 rounded-full bg-ink shadow transition-transform',
          'data-[state=unchecked]:translate-x-0.5 data-[state=checked]:translate-x-[18px]'
        )}
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
