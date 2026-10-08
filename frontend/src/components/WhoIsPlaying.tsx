/**
 * "Who's playing?" at start, drawn by the host over whichever shell is up, so
 * every theme has it without drawing it. Markup: `settings/whoIsPlaying.js`.
 *
 * Asked once per interface start, only with two profiles or more and
 * "Log in automatically" off: a box with one player starts exactly as it did
 * before profiles. A theme switch
 * reloads the page, so "once" is kept in sessionStorage, which a reload keeps
 * and a restart of the interface clears.
 *
 * Decided during the boot and drawn under the splash (the `who` boot step), so
 * the splash hands over straight to the question: read after it, the home
 * showed until the answer came.
 */
import { useEffect, useLayoutEffect, useMemo, useState, type ComponentType } from 'react'
import { api, type ProfilesState } from '../api'
import { useStore } from '../store'
import { markBootStep } from '../lib/boot'
import { buildSdk } from '../lib/themeSdk'
import { createWhoIsPlaying } from '../settings/whoIsPlaying'
import { VirtualKeyboard } from './ui/VirtualKeyboard'
import { useThemeCtx } from './ThemeSurface'
import '../settings/settings.css'

const ASKED_KEY = 'gamecore-who-asked'

// Not with "Log in automatically" on (Settings → Profiles): the box starts
// as the last profile, as a console set to log in by itself does.
export const shouldAskWhoIsPlaying = (s: ProfilesState | null): boolean =>
  !!s && Array.isArray(s.profiles) && s.profiles.length >= 2 && !s.auto_login

/** Already asked since the interface started; storage errors count as not. */
function askedThisStart(): boolean {
  try { return !!sessionStorage.getItem(ASKED_KEY) } catch { return false }
}

// Marked only once the list arrived: a backend still starting must not cost
// the question for the whole run.
function markAsked(): void {
  try { sessionStorage.setItem(ASKED_KEY, '1') } catch { /* private storage: ask again after a reload */ }
}

interface ViewProps {
  profiles: ProfilesState['profiles']
  activeId: string
  active: boolean
  msg: string
  onPick: (id: string) => void
  onAdd: () => void
  onSkip: () => void
}

/** `interactive`: the splash is gone, so the pad may answer the question. */
export default function WhoIsPlaying({ interactive }: { interactive: boolean }) {
  const [state, setState] = useState<ProfilesState | null>(null)
  const [adding, setAdding] = useState(false)
  const [msg, setMsg] = useState('')

  const ownView = useMemo(() => {
    const sdk = buildSdk('', { selectTheme: async () => {} })
    return createWhoIsPlaying(sdk, { skin: 'gcs-skin-default' }) as unknown as ComponentType<ViewProps>
  }, [])
  // The theme's dress when it brought one (`whoIsPlaying`), the host's
  // otherwise; when to ask and what a pick does stay here either way.
  const themeCtx = useThemeCtx()
  const themed = themeCtx?.whoIsPlaying as (ComponentType<ViewProps> & { skin?: string }) | undefined
  // Shown once the theme has loaded: drawn before, it would swap from the
  // host's dress to the theme's under the player and lose the cursor.
  const themeLoading = !!themeCtx?.loading
  const View = themed ?? ownView
  const skin = (themed ? themed.skin : '') || 'gcs-skin-default'

  useEffect(() => {
    if (askedThisStart()) { markBootStep('who'); return }
    // The session is asked too: at boot the store does not know it yet.
    Promise.all([api.profiles.list(), api.games.session()])
      .then(([s, session]) => {
        markAsked()
        // An interface restarted under a running game must not cover it.
        if (shouldAskWhoIsPlaying(s) && !session.game_key) setState(s)
        else markBootStep('who')
      })
      // Never holds the boot: no answer means no question.
      .catch((e) => { console.error('profiles: could not ask who is playing', e); markBootStep('who') })
  }, [])

  // Raises the modal depth, which every shell's own pad handlers respect.
  const open = state !== null && !themeLoading
  // Marked once the question is in the DOM, before the paint: the frame the
  // boot gate waits for then already holds it.
  useLayoutEffect(() => { if (open) markBootStep('who') }, [open])
  useEffect(() => {
    if (!open) return
    useStore.getState().openModal()
    return () => useStore.getState().closeModal()
  }, [open])

  if (!state || themeLoading) return null

  const close = () => setState(null)
  // Closed only once the switch is saved: closing first would leave the
  // player believing they play as someone the backend never switched to.
  const pick = (id: string) => {
    if (id === state.active) return close()
    setMsg('')
    api.profiles.setActive(id)
      .then(close)
      .catch((e) => setMsg(String(e?.message || 'Could not switch profile.')))
  }
  const add = (name: string) => {
    setAdding(false)
    api.profiles.create({ name })
      .then((p) => pick(p.id))
      .catch((e) => setMsg(String(e?.message || 'Could not add that profile.')))
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 950 }}>
      <View profiles={state.profiles} activeId={state.active} active={interactive && !adding} msg={msg}
            onPick={pick} onAdd={() => { setMsg(''); setAdding(true) }} onSkip={close} />
      {adding && (
        <div className={`gcs-who-kb ${skin}`}>
          <div className="gcs-who-kb-panel">
            <VirtualKeyboard title="New profile" placeholder="Name"
                             onConfirm={add} onCancel={() => setAdding(false)} />
          </div>
        </div>
      )}
    </div>
  )
}
