/**
 * The game box as an object you can turn, not a picture of one.
 *
 * ScreenScraper ships the faces separately — `box-front`, `box-spine`,
 * `box-back` — so the box can be rebuilt as an actual cuboid instead of
 * displayed as a pre-rendered photograph. Six faces in CSS 3D, no WebGL: the
 * ocean already owns a GL context and a second one competing for the GPU on a
 * mini PC is a poor trade for a piece of cover art.
 *
 * Two things this file is careful about, because both decide whether the
 * feature is pleasant or annoying:
 *
 *  · **Not every game has three faces.** Plenty have only a front. A cuboid
 *    built from a missing spine is a grey slab, which looks broken in a way a
 *    flat cover never does — so the box only becomes an object when the
 *    material is really there, and otherwise falls back, in order, to the
 *    pre-rendered `box-3d`, then to the host's Cover (which itself falls back
 *    to /api/covers). Three steps down, each one still a picture of the game.
 *
 *  · **Nothing on screen says it turns.** So it turns on its own: a slow, small
 *    drift that reads as "this is a physical thing" rather than as an
 *    animation. It stops the instant the player takes the stick and resumes a
 *    few seconds after they let go. The hint bar gains a line too — the drift
 *    suggests, the hint states.
 *
 * The stick is read through the SDK's per-frame state, but the transform is
 * written straight to the node from a rAF loop. Re-rendering React sixty times
 * a second beside a running WebGL canvas is exactly the kind of thing that
 * makes a launcher feel slow.
 */

// How far the box may turn, in degrees. Past about 55° the front face is edge
// on and the art stops being readable — the point is to see the spine and a
// hint of the back, not to inspect the barcode.
const YAW_MAX = 52
const PITCH_MAX = 20

// Idle drift: small and slow enough to be missed if you are reading the
// synopsis, obvious enough if you are looking at the box.
const IDLE_YAW = 7
const IDLE_PITCH = 2.5
const IDLE_PERIOD = 9000      // ms for a full cycle
const IDLE_AFTER = 1400       // ms of stillness before it starts
const IDLE_RESUME = 2600      // ms after the player lets go

const DEADZONE = 0.14
const SPRING = 0.12           // how fast the box chases the stick

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v)
const dead = (v) => (Math.abs(v) < DEADZONE ? 0 : (v - Math.sign(v) * DEADZONE) / (1 - DEADZONE))

/**
 * Natural size of an image URL, or null.
 *
 * The timeout is not defensive padding. A face that is still `deferred` is
 * fetched on demand, behind the scraper's global lock and its 1.2 s spacing —
 * and while a library is being swept that queue is minutes long. Waiting on it
 * silently is what left the panel showing a flat jacket with no explanation.
 * Give up, show the best still image, and let the next visit find it cached.
 */
const measure = (url, ms = 6000) => new Promise((resolve) => {
  const img = new Image()
  let done = false
  const finish = (v) => { if (!done) { done = true; resolve(v) } }
  img.onload = () => finish({ w: img.naturalWidth, h: img.naturalHeight })
  img.onerror = () => finish(null)
  setTimeout(() => finish(null), ms)
  img.src = url
})

