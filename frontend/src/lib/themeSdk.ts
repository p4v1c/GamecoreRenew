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

/** SDK major. Bumped only when something is removed or changes shape. */
export const SDK_VERSION = 1

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

      /**
       * How long a boot animation should hold its first frame, in ms.
       *
       * Electron asks for this at cold boot (`?splashHold=`) because the
       * display path — the X mode switch, then the TV's HDMI re-sync — is
       * still black when the splash mounts. Without the hold, the animation
       * starts against a dead screen and the first thing the player actually
       * sees is the middle of it.
       *
       * The default splash honoured this and nothing said so, so every themed
       * splash was starting mid-animation on the one boot that matters. Parsed
       * and clamped here rather than left to each theme to rediscover from
       * window.location.
       */
      splashHoldMs: Math.min(10000, Math.max(0,
        Number(new URLSearchParams(window.location.search).get('splashHold')) || 0)),
      /** Resolve a file shipped inside this theme's folder. */
      asset: (path: string) =>
        `/themes/${encodeURIComponent(themeId)}/${String(path).replace(/^\/+/, '')}`,
    },

    defaults,
  }
}
