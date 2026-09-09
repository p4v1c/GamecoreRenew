/** Theme-local media index cache shared by Orbit's backdrop and physical art.
 * Successful answers are cached; failures remain retryable. Concurrent callers
 * for the same game share one request.
 */
const cache = new Map()
const inflight = new Map()
const key = (systemId, filename) => `${systemId}::${filename}`

export const listMediaIndex = (sdk, systemId, filename) => {
  if (!systemId || !filename || !sdk.api.media?.list) return Promise.resolve({media: {}})
  const k = key(systemId, filename)
  if (cache.has(k)) return Promise.resolve(cache.get(k))
  if (inflight.has(k)) return inflight.get(k)

  const request = sdk.api.media.list(systemId, filename).then(index => {
    const answer = index || {media: {}}
    cache.set(k, answer)
    return answer
  }).finally(() => inflight.delete(k))

  inflight.set(k, request)
  return request
}
