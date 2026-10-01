import {toggleJacketStyle, createUseJacketStyle} from '../lib/jacket-style.js'

/** The chips several screens share: open the search, and 3D boxes or flat
 * jackets for every card. */
export function createChips(sdk, {Icon}) {
  const {html} = sdk.ui
  const PadKey = sdk.ui.PadKey || (({k}) => html`<kbd>${k}</kbd>`)
  const useJacketStyle = createUseJacketStyle(sdk)

  function SearchChip({nav, label = 'Search', onClick}) {
    return html`<button type="button" className="jl-chip jl-chip-search" data-nav=${nav} onClick=${onClick}>
      <${Icon} name="search" />${label}<${PadKey} k="△" /></button>`
  }

  function StyleChip({nav}) {
    const style = useJacketStyle()
    const solid = style === 'box-3d'
    return html`<button type="button" className="jl-chip jl-chip-style" data-nav=${nav}
                        aria-pressed=${String(solid)} onClick=${toggleJacketStyle}>
      <${Icon} name=${solid ? 'box' : 'flat'} />${solid ? '3D boxes' : 'Flat covers'}</button>`
  }

  return {SearchChip, StyleChip}
}
