import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold tracking-wide whitespace-nowrap uppercase',
  {
    variants: {
      variant: {
        neon: 'border-neon/30 bg-neon/10 text-neon',
        accent: 'border-accent/30 bg-accent/10 text-accent',
        muted: 'border-white/10 bg-white/[0.05] text-muted',
        warn: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
        danger: 'border-rose-400/30 bg-rose-400/10 text-rose-300',
      },
    },
    defaultVariants: {
      variant: 'muted',
    },
  }
)

function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
