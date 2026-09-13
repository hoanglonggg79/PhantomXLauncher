import * as React from 'react'
import * as SliderPrimitive from '@radix-ui/react-slider'

import { cn } from '@/lib/utils'

function Slider({
  className,
  ...props
}: React.ComponentProps<typeof SliderPrimitive.Root>) {
  return (
    <SliderPrimitive.Root
      className={cn(
        'relative flex w-full touch-none items-center select-none data-[disabled]:opacity-50',
        className
      )}
      {...props}
    >
      <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-black/45">
        <SliderPrimitive.Range className="absolute h-full bg-gradient-to-r from-accent to-neon" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        className={cn(
          'block size-4 rounded-full border-2 border-accent bg-void shadow-[0_0_12px_rgba(16,185,129,0.55)]',
          'transition-transform hover:scale-110 focus-visible:outline-none'
        )}
      />
    </SliderPrimitive.Root>
  )
}

export { Slider }
