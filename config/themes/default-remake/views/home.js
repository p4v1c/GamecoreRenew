/**
 * The dashboard — markup only.
 *
 * Every number and every index here arrives as a prop. Nothing in this file
 * decides anything: paging, focus, wrap and launching are HomeScreen's, for the
 * default and for this theme alike. That is the seam the whole SDK rests on,
 * and it is why a themed dashboard cannot navigate differently from the stock
 * one — it cannot navigate at all.
 *
 * `onActivate(i)` takes an index within the CURRENT page, not within `systems`.
 * Passing the wrong one launches a neighbour, which is the sort of bug that
 * only shows up on page two.
 */
import { createCard } from '../lib/card.js'

export const createHomeView = (sdk) => {
  const { html, motion } = sdk.ui
  const Card = createCard(sdk)

  return ({
    systems, playtime, counts, focusIdx, page, pageCount, cols, rows, perPage,
    totals, onPage, onActivate,
  }) => {
    const pages = Math.max(pageCount, 1)

    return html`
      <div class="dr-home">
        <div class="dr-stats">
          <div class="dr-stats-label">YOUR LIBRARY</div>
          <div class="dr-stats-row">
            ${[
              { v: totals.systems, l: 'Systems' },
              { v: totals.games, l: 'Games' },
              { v: `${totals.hours}h`, l: 'Played' },
            ].map(s => html`
              <div key=${s.l} class="dr-stat">
                <b>${s.v}</b><i>${s.l}</i>
              </div>`)}
          </div>
        </div>

        <div class="dr-grid-wrap">
          ${page > 0
            ? html`<button class="dr-arrow dr-arrow-l" onClick=${() => onPage(page - 1)}>‹</button>`
            : null}
          ${page < pageCount - 1
            ? html`<button class="dr-arrow dr-arrow-r" onClick=${() => onPage(page + 1)}>›</button>`
            : null}

          <div class="dr-grid-clip">
            <${motion.div}
              animate=${{ x: pageCount > 1 ? `${-(page / pages) * 100}%` : 0 }}
              transition=${{ type: 'spring', stiffness: 280, damping: 30, clamp: true }}
              style=${{ display: 'flex', width: `${pages * 100}%` }}>
              ${Array.from({ length: pages }).map((_, pi) => html`
                <div key=${pi} class="dr-page"
                     style=${{
                       width: `${100 / pages}%`,
                       gridTemplateColumns: `repeat(${cols}, 1fr)`,
                       gridTemplateRows: `repeat(${rows}, 1fr)`,
                     }}>
                  ${systems.slice(pi * perPage, (pi + 1) * perPage).map((system, i) => html`
                    <${Card} key=${system.id}
                             system=${system}
                             playtime=${playtime[system.id]}
                             gameCount=${counts[system.id]}
                             focused=${pi === page && i === focusIdx}
                             onClick=${() => onActivate(i)} />`)}
                </div>`)}
            <//>
          </div>
        </div>

        ${pageCount > 1 ? html`
          <div class="dr-dots">
            ${Array.from({ length: pageCount }).map((_, i) => html`
              <div key=${i} class="dr-dot" data-on=${i === page ? '1' : '0'}
                   onClick=${() => onPage(i)} />`)}
          </div>` : null}

        <div class="dr-hint">
          ${pageCount > 1
            ? '← → Navigate · L1/R1 Page · ✕ Select · □ Controller'
            : '← → Navigate · ✕ Select · □ Controller'}
        </div>
      </div>`
  }
}
