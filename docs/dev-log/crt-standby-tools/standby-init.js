// Dev only, for legibility-audit.mjs --init: the box reports the screensaver
// stage, so the CRT standby mounts (devserve cannot enter standby itself).
(() => {
  const real = window.fetch.bind(window)
  window.fetch = (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href)
    if (url.pathname === '/api/standby') {
      return Promise.resolve(new Response(JSON.stringify(
        {state: 'screensaver', enabled: true, screensaver_mins: 10, sleep_mins: 20}),
        {headers: {'content-type': 'application/json'}}))
    }
    return real(input, init)
  }
})()
