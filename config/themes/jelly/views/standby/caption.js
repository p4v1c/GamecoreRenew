/** The standby's words: the paper caption bottom left, the clock and its
 * date pill bottom right. Both sit above the jellies, which keep out of
 * their boxes (the engine's repel zones). */

const clockOf = (d) => d.toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'})
const dateOf = (d) => d.toLocaleDateString('en-GB', {weekday: 'long', day: 'numeric', month: 'long'})
const TICK_MS = 10_000

export function createCaption(sdk) {
  const {html, useEffect, useState, React} = sdk.ui

  /** The clock's minute, re-read every 10 s. */
  function useNow() {
    const [now, setNow] = useState(() => new Date())
    useEffect(() => {
      const t = setInterval(() => setNow(new Date()), TICK_MS)
      return () => clearInterval(t)
    }, [])
    return now
  }

  /** "Game Boy Advance, played 2 days ago"; the system alone if never played. */
  const metaOf = (game, now) => {
    const ago = sdk.format.playedAgo(game.lastPlayed, now)
    return ago ? `${game.systemName}, ${ago}` : game.systemName
  }

  function Caption({game, boxRef}) {
    const now = useNow()
    // Laid out even before the first game, so the jellies avoid its box from the start.
    return html`<div ref=${boxRef} className="jl-sb-caption" data-empty=${game ? 'false' : 'true'}>
      ${game && html`<${React.Fragment}>
        <span className="jl-sb-eyebrow">Wobbling now</span>
        <strong className="jl-sb-title">${game.title}</strong>
        <span className="jl-sb-meta">${metaOf(game, now)}</span>
      <//>`}
    </div>`
  }

  function Clock({boxRef}) {
    const now = useNow()
    return html`<div ref=${boxRef} className="jl-sb-clock">
      <b className="jl-sb-time">${clockOf(now)}</b>
      <span className="jl-sb-pill">
        <span className="jl-sb-date">${dateOf(now)}</span>
        <span className="jl-sb-wake">Press any button</span>
      </span>
    </div>`
  }

  return {Caption, Clock}
}
