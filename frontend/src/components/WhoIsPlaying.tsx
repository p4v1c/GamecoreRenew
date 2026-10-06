/**
 * "Who's playing?" at start, drawn by the host over whichever shell is up, so
 * every theme has it without drawing it. Markup: `settings/whoIsPlaying.js`.
 *
 * Asked once per interface start, and only with two profiles or more: a box
 * with one player starts exactly as it did before profiles. A theme switch
 * reloads the page, so "once" is kept in sessionStorage, which a reload keeps
 * and a restart of the interface clears.
 */
import { useEffect, useMemo, useState, type ComponentType } from 'react'
import { api, type ProfilesState } from '../api'
import { useStore } from '../store'
import { buildSdk } from '../lib/themeSdk'
import { createWhoIsPlaying } from '../settings/whoIsPlaying'
import { VirtualKeyboard } from './ui/VirtualKeyboard'
import '../settings/settings.css'

const ASKED_KEY = 'gamecore-who-asked'

export const shouldAskWhoIsPlaying = (s: ProfilesState | null): boolean =>
  !!s && Array.isArray(s.profiles) && s.profiles.length >= 2

/** True the first time per interface start; storage errors count as first. */
function firstAskThisStart(): boolean {
  try {
    if (sessionStorage.getItem(ASKED_KEY)) return false
    sessionStorage.setItem(ASKED_KEY, '1')
  } catch { /* private storage: ask, at worst again after a reload */ }
  return true
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

export default function WhoIsPlaying({ enabled }: { enabled: boolean }) {
  const [state, setState] = useState<ProfilesState | null>(null)
  const [adding, setAdding] = useState(false)
  const [msg, setMsg] = useState('')

  const View = useMemo(() => {
    const sdk = buildSdk('', { selectTheme: async () => {} })
    return createWhoIsPlaying(sdk, { skin: 'gcs-skin-default' }) as unknown as ComponentType<ViewProps>
  }, [])

  useEffect(() => {
    if (!enabled || !firstAskThisStart()) return
    api.profiles.list()
      .then((s) => {
        // An interface restarted under a running game must not cover it.
        if (shouldAskWhoIsPlaying(s) && !useStore.getState().sessionGameKey) setState(s)
      })
      .catch((e) => console.error('profiles: could not ask who is playing', e))
  }, [enabled])

  // Raises the modal depth, which every shell's own pad handlers respect.
  const open = state !== null
  useEffect(() => {
    if (!open) return
    useStore.getState().openModal()
    return () => useStore.getState().closeModal()
  }, [open])

  if (!state) return null

  const close = () => setState(null)
  const pick = (id: string) => {
    close()
    if (id !== state.active) {
      api.profiles.setActive(id).catch((e) => console.error('profiles: could not switch', e))
    }
  }
  const add = (name: string) => {
    setAdding(false)
    api.profiles.create({ name })
      .then((p) => pick(p.id))
      .catch((e) => setMsg(String(e?.message || 'Could not add that profile.')))
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 950 }}>
      <View profiles={state.profiles} activeId={state.active} active={!adding} msg={msg}
            onPick={pick} onAdd={() => { setMsg(''); setAdding(true) }} onSkip={close} />
      {adding && (
        <div className="gcs-who-kb gcs-skin-default">
          <div className="gcs-who-kb-panel">
            <VirtualKeyboard title="New profile" placeholder="Name"
                             onConfirm={add} onCancel={() => setAdding(false)} />
          </div>
        </div>
      )}
    </div>
  )
}
