/**
 * The object a theme module receives. It is the whole contract — a theme
 * imports nothing from the host, which is what keeps a single React instance in
 * memory and removes any need for an import map.
 *
 * Everything here already existed; this file only gathers it. See
 * docs/themes/README.md for the specification and
 * docs/architecture/05-frontend.md for the detail of each piece.
 */
import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import htm from 'htm'

import { api } from '../api'
import { fetchThemeIndex } from './themeLoader'
import { useStore } from '../store'
import { onGp, useGamepadState, GP_BTN, isPlaying } from '../hooks/useGamepad'
import { rumble, rumbleSettings, type RumblePattern } from './rumble'
import { onWsEvent } from '../hooks/useWebSocket'
import { playSound, getAudioContext, soundSettings } from './sounds'
import { formatGameName, hexToRgb, fmtTime, fmtDate, systemColor } from './format'
import * as defaults from '../components/defaults'

/**
 * SDK major. Bumped when something is removed, changes shape, or becomes
 * REQUIRED by a theme this repository ships.
 *
 * That last clause was learned the hard way. `sdk.defaults.createSettings` and
 * `createPowerView` were added and both shipped themes were rewritten to
 * destructure them — while this constant stayed at 1. So Shelf kept declaring
 * `api: 1`, every bundle old and new answered "compatible", and on a box in the
 * window between the theme landing on disk and the front end restarting onto
 * the matching bundle, Shelf imported cleanly and then threw the moment it
 * called a function that was not there.
 *
 * The player sees that as the theme silently becoming the default one, because
 * the surface boundary catches the throw and swaps in the built-in shell — and
 * after CRASH_LIMIT of those, safe mode refuses the theme outright.
 *
 * `compatible: api <= SDK_VERSION` is the gate that was supposed to prevent
 * exactly this. It can only work if the number moves when the contract does.
 *
 * 3 adds `standby` to the store, and both shipped themes now read it — Summer's
 * screensaver keys its whole overlay off it. On a front end that does not have
 * it, `s.standby` is `undefined`, `undefined !== 'off'` is true, and Summer
 * draws a black rectangle over the box forever. That is a refusal, not a
 * degradation, so the number moves.
 *
 * 5 adds `sdk.session` — suspending a game and resuming it — and all three
 * shipped themes now draw a session bar from it. On a front end without it,
 * `sdk.session` is `undefined` and the theme throws on its first read, which
 * the surface boundary shows the player as their theme silently becoming the
 * default one. Worse than the usual case, because the actions are the only way
 * to reach a suspended game: a theme that half-loaded would leave a frozen
 * emulator holding its memory with nothing on screen able to close it.
 */
// 6 adds spatial library omissions, search/options callbacks and __all__ libraries.
// 7 adds defaults.launchGame: a ROM can launch without navigating to Library.
export const SDK_VERSION = 7

/**
 * Game or application, from the identity the launcher gave the session.
 *
 * A tile with no ROM launches with `game_key === system_id` — see
 * backend/routers/games.py — and that is the only thing telling the two apart
 * once the session exists. Themes need it to say "Close application" rather
 * than "Close game", and a theme getting that wrong is the interface talking
 * about a game the player never started.
 */
const sessionKind = (gameKey: string, systemId: string | null): 'game' | 'app' =>
  systemId !== null && gameKey === systemId ? 'app' : 'game'

/** Every gamepad event a theme may subscribe to. gp:guide is intentionally absent. */
export const GP_EVENTS = [
  'gp:dpad-up', 'gp:dpad-down', 'gp:dpad-left', 'gp:dpad-right',
  'gp:confirm', 'gp:back', 'gp:y', 'gp:x',
  'gp:menu', 'gp:power',
  'gp:l1', 'gp:r1', 'gp:l2', 'gp:r2',
  'gp:connected', 'gp:disconnected',
] as const

/** The core owns this one: double-press kills a running game. */
const RESERVED_EVENTS = new Set(['gp:guide'])

export interface ThemeSdk {
  version: number
  ui: Record<string, unknown>
  api: typeof api
  format: Record<string, unknown>
  nav: Record<string, unknown>
  session: Record<string, unknown>
  themes: Record<string, unknown>
  input: Record<string, unknown>
  system: Record<string, unknown>
  defaults: typeof defaults
}

/**
 * @param themeId  used to resolve asset paths inside the theme's own folder
 */
export interface SdkHost {
  /** The host's own theme switch — clears safe mode and crash counts too. */
  selectTheme: (id: string | null) => Promise<void>
  /** Validated duration from this theme's manifest, also for direct launches. */
  launchMs?: number
}

