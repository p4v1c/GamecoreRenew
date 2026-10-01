/** Settings: the host's nine-category screen, dressed in Jelly.
 *
 * Wi-Fi, Bluetooth, Display, Audio, Controllers, Emulators & apps, BIOS,
 * Themes and System are the host's pages (`sdk.defaults.createSettings`), with
 * their confirmations, timers and locks. Jelly sets the layout: the rail on the
 * left, L1/R1 between categories (`pager`), details in dialogs.
 *
 * What it adds is L2/R2, to scroll a long page by a screenful without walking
 * every row. Never under a dialog: a dialog owns the pad.
 */
export function createJellySettings(sdk) {
  const {html, useEffect} = sdk.ui
  const Host = sdk.defaults.createSettings(sdk, {}, {
    skin: 'jelly-settings', layout: 'rail', pager: true, detail: 'dialog',
  })

  return function Settings(props) {
    useEffect(() => {
      const scroll = (dir) => {
        const screen = document.querySelector('.gcs-set.jelly-settings')
        if (!screen || screen.querySelector('.gcs-dlg-scrim')) return
        const page = screen.querySelector('.gcs-set-main')
        if (page) page.scrollBy({top: dir * page.clientHeight * 0.8, behavior: 'smooth'})
      }
      const offs = [
        sdk.input.onGp('gp:l2', () => scroll(-1)),
        sdk.input.onGp('gp:r2', () => scroll(1)),
      ]
      return () => offs.forEach((off) => off())
    }, [])
    return html`<${Host} ...${props} />`
  }
}
