/**
 * Shelf's handovers back to and from a frozen game.
 *
 * The launch already has a ceremony and it stays where it is: the cartridge
 * rises off the shelf and the iris closes on its label, drawn in views/
 * library.js because it needs the jacket that is on screen. This file is the
 * other two moments, which have no shelf to leave from:
 *
 *   resume   a game that is already frozen is coming back — the iris closes
 *            again, without the rise, because nothing was picked up
 *   suspend  the game let go and the shelf is back — the iris opens
 *
 * The same iris both ways, so the box has one gesture for "the screen changes
 * hands" rather than three unrelated ones. `launch` is deliberately ignored
 * here: the library is already drawing it, and two overlays for one handover
 * is worse than none.
 *
 * The host says when — `transition` in the store, set by the resume the session
 * bar sends and by the backgrounded event — and holds the resume for
 * `launch.ms`. `CLOSE_MS` below must therefore equal that number, or the
 * emulator takes the screen mid-iris. `backend/tests/test_theme_ceremony.py`
 * keeps the two honest.
 */

/** The close, on a resume. Must equal `launch.ms` in theme.json. */
export const CLOSE_MS = 1780

/** The open, on a suspend. Held by nothing — the game is already frozen. */
export const OPEN_MS = 760

export const createCeremony = (sdk) => {
  const { html, useState, useEffect } = sdk.ui

  return () => {
    const transition = sdk.nav.use((s) => s.transition)
    // Held one beat past the store, so the picture finishes instead of being
    // unmounted on the frame the host stops caring.
    const [shown, setShown] = useState(null)

    useEffect(() => {
      if (transition === 'resume' || transition === 'suspend') { setShown(transition); return }
      if (!shown) return
      const hold = setTimeout(() => setShown(null), shown === 'suspend' ? OPEN_MS : 200)
      return () => clearTimeout(hold)
    }, [transition, shown])

    if (!shown) return null

    return html`
      <div class="cz-handover" data-move=${shown} aria-hidden="true">
        <div class="cz-handover-iris"></div>
      </div>`
  }
}
