/**
 * The active profile's picture, for a top bar beside Settings and Power: its
 * colour with its picture or initial. Nothing on a box without profiles, so a
 * top bar there looks exactly as before. Pressing it opens Settings → Profiles
 * (the shell's `onProfile`). Themes place it as `sdk.players.Avatar`.
 */
import { useStore } from '../store'
import { avatarSvg, initial } from '../settings/avatars'

export default function ProfileAvatar({ onClick, className = '' }: { onClick?: () => void; className?: string }) {
  const name = useStore((s) => s.profileName)
  const look = useStore((s) => s.profileLook)
  if (!name) return null
  const svg = avatarSvg(look.avatar)
  return (
    <button type="button" className={`gcs-avatar ${className}`.trim()} onClick={onClick}
            aria-label={`Profile: ${name}`} title={name} style={{ background: look.color || undefined }}>
      {svg
        ? <span className="gcs-animal" aria-hidden="true" dangerouslySetInnerHTML={{ __html: svg }} />
        : <span aria-hidden="true">{initial(name)}</span>}
    </button>
  )
}
