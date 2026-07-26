/**
 * Holiday — example theme.
 *
 * Paints two layers and nothing else: it returns a shell that is the default
 * shell with a background and a decor passed in. 60 lines, not a UI rewrite —
 * that is what composing the default shell buys.
 *
 * Native ES module, no build step. Markup goes through sdk.ui.html.
 * Contract: docs/themes/README.md
 */
export default (sdk) => {
  const { html, useState, useEffect, useMemo } = sdk.ui

  // ── background ──────────────────────────────────────────────────────────────
  const Background = () => html`<div class="hol-bg" />`

  // ── decor: snow + a sleigh crossing now and then ─────────────────────────────
  const Decor = () => {
    // The host already unmounts decor while a game runs. Standby is ours to
    // handle: nothing should animate behind a screensaver or a dark screen.
    const [asleep, setAsleep] = useState(false)
    useEffect(() => {
      const offs = [
        sdk.system.onWsEvent('standby:screensaver', () => setAsleep(true)),
        sdk.system.onWsEvent('standby:sleep', () => setAsleep(true)),
        sdk.system.onWsEvent('standby:exit', () => setAsleep(false)),
      ]
      return () => offs.forEach(off => off())
    }, [])

    // Only render on the dashboard — the library needs its cover art readable.
    const screen = sdk.nav.use(s => s.screen)

    // Fixed count, computed once: the motion budget is 8 animated elements.
    const flakes = useMemo(
      () => Array.from({ length: 7 }, (_, i) => ({
        left: `${(i * 13 + 7) % 96}%`,
        duration: `${9 + (i % 4) * 2.5}s`,
        delay: `${i * 1.6}s`,
        size: `${11 + (i % 3) * 4}px`,
      })),
      [],
    )

    if (asleep || screen !== 'home') return null

    return html`
      <div class="hol-layer">
        ${flakes.map((f, i) => html`
          <span
            key=${i}
            class="hol-flake"
            style=${{
              left: f.left,
              fontSize: f.size,
              animationDuration: f.duration,
              animationDelay: f.delay,
            }}
          >❄</span>
        `)}
        <img class="hol-sleigh" src=${sdk.system.asset('assets/sleigh.svg')} alt="" />
      </div>
    `
  }

  // One shell, composed from the default one: this theme only paints, so it
  // hands its two layers to sdk.defaults.Shell and inherits every screen.
  const Shell = () => html`
    <${sdk.defaults.Shell} background=${Background} decor=${Decor} />`

  return { shell: Shell }
}
