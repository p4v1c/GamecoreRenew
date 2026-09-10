/** Scroll an active element into view without making optional browser support fatal. */
export const reveal = (el, opts) => {
  try { el?.scrollIntoView?.(opts) } catch { /* not worth a blank screen */ }
}
