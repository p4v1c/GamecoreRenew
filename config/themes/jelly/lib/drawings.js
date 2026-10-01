/** Jelly's illustrations, drawn in SVG so they cost no download and scale to
 * any TV. Only shapes and colours: no character, no brand art. */

/** The jelly race track behind the Play card, with two karts going round. */
export const track = () => `<svg viewBox="0 0 430 300" preserveAspectRatio="xMidYMid slice">
<defs><pattern id="jl-dots" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.3" fill="#ffffff18"/></pattern></defs>
<rect width="430" height="300" fill="url(#jl-dots)"/>
<g transform="translate(20 15) rotate(-20 210 140)">
<ellipse cx="235" cy="238" rx="165" ry="27" fill="#382159" opacity=".25"/>
<path d="M100 205V90q0-40 50-40h145q53 0 53 52v54q0 49-53 49z" fill="none" stroke="#382159" stroke-width="72" transform="translate(0 13)"/>
<path d="M100 205V90q0-40 50-40h145q53 0 53 52v54q0 49-53 49z" fill="none" stroke="#6edced" stroke-width="72"/>
<path d="M100 205V90q0-40 50-40h145q53 0 53 52v54q0 49-53 49z" fill="none" stroke="#b4f4f2" stroke-width="3" stroke-dasharray="12 10"/>
<path d="m164 162 23 23-23 23m31-46 23 23-23 23" fill="none" stroke="#fffdf7" stroke-width="9" stroke-linejoin="round"/>
<g class="jl-kart"><rect x="-12" y="-4" width="26" height="34" rx="8" fill="#35244c"/><rect x="-12" y="-10" width="26" height="34" rx="8" fill="#ffe66b"/><rect x="-8" y="-5" width="18" height="12" rx="4" fill="#fff9d5"/></g>
<g class="jl-kart jl-kart-two"><rect x="-12" y="-10" width="26" height="34" rx="8" fill="#f950a3"/><rect x="-8" y="-5" width="18" height="12" rx="4" fill="#ffd2e9"/></g>
<path d="M93 150V89" stroke="#ffedf8" stroke-width="5"/><path class="jl-flag" d="M96 89h40l-8 13 8 13H96" fill="#ff64af"/>
</g>
<circle class="jl-bubble" cx="55" cy="70" r="10" fill="#ffe66b"/>
<path class="jl-star" d="m378 212 5 11 12 2-9 8 2 12-10-6-11 6 2-12-9-8 12-2Z" fill="#ff8fc6"/>
<rect x="70" y="253" width="16" height="9" rx="4" transform="rotate(-30 70 253)" fill="#ff9cce"/>
</svg>`

/** The wobbling wave used on the playground and the splash. */
export const wave = () => `<svg viewBox="0 0 100 50"><path d="M5 30q12-25 24 0t24 0 24 0 24 0" fill="none" stroke="currentColor" stroke-width="9" stroke-linecap="round"/></svg>`

/** The GameCore mark: a lowercase g with a small c, as a tilted jelly tile. */
export const mark = () => `<svg viewBox="0 0 48 48" aria-hidden="true">
<rect x="4" y="6" width="40" height="38" rx="13" fill="#2a1a44" transform="rotate(-8 24 24)"/>
<rect x="4" y="3" width="40" height="38" rx="13" fill="#30204e" transform="rotate(-8 24 22)"/>
<text x="20" y="31" text-anchor="middle" font-size="25" font-weight="900" fill="#fff" font-family="inherit">g</text>
<text x="33" y="36" text-anchor="middle" font-size="14" font-weight="900" fill="#ffe66b" font-family="inherit">c</text>
</svg>`
