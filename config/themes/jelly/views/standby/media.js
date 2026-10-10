/** The featured jelly's picture: its game's clip, or a screenshot panning
 * slowly. One <video> for the whole standby, so two clips can never play at
 * once; `release()` empties it, which is what frees the decoder. */
export function createFeatureMedia() {
  const frame = document.createElement('div')
  frame.className = 'jl-sb-media'
  const video = document.createElement('video')
  video.className = 'jl-sb-clip'
  video.muted = true
  video.playsInline = true
  video.preload = 'auto'
  video.setAttribute('aria-hidden', 'true')
  const still = document.createElement('img')
  still.className = 'jl-sb-still'
  still.alt = ''
  const film = document.createElement('span')
  film.className = 'jl-sb-film'
  let handlers = null

  function detach() {
    if (!handlers) return
    video.removeEventListener('loadedmetadata', handlers.meta)
    video.removeEventListener('ended', handlers.end)
    video.removeEventListener('error', handlers.end)
    handlers = null
  }

  /** Put `entry`'s media in `blobEl`, hidden and loading. `onLength(s)` gets
   * the clip's duration, `onEnd()` its end or failure. */
  function load(blobEl, entry, {onLength, onEnd}) {
    release()
    frame.replaceChildren()
    if (entry.kind === 'video') {
      handlers = {meta: () => onLength(video.duration), end: () => onEnd()}
      video.addEventListener('loadedmetadata', handlers.meta)
      video.addEventListener('ended', handlers.end)
      video.addEventListener('error', handlers.end)
      video.src = entry.url
      frame.appendChild(video)
    } else if (entry.kind === 'still') {
      still.src = entry.url
      frame.appendChild(still)
    }
    frame.appendChild(film)
    blobEl.insertBefore(frame, blobEl.querySelector('.jl-sb-shine'))
  }

  /** Fade the media in over the cover and start the clip. A cover-only
   * feature has no media: its cover simply grows with the jelly. */
  function show() {
    frame.classList.add('is-on')
    if (frame.contains(video) || frame.contains(still)) frame.parentElement?.classList.add('is-featured')
    if (frame.contains(video)) video.play().catch(() => {})
  }

  /** Fade it out; the cover comes back. The clip keeps its last frame. */
  function hide() {
    frame.classList.remove('is-on')
    frame.parentElement?.classList.remove('is-featured')
    video.pause()
  }

  /** Stop, empty and take the media out of the page. */
  function release() {
    detach()
    hide()
    video.removeAttribute('src')
    video.load()
    still.removeAttribute('src')
    frame.remove()
  }

  return {load, show, hide, release}
}
