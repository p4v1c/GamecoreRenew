/** AZERTY letters, a page of digits and symbols, space and delete. A key keeps
 * its node when the query changes, so typing never moves the cursor. No
 * accented keys: the search ignores accents. */
const LETTERS = [
  ['A', 'Z', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
  ['Q', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'M'],
  ['W', 'X', 'C', 'V', 'B', 'N', '\'', '-'],
]
const SYMBOLS = [
  ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
  ['&', ':', '.', ',', '!', '?', '+', '/', '#', '@'],
  ['(', ')', '_', '*', '\'', '-'],
]

export function createKeyboard(sdk) {
  const {html} = sdk.ui

  return function Keyboard({page, onKey, onPage, onSpace, onDelete, Icon}) {
    const rows = page === 'symbols' ? SYMBOLS : LETTERS
    return html`<div className="jl-keys" role="group" aria-label="Clavier">
      ${rows.map((row, r) => html`<div className="jl-keys-row" key=${r}>
        ${row.map((k) => html`<button type="button" key=${k} className="jl-key"
          data-nav=${`k-${k}`} onClick=${() => onKey(k)}>${k}</button>`)}
        ${r === 2 ? html`<button type="button" className="jl-key jl-key-wide" data-nav="k-page"
          onClick=${onPage}>${page === 'symbols' ? 'ABC' : '123'}</button>` : null}
      </div>`)}
      <div className="jl-keys-row">
        <button type="button" className="jl-key jl-key-space" data-nav="k-space" onClick=${onSpace}>Espace</button>
        <button type="button" className="jl-key jl-key-del" data-nav="k-del" onClick=${onDelete}
                aria-label="Effacer une lettre"><${Icon} name="erase" /></button>
      </div>
    </div>`
  }
}