export const createBox3D = (sdk) => {
  const { html, useState, useEffect, useRef } = sdk.ui

  /**
   * Resolve what we can actually build for this game.
   * → { mode: 'cuboid', faces, ratio } | { mode: 'flat', url } | { mode: 'cover' }
   */
  const usePlan = (systemId, filename, media) => {
    const [plan, setPlan] = useState({ mode: 'cover' })

    useEffect(() => {
      let cancelled = false
      if (!media || !sdk.api.media || !filename) { setPlan({ mode: 'cover' }); return }

      const url = (t) => sdk.api.media.url(systemId, filename, t)
      const has = (t) => !!media[t]

      // Start at the best thing that can be shown *now*, then climb. Starting
      // at the bottom and waiting to be upgraded is what made this look broken:
      // the pre-rendered box was already on disk, and the panel showed a flat
      // jacket instead while it waited on a face that was queued behind a
      // library-wide scrape.
      setPlan(has('box-3d') ? { mode: 'flat', url: url('box-3d') } : { mode: 'cover' })

      ;(async () => {
        // A cuboid needs a front and a spine: the spine is what gives the box
        // its depth, and without it there is nothing to turn towards.
        if (has('box-front') && has('box-spine')) {
          const [front, spine] = await Promise.all([
            measure(url('box-front')), measure(url('box-spine')),
          ])
          // Measured, not assumed: a DS case, a PS3 case and a PC big box have
          // nothing in common, and the proportions are what sell the illusion.
          if (!cancelled && front && spine && front.h > 0 && spine.h > 0) {
            // A spine is always a long thin strip: its long side runs along the
            // height of the box, its short side IS the depth. Which way round it
            // was stored is an accident of the source — the DS one is upright
            // (63x458), the N64 one is lying down (680x115). Reading the depth
            // as w/h believed the N64 box was six times deeper than it is tall,
            // and drew a black beam across the whole panel.
            const short = Math.min(spine.w, spine.h)
            const long = Math.max(spine.w, spine.h)
            setPlan({
              mode: 'cuboid',
              ratio: { front: front.w / front.h, depth: short / long },
              // Lying down, so the title has to be turned upright before it can
              // be painted on the side of the box.
              spineTurned: spine.w > spine.h,
              faces: {
                front: url('box-front'),
                spine: url('box-spine'),
                back: has('box-back') ? url('box-back') : null,
              },
            })
            return
          }
        }
        // Nothing better arrived; whatever was set above stands.
      })()

      return () => { cancelled = true }
    }, [systemId, filename, media])

    return plan
  }

  /** The cuboid itself. Owns its own animation frame. */
  const Cuboid = ({ plan, height }) => {
    const stage = useRef(null)
    const shadow = useRef(null)
    const pad = sdk.input.useGamepadState()

    // The stick, read on render but consumed in the loop — so the loop keeps
    // running smoothly between the hook's (quantised, sparse) updates.
    const input = useRef({ x: 0, y: 0 })
    input.current = {
      x: dead(pad.axes?.[2] ?? 0),
      y: dead(pad.axes?.[3] ?? 0),
    }

    useEffect(() => {
      const node = stage.current
      if (!node) return
      let raf = 0
      let yaw = 0, pitch = 0            // where the box is
      let lastTouch = 0                 // when the stick last said something
      const t0 = performance.now()

      const frame = (now) => {
        raf = requestAnimationFrame(frame)
        const { x, y } = input.current
        const active = x !== 0 || y !== 0
        if (active) lastTouch = now

        let tYaw, tPitch
        if (active || now - lastTouch < IDLE_RESUME) {
          // Under the player's hand — and for a moment after, so letting go
          // does not snap straight into the idle drift.
          tYaw = x * YAW_MAX
          tPitch = -y * PITCH_MAX
        } else if (now - t0 > IDLE_AFTER) {
          const phase = (now / IDLE_PERIOD) * Math.PI * 2
          tYaw = Math.sin(phase) * IDLE_YAW
          tPitch = Math.sin(phase * 0.5) * IDLE_PITCH
        } else {
          tYaw = 0; tPitch = 0
        }

        yaw += (tYaw - yaw) * SPRING
        pitch += (tPitch - pitch) * SPRING

        node.style.transform =
          `rotateX(${pitch.toFixed(2)}deg) rotateY(${yaw.toFixed(2)}deg)`
        // The light does not turn with the box, so the sheen slides across the
        // front as it rotates — a fixed highlight is what makes CSS 3D read as
        // flat cardboard.
        node.style.setProperty('--sheen', `${(50 - yaw * 0.9).toFixed(1)}%`)
        if (shadow.current) {
          const s = Math.cos(yaw * Math.PI / 180)
          shadow.current.style.transform =
            `translateX(${(yaw * 0.55).toFixed(1)}px) scaleX(${(0.72 + 0.28 * s).toFixed(3)})`
        }
      }
      raf = requestAnimationFrame(frame)
      return () => cancelAnimationFrame(raf)
    }, [plan])

    // Fit the box inside the slot rather than overflowing it: a wide case
    // (PC, Saturn) is wider than it is tall, and the panel has a fixed column.
    const maxW = 320
    let H = height
    let W = Math.round(H * plan.ratio.front)
    if (W > maxW) { H = Math.round(maxW / plan.ratio.front); W = maxW }
    // Clamped, and not only because of the N64. Two hundred and fifty systems
    // supply these images and nothing guarantees what shape they arrive in; a
    // box deeper than a third of its width does not exist, so anything past
    // that is a bad measurement rather than a fat case. Better a box slightly
    // too thin than a beam across the screen.
    const D = Math.max(8, Math.min(Math.round(H * plan.ratio.depth), Math.round(W * 0.34)))

    // Every face is centred on the box's own centre, then pushed out along its
    // own axis — that is the whole of a cuboid, and the only order that works.
    // Translating a face *before* rotating it (what this did at first) moves it
    // in the parent's frame, which is why the spine ended up adrift across the
    // panel instead of on the side of the box.
    const face = (w) => ({ width: `${w}px`, marginLeft: `${-w / 2}px` })
    // The caps are short, so they need centring on the other axis too. Left
    // anchored to the top of the stage, a cap pivots about its own middle
    // rather than the box's and flies off above it — which is exactly what it
    // did, as a white ribbon floating over the panel.
    const cap = (d) => ({ height: `${d}px`, top: '50%', marginTop: `${-d / 2}px` })

    return html`
      <div class="sm-box3d" style=${{ width: `${W}px`, height: `${H}px` }}>
        <div class="sm-box3d-stage" ref=${stage}>
          <div class="sm-box3d-face sm-box3d-front"
               style=${{ ...face(W), transform: `translateZ(${D / 2}px)`,
                         backgroundImage: `url("${plan.faces.front}")` }} />
          <div class="sm-box3d-face sm-box3d-back"
               style=${{ ...face(W), transform: `rotateY(180deg) translateZ(${D / 2}px)`,
                         backgroundImage: plan.faces.back ? `url("${plan.faces.back}")` : 'none' }} />
          <!-- The spine carries the title; the opposite edge is where the case
               opens, and no source photographs it. A plain edge in the art's own
               darkness is closer to the truth than a mirrored spine. -->
          <!-- The spine. When the source stored it lying down the artwork is
               turned upright inside the face rather than squashed into it: a
               child sized H x D, rotated a quarter turn, ends up covering
               exactly the D x H face. -->
          <div class="sm-box3d-face sm-box3d-spine"
               style=${{ ...face(D),
                         transform: `rotateY(-90deg) translateZ(${W / 2}px)`,
                         backgroundImage: plan.spineTurned ? 'none' : `url("${plan.faces.spine}")` }}>
            ${plan.spineTurned ? html`
              <div class="sm-box3d-spine-turned"
                   style=${{ width: `${H}px`, height: `${D}px`,
                             marginLeft: `${-H / 2}px`, marginTop: `${-D / 2}px`,
                             backgroundImage: `url("${plan.faces.spine}")` }} />` : null}
          </div>
          <div class="sm-box3d-face sm-box3d-edge"
               style=${{ ...face(D), transform: `rotateY(90deg) translateZ(${W / 2}px)` }} />
          <!-- Top and bottom. No source photographs them — box-texture is
               back | spine | front and nothing else — but the information is
               there all the same: the top of a case is the cut edge of the
               sleeve, so it *is* the top sliver of the front art. Taking it
               from the art gives a white DS case a white top and a black PS3
               case a black one, where both used to get the same grey.
               The CSS says background-size: 100% 2600%, which is how you ask
               for the outermost 1/26th of an image, stretched across the edge.
               (No backticks in here: this comment sits inside a template
               literal, and one backtick ends it — the rest of the markup then
               parses as JavaScript and the whole theme refuses to load.) -->
          <div class="sm-box3d-face sm-box3d-cap sm-box3d-cap-top"
               style=${{ ...face(W), ...cap(D),
                         backgroundImage: `url("${plan.faces.front}")`,
                         transform: `rotateX(90deg) translateZ(${H / 2}px)` }} />
          <div class="sm-box3d-face sm-box3d-cap sm-box3d-cap-bottom"
               style=${{ ...face(W), ...cap(D),
                         backgroundImage: `url("${plan.faces.front}")`,
                         transform: `rotateX(-90deg) translateZ(${H / 2}px)` }} />
        </div>
        <div class="sm-box3d-shadow" ref=${shadow} />
      </div>`
  }

  /**
   * @param media  the `media` map from api.media.list(), or null
   * @param Cover  the host's cover component, used as the last fallback
   */
  return ({ systemId, filename, media, color, Cover, height = 420 }) => {
    const plan = usePlan(systemId, filename, media)

    if (plan.mode === 'cuboid') return html`<${Cuboid} plan=${plan} height=${height} />`
    if (plan.mode === 'flat') {
      return html`<${Cover} filename=${filename} systemId=${systemId}
                            color=${color} type="box-3d" />`
    }
    return html`<${Cover} filename=${filename} systemId=${systemId} color=${color} />`
  }
}

/** True when this game can be turned — the hint bar asks before it says so. */
export const isTurnable = (media) => !!(media && media['box-front'] && media['box-spine'])
