import {wave} from '../lib/drawings.js'

/** The playground behind every screen: the cyan floor with its drifting
 * texture, two candy rings and a few floating shapes. CSS-only motion on
 * transform and opacity, stopped by reduced motion and while a game runs
 * (the shell unmounts nothing, so the pause is the `data-still` attribute). */
export function createBackground(sdk, {Icon}) {
  const {html} = sdk.ui
  return function Background() {
    const playing = sdk.nav.use((s) => !!s.sessionGameKey)
    const standby = sdk.nav.use((s) => s.standby)
    return html`<div className="jl-playground" aria-hidden="true"
                     data-still=${playing || standby !== 'off' ? 'true' : 'false'}>
      <div className="jl-texture" />
      <div className="jl-ring jl-ring-one" />
      <div className="jl-ring jl-ring-two" />
      <span className="jl-shape jl-shape-one"><${Icon} name="sparkle" filled=${true} /></span>
      <span className="jl-shape jl-shape-two"><${Icon} name="plus" /></span>
      <span className="jl-shape jl-shape-three"><${Icon} name="ring" /></span>
      <span className="jl-shape jl-shape-four" dangerouslySetInnerHTML=${{__html: wave()}} />
    </div>`
  }
}