export function buildSdk(themeId: string, host: SdkHost): ThemeSdk {
  const html = htm.bind(React.createElement)

  return {
    version: SDK_VERSION,

    ui: {
      html, React,
      useState, useEffect, useRef, useMemo, useCallback,
      motion, AnimatePresence,
    },

    api,

    /**
     * How the rest of the UI renders the box's data.
     *
     * Not conveniences: these are the difference between a theme that shows
     * the same information as the default and one that shows it *differently*.
     * A theme reimplementing `gameName` gets ROM-name cleanup subtly wrong, and
     * one reimplementing `systemColor` misses that `system.color` is optional
     * and paints half the dashboard purple.
     */
    format: {
      /** `Super_Mario_64_(USA).z64` → `Super Mario 64`. */
      gameName: formatGameName,
      /** Seconds → the playtime string the whole UI uses. */
      time: fmtTime,
      /** ISO date → the "last played" string. */
      date: fmtDate,
      /** `#7c3aed` → `124, 58, 237`, for rgba() in your own styles. */
      hexToRgb,
      /** A system's accent: its pack's colour, the catalogue's, then the default. */
      systemColor,
    },

    /**
     * So a theme can dress its own theme picker instead of falling back to the
     * host's dark one. Selecting is the host's call either way: it clears safe
     * mode, resets the crash count and reloads the frontend.
     */
    themes: {
      list: () => fetchThemeIndex(),
      select: (id: string | null) => host.selectTheme(id ?? null),
    },

    nav: {
      /** Reactive read — call it inside a component. */
      use: useStore,
      /** One-shot read, for event handlers. */
      get: () => {
        const s = useStore.getState()
        return {
          screen: s.screen,
          selectedSystemId: s.selectedSystemId,
          selectedGameIdx: s.selectedGameIdx,
          gridFocusIdx: s.gridFocusIdx,
          gridPage: s.gridPage,
          sessionGameKey: s.sessionGameKey,
          sessionSystemId: s.sessionSystemId,
          // Read-only on purpose: these are the core's focus and shutdown locks.
          modalDepth: s.modalDepth,
          powerPending: s.powerPending,
          /**
           * 'off' | 'screensaver' | 'sleep'.
           *
           * A theme drawing its own standby screen should read THIS rather than
           * keep its own copy built from the three `standby:*` events. The bus
           * swallows the first press into a wake and gives up after a grace
           * period if the box never answers; a theme mirroring the events
           * separately would keep its overlay on screen after that, which is a
           * black rectangle over a live cursor — the exact fault the guard
           * exists to prevent, reintroduced one level down.
           *
           * Reactive form: sdk.nav.use(s => s.standby).
           */
          standby: s.standby,
        }
      },
      goHome: () => useStore.getState().goHome(),
      goLibrary: (id: string) => useStore.getState().goLibrary(id),
      setGridFocus: (i: number) => useStore.getState().setGridFocus(i),
      setGridPage: (p: number) => useStore.getState().setGridPage(p),
      setSelectedGameIdx: (i: number) => useStore.getState().setSelectedGameIdx(i),
      openModal: () => useStore.getState().openModal(),
      closeModal: () => useStore.getState().closeModal(),
    },

    /**
     * What the box is running, and what may be done about it.
     *
     * The state is split the way the box is: `foreground` is the one thing on
     * the screen, `background` is everything frozen behind it. A theme draws
     * both — the second one is a session bar — and the host guarantees there
     * is always some way to reach a suspended session, so a theme that omits
     * the bar loses nothing but its own styling of it.
     *
     * `nav.sessionGameKey` still means "a game owns the screen" and is still
     * what the pad guard reads. It goes null when a session is suspended,
     * which is what gives the interface back to the player while their game
     * stays alive — so a theme keying anything off it keeps working unchanged.
     */
    session: {
      /** Reactive read — call it inside a component. */
      use: () => {
        const gameKey = useStore(s => s.sessionGameKey)
        const systemId = useStore(s => s.sessionSystemId)
        const background = useStore(s => s.backgroundSessions)
        // Selected one field at a time and rebuilt here: a selector returning
        // a fresh object compares unequal on every store write, which in
        // Zustand's default `Object.is` equality is a render loop.
        return useMemo(() => ({
          foreground: gameKey
            ? { gameKey, systemId, kind: sessionKind(gameKey, systemId) }
            : null,
          background,
        }), [gameKey, systemId, background])
      },
      /** One-shot read, for event handlers. */
      get: () => {
        const s = useStore.getState()
        return {
          foreground: s.sessionGameKey
            ? { gameKey: s.sessionGameKey, systemId: s.sessionSystemId,
                kind: sessionKind(s.sessionGameKey, s.sessionSystemId) }
            : null,
          background: s.backgroundSessions,
        }
      },
      /**
       * Freeze what is on the screen. Resolves once the box has done it.
       *
       * Rejects with the host's own sentence when there is nothing to suspend,
       * which is worth showing rather than swallowing.
       */
      background: () => api.games.background(),
      /** Wake a suspended session. With no number, the most recent one. */
      resume: (session?: number) => api.games.foreground(session),
      /** End a session. With no number, the one on the screen. */
      close: (session?: number) => api.games.kill(session),
    },

    input: {
      /** Same signature as the host's, minus the events the core reserves. */
      onGp: (event: string, handler: (detail?: unknown) => void) => {
        if (RESERVED_EVENTS.has(event)) {
          console.warn(`[gamecore] theme tried to bind reserved event ${event} — ignored`)
          return () => {}
        }
        return onGp(event, handler)
      },
      useGamepadState,
      GP_BTN,
      events: GP_EVENTS,

      /**
       * Punctuate a moment of your own — a launch ceremony landing, a boot
       * animation's impact frame.
       *
       * The routine feedback for a button press is not this: declare a
       * `rumble` table and the input bus fires it, the same way it fires your
       * sounds, so the *when* stays where every other decision about behaviour
       * lives. This is the escape hatch for the things the bus cannot know
       * about, and it is exactly as much latitude as `playSound` already gives.
       *
       * Refused while a game is running: the emulator owns the pad then,
       * motors included, and a theme buzzing over someone's game is the kind
       * of bug that gets blamed on the controller.
       */
      rumble: (pattern: RumblePattern) => {
        if (isPlaying()) return
        rumble(pattern)
      },
      /**
       * The player's haptics setting.
       *
       * Readable so a theme can respect it; writable so a theme that replaces
       * Settings → Audio can still offer it. It used to be read-only, and the
       * comment said "setting it stays in Settings → Audio" — true while that
       * page was always the host's. Once a theme can render its own, that
       * sentence stopped describing a boundary and started describing a hole:
       * replacing the page silently deleted the vibration switch from the box,
       * with the page still there and nothing able to reach it. That is the
       * same failure `catalog` and `storage` shipped as, arriving by a
       * different door.
       */
      get haptics() {
        return {
          get enabled() { return rumbleSettings.enabled },
          set enabled(v: boolean) { rumbleSettings.enabled = !!v },
        }
      },
    },

    system: {
      onWsEvent,
      /** The user's UI-sound setting always wins over the theme. */
      playSound: (name: Parameters<typeof playSound>[0]) => {
        if (!soundSettings.enabled) return
        playSound(name)
      },
      getAudioContext,
      /**
       * The player's sound setting.
       *
       * A theme that runs an ambience needs to READ it: `playSound` gates
       * itself, but a loop the theme starts would otherwise keep playing after
       * the player turned sound off, and ignore their volume.
       *
       * Writable for the same reason `haptics` is — a theme rendering its own
       * Settings → Audio has to be able to set what that page sets, or
       * replacing the page quietly removes the control from the console.
       *
       * `volume` is 0–1 in both directions, which is the unit a theme mixes in;
       * the 0–100 the slider stores is an implementation detail of localStorage
       * and stays behind this boundary. Clamped, because a theme is code its
       * owner installed and a NaN here silences the box until someone finds
       * this key in devtools.
       */
      sound: {
        get enabled() { return soundSettings.enabled },
        set enabled(v: boolean) { soundSettings.enabled = !!v },
        get volume() { return soundSettings.volume / 100 },
        set volume(v: number) {
          const n = Number(v)
          soundSettings.volume = Math.round(
            Math.max(0, Math.min(1, isFinite(n) ? n : 0.6)) * 100)
        },
      },
      gamecore: window.gamecore,

      /*
       * `splashHoldMs` was here, and it is gone with SDK 4.
       *
       * It held a boot animation's first frame for a fixed 4000 ms whenever
       * the machine had booted recently, because the display path — the X mode
       * switch, then the television's HDMI re-sync — is still black when the
       * splash mounts. The reasoning was sound and the mechanism was not: a
       * duration measured on one box, applied to every box, and paid in full
       * on the ones that never needed it. Neither shipped theme ever read it.
       *
       * What replaces it is the `bootReady` prop the host passes to a splash:
       * the animation ends on a held frame and leaves when the interface
       * behind it is actually ready. A television still dark is a television
       * that has nothing to miss.
       */
      /** Resolve a file shipped inside this theme's folder. */
      asset: (path: string) =>
        `/themes/${encodeURIComponent(themeId)}/${String(path).replace(/^\/+/, '')}`,
    },

    defaults: {
      ...defaults,
      launchGame: game => defaults.launchGame(game, host.launchMs),
    },
  }
}
