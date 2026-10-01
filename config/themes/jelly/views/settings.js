/** Settings: the host's nine categories (`createSettings`), dressed in Jelly:
 * rail, L1/R1 between categories, details in dialogs. Jelly adds L2/R2 to
 * scroll a long page, never under a dialog, which owns the pad. */
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
