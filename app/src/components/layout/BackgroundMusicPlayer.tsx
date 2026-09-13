import { useEffect, useRef, useState } from 'react'
import { Volume2, VolumeX } from 'lucide-react'

import { getThemeAudioUrl } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/app-store'

export function BackgroundMusicPlayer() {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const bgMusicMuted = useAppStore((s) => s.bgMusicMuted)
  const bgMusicVolume = useAppStore((s) => s.bgMusicVolume)
  const setBgMusicMuted = useAppStore((s) => s.setBgMusicMuted)
  const sidecar = useAppStore((s) => s.sidecar)

  const [isPlaying, setIsPlaying] = useState(false)
  const [blocked, setBlocked] = useState(false)

  const audioUrl = sidecar ? getThemeAudioUrl() : ''

  // Sync volume & mute state with HTML5 audio element
  useEffect(() => {
    if (!audioRef.current) return
    audioRef.current.volume = Math.max(0, Math.min(1, bgMusicVolume))
    audioRef.current.muted = bgMusicMuted
  }, [bgMusicVolume, bgMusicMuted])

  // Handle playback & autoplay policies
  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !audioUrl) return

    if (bgMusicMuted) {
      audio.pause()
      setIsPlaying(false)
      return
    }

    const tryPlay = () => {
      audio
        .play()
        .then(() => {
          setIsPlaying(true)
          setBlocked(false)
        })
        .catch(() => {
          // Autoplay policy prevented playback until user interaction
          setBlocked(true)
          setIsPlaying(false)
        })
    }

    tryPlay()

    // Unlock autoplay on first user interaction if blocked
    const handleFirstInteraction = () => {
      if (audio.paused && !useAppStore.getState().bgMusicMuted) {
        audio
          .play()
          .then(() => {
            setIsPlaying(true)
            setBlocked(false)
            window.removeEventListener('click', handleFirstInteraction)
            window.removeEventListener('keydown', handleFirstInteraction)
          })
          .catch(() => undefined)
      }
    }

    window.addEventListener('click', handleFirstInteraction, { once: true })
    window.addEventListener('keydown', handleFirstInteraction, { once: true })

    return () => {
      window.removeEventListener('click', handleFirstInteraction)
      window.removeEventListener('keydown', handleFirstInteraction)
    }
  }, [audioUrl, bgMusicMuted])

  const toggleMute = () => {
    if (!audioRef.current) return
    const nextMuted = !bgMusicMuted
    setBgMusicMuted(nextMuted)
    if (!nextMuted) {
      audioRef.current
        .play()
        .then(() => {
          setIsPlaying(true)
          setBlocked(false)
        })
        .catch(() => undefined)
    }
  }

  if (!audioUrl) return null

  return (
    <>
      <audio
        ref={audioRef}
        src={audioUrl}
        loop
        preload="auto"
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
      />

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleMute}
            className={cn(
              'relative h-8 gap-1.5 px-2.5 text-xs transition-colors',
              !bgMusicMuted && isPlaying
                ? 'border border-accent/20 bg-accent/10 text-accent hover:bg-accent/15'
                : 'text-muted hover:text-white'
            )}
            aria-label={bgMusicMuted ? 'Bật nhạc nền' : 'Tắt nhạc nền'}
            id="btn-bg-music-toggle"
          >
            {bgMusicMuted ? (
              <VolumeX className="size-3.5 text-muted" />
            ) : (
              <Volume2 className={cn('size-3.5', isPlaying ? 'text-accent' : 'text-muted')} />
            )}

            {/* Sound Wave indicator */}
            {!bgMusicMuted && isPlaying ? (
              <div className="flex h-3 items-end gap-0.5" aria-hidden="true">
                <span className="w-0.5 animate-[pulse_0.8s_ease-in-out_infinite] rounded-full bg-accent h-2" />
                <span className="w-0.5 animate-[pulse_0.5s_ease-in-out_infinite] rounded-full bg-accent h-3" />
                <span className="w-0.5 animate-[pulse_0.7s_ease-in-out_infinite] rounded-full bg-accent h-1.5" />
              </div>
            ) : (
              <span className="text-[11px] font-medium opacity-80">
                {bgMusicMuted ? 'Muted' : blocked ? 'Click to play' : `${Math.round(bgMusicVolume * 100)}%`}
              </span>
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p className="font-medium">
            {bgMusicMuted ? 'Bật nhạc nền PhantomX Theme' : `Nhạc nền (${Math.round(bgMusicVolume * 100)}%) — Click để tắt`}
          </p>
        </TooltipContent>
      </Tooltip>
    </>
  )
}
