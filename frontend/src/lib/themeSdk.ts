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
import { useStore } from '../store'
import { onGp, useGamepadState, GP_BTN } from '../hooks/useGamepad'
import { onWsEvent } from '../hooks/useWebSocket'
import { playSound, getAudioContext, soundSettings } from './sounds'
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
  nav: Record<string, unknown>
  input: Record<string, unknown>
  system: Record<string, unknown>
  defaults: typeof defaults
}

/**
 * @param themeId  used to resolve asset paths inside the theme's own folder
 */
export function buildSdk(themeId: string): ThemeSdk {
  const html = htm.bind(React.createElement)

  return {
    version: SDK_VERSION,

    ui: {
      html, React,
      useState, useEffect, useRef, useMemo, useCallback,
      motion, AnimatePresence,
    },

    api,

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
    },

    system: {
      onWsEvent,
      /** The user's UI-sound setting always wins over the theme. */
      playSound: (name: Parameters<typeof playSound>[0]) => {
        if (!soundSettings.enabled) return
        playSound(name)
      },
      getAudioContext,
      gamecore: window.gamecore,
      /** Resolve a file shipped inside this theme's folder. */
      asset: (path: string) =>
        `/themes/${encodeURIComponent(themeId)}/${String(path).replace(/^\/+/, '')}`,
    },

    defaults,
  }
}
