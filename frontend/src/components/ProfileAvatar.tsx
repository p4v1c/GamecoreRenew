/**
 * The active profile's picture, for a top bar beside Settings and Power: its
 * colour with its picture or initial. Nothing on a box without profiles, so a
 * top bar there looks exactly as before. Pressing it opens Settings → Profiles
 * (the shell's `onProfile`). Themes place it as `sdk.players.Avatar`.
 */
import { useStore } from '../store'
import { AVATARS, initial } from '../settings/avatars'

const PATHS: Record<string, string> = Object.fromEntries(AVATARS.map(([key, , d]) => [key, d]))

export default function ProfileAvatar({ onClick, className = '' }: { onClick?: () => void; className?: string }) {
  const name = useStore((s) => s.playerOneName)
  const look = useStore((s) => s.profileLook)
  if (!name) return null
  const d = look.avatar ? PATHS[look.avatar] : undefined
  return (
    <button type="button" className={`gcs-avatar ${className}`.trim()} onClick={onClick}
            aria-label={`Profile: ${name}`} title={name} style={{ background: look.color || undefined }}>
      {d
        ? <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8"
               strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
        : <span aria-hidden="true">{initial(name)}</span>}
    </button>
  )
}
