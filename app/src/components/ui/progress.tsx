import * as React from 'react'
import * as ProgressPrimitive from '@radix-ui/react-progress'

import { cn } from '@/lib/utils'

function Progress({
  className,
  value,
  indeterminate = false,
  ...props
}: React.ComponentProps<typeof ProgressPrimitive.Root> & { indeterminate?: boolean }) {
  const pct = Math.min(100, Math.max(0, value ?? 0))

  return (
    <ProgressPrimitive.Root
      value={value}
      className={cn(
        'relative h-2 w-full overflow-hidden rounded-full border border-white/5 bg-black/40',
        className
      )}
      {...props}
    >
      <ProgressPrimitive.Indicator
        className={cn(
          'h-full rounded-full bg-gradient-to-r from-accent to-neon shadow-[0_0_12px_rgba(16,185,129,0.45)]',
          indeterminate
            ? 'w-1/3 animate-pulse-ring'
            : 'transition-transform duration-300 ease-out'
        )}
        style={indeterminate ? undefined : { transform: `translateX(-${100 - pct}%)`, width: '100%' }}
      />
    </ProgressPrimitive.Root>
  )
}

export { Progress }
