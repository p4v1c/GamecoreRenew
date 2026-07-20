// TV-safe area.
//
// The UI renders at a fixed 1920x1080 (see electron/main.js) and is shown
// pixel-for-pixel on a PC monitor. Over HDMI, many TVs still apply overscan
// by default (Samsung's "Screen Fit" / "16:9" picture size setting is the
// common culprit) and crop a few percent off every edge of the signal —
// invisible on a monitor, but it eats into anything sitting flush against
// the true canvas border (e.g. the Power button in the top-right corner).
//
// These constants keep interactive/text content clear of the raw edges so
// it survives a moderate overscan crop without the box requiring a "Just
// Scan" / "Screen Fit" change on every TV. Purely decorative full-bleed
// layers (Screensaver background, Splash) don't need this — only their own
// text/UI does.
export const SAFE_AREA_X = 40 // ~2.1% of 1920
export const SAFE_AREA_Y = 28 // ~2.6% of 1080
