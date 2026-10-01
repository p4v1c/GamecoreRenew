const WORDS = {launch: 'C’est parti', resume: 'On reprend', suspend: 'En pause'}
// The whole handover. `launch.ms` in theme.json is this number: the host holds
// the game back exactly as long as the blob takes to land and settle.
const LAUNCH_MS = 900

/** The launch handover: a jelly blob bounces up and wobbles while the host
 * waits the manifest's `launch.ms` before starting the game. The host owns
 * the timing and the layer; this only draws the transition it is told about. */
export function createCeremony(sdk) {
  const {html} = sdk.ui
  return function Ceremony() {
    const transition = sdk.nav.use((s) => s.transition)
    if (!transition || !WORDS[transition]) return null
    return html`<div className="jl-ceremony" data-kind=${transition} aria-hidden="true"
                     style=${{'--jl-launch': `${LAUNCH_MS}ms`}}>
      <span className="jl-ceremony-blob" />
      <span className="jl-ceremony-word">${WORDS[transition]}</span>
    </div>`
  }
}
