// Fake pads for captures (legibility-audit.mjs --init). ?pads=ds4,xbox picks
// them; __press/__hold/__axes drive them from --eval; ?bg=1 fakes a suspended game.
(() => {
  const mk = (id, n = 17, axes = 4, mapping = 'standard') => ({
    id, mapping, connected: true, timestamp: 0,
    buttons: Array.from({ length: n }, () => ({ pressed: false, touched: false, value: 0 })),
    axes: Array.from({ length: axes }, () => 0),
  })
  // What the backend would say about each pad (GET /api/controllers/pads).
  const ROSTER = {
    ds4: { id: '84:30:95:07:c8:1c', name: 'PS4 Controller', vendor: '054c', product: '09cc', connection: 'Bluetooth', battery: 85, charging: true, known: 'sdl', controls: null, analogTriggers: true },
    xbox: { id: '045e:0b13', name: 'Xbox Wireless Controller', vendor: '045e', product: '0b13', connection: 'USB', battery: null, charging: false, known: 'sdl', controls: null, analogTriggers: true },
    stick: { id: '0f0d:0092', name: 'Hori Fighting Stick mini 4', vendor: '0f0d', product: '0092', connection: 'USB', battery: null, charging: false, known: 'table',
      controls: ['south', 'east', 'west', 'north', 'l1', 'r1', 'l2', 'r2', 'select', 'start', 'home', 'up', 'down', 'left', 'right'], analogTriggers: false },
    generic: { id: '0079:0006', name: 'USB Gamepad', vendor: '0079', product: '0006', connection: 'USB', battery: null, charging: false, known: 'unknown', controls: null, analogTriggers: true },
  }
  let names = []
  const realFetch = window.fetch.bind(window)
  // ?bg=1: a game suspended in the background, so the power menu leads with it.
  const BG = new URLSearchParams(location.search).get('bg') === '1'
  // The socket announces the (empty) dev session on connect; drop that one
  // event so the stubbed answer to /api/games/session stands.
  if (BG) {
    const Real = window.WebSocket
    window.WebSocket = class extends Real {
      set onmessage(fn) {
        super.onmessage = (e) => { try { if (/^session:|^game:/.test(JSON.parse(e.data).event)) return } catch {} fn(e) }
      }
    }
  }
  const json = (o) => Promise.resolve(new Response(JSON.stringify(o)))
  window.fetch = (url, init) => {
    const u = String(url)
    if (u.endsWith('/api/controllers/pads')) return json({ pads: names.map((n, i) => ({ player: i + 1, kernelName: '', ...ROSTER[n] })) })
    if (BG && u.endsWith('/api/games/session')) return json({ background: [{ game_key: 'Mario Kart 7 (Europe).3ds', system_id: 'azahar', session: 1, state: 'background', kind: 'game' }] })
    return realFetch(url, init)
  }
  const PADS = {
    ds4: () => mk('Wireless Controller (STANDARD GAMEPAD Vendor: 054c Product: 09cc)'),
    xbox: () => mk('Xbox Wireless Controller (STANDARD GAMEPAD Vendor: 045e Product: 0b13)'),
    stick: () => mk('Fighting Stick mini 4 (STANDARD GAMEPAD Vendor: 0f0d Product: 0092)'),
    generic: () => mk('USB Gamepad (Vendor: 0079 Product: 0006)', 12, 2, ''),
  }
  let pads = []
  window.__setPads = (...ns) => { names = ns; pads = ns.map((n, i) => Object.assign(PADS[n](), { index: i })) }
  window.__press = (btn, ms = 120, pad = 0) => {
    const b = pads[pad].buttons[btn]; b.pressed = true; b.value = 1; pads[pad].timestamp++
    setTimeout(() => { b.pressed = false; b.value = 0; pads[pad].timestamp++ }, ms)
  }
  window.__hold = (btn, value = 1, pad = 0) => {
    const b = pads[pad].buttons[btn]; b.pressed = value > 0.1; b.value = value; pads[pad].timestamp++
  }
  window.__axes = (a, pad = 0) => { pads[pad].axes = a; pads[pad].timestamp++ }
  navigator.getGamepads = () => { const out = [null, null, null, null]; pads.forEach((p, i) => { out[i] = p }); return out }
  const s = new URLSearchParams(location.search).get('pads')
  if (s) window.__setPads(...s.split(','))
})()
