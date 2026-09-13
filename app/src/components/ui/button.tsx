import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium outline-none transition-[background-color,box-shadow,opacity,transform] duration-150 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'border border-white/10 bg-white/[0.06] text-ink hover:bg-white/[0.1]',
        play: 'bg-accent font-semibold text-[#03150e] shadow-[0_0_20px_rgba(16,185,129,0.4)] hover:bg-accent-bright',
        neon: 'border border-neon/40 bg-neon/5 text-neon hover:bg-neon/10',
        outline: 'border border-white/15 bg-transparent text-ink hover:bg-white/[0.06]',
        ghost: 'text-muted hover:bg-white/[0.06] hover:text-ink',
        danger:
          'border border-rose-400/25 bg-rose-500/15 text-rose-300 hover:bg-rose-500/25',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        default: 'h-9 px-4',
        lg: 'h-11 px-6 text-base',
        icon: 'size-9',
        'icon-sm': 'size-8',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : 'button'
  return (
    <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />
  )
}

export { Button, buttonVariants }
