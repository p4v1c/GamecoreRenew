/**
 * Summer — the ocean renderer.
 *
 * Ported from the design mockup, which drew it in a single fullscreen fragment
 * shader: sky, swell, breaking crests, foam, wet sand and grass are all
 * procedural, so there is no texture to ship and the camera never moves.
 *
 * Two deliberate deviations from DESIGN-BRIEF.md, both listed in the theme's
 * README:
 *   - no geo-IP lookup. The brief resolves latitude/longitude over the network;
 *     a theme making an outbound call at boot is a decision for the box owner,
 *     not for a stylesheet. Location is a constant here, overridable below.
 *   - solar events use the mockup's compact formulas rather than full NOAA.
 *     Within a few minutes at usable latitudes, and no network either way.
 */

// Change these two if the light should track your actual sky.
export const LOCATION = { lat: 48.86, lon: 2.35 }

export const TOD = {
  dawn:{skyTop:'#5E6FA8',skyMid:'#B98BA6',skyLow:'#F6B896',seaDeep:'#33607F',seaShallow:'#79A7B8',foam:'#FFF1E6',sandNear:'#E4C39B',sandWet:'#C0A183',grass:'#4E7A55',disc:'#FFE1B8',glow:[1.0,0.745,0.549,0.45],ambient:[0.47,0.353,0.588,0.14],energy:0.85,elev:4,azim:-62,accent:'#F0761E',glyph:'☀',night:0},
  noon:{skyTop:'#2E86C8',skyMid:'#7EC0E8',skyLow:'#CDEBF7',seaDeep:'#0E6E92',seaShallow:'#3FB4C6',foam:'#FFFFFF',sandNear:'#F4DCB4',sandWet:'#D9C29B',grass:'#57904F',disc:'#FFFDF0',glow:[1,1,0.92,0.38],ambient:[1,1,1,0],energy:1.0,elev:78,azim:0,accent:'#F0761E',glyph:'☀',night:0},
  afternoon:{skyTop:'#3E93C6',skyMid:'#8FC9E4',skyLow:'#E4EFF2',seaDeep:'#12718C',seaShallow:'#4FBAC2',foam:'#FDFBF4',sandNear:'#EFD3A4',sandWet:'#D3B78B',grass:'#4E8449',disc:'#FFF3D2',glow:[1,0.92,0.745,0.34],ambient:[1,0.784,0.47,0.08],energy:1.15,elev:40,azim:38,accent:'#F0761E',glyph:'☀',night:0},
  sunset:{skyTop:'#6E3F86',skyMid:'#E2743C',skyLow:'#FBC06A',seaDeep:'#2A4C77',seaShallow:'#C98A55',foam:'#FFE3C2',sandNear:'#C98F4F',sandWet:'#A9713C',grass:'#5B4A2C',disc:'#FF9A3C',glow:[1,0.549,0.196,0.52],ambient:[0.784,0.353,0.118,0.16],energy:0.95,elev:2,azim:74,accent:'#F0761E',glyph:'☾',night:0},
  night:{skyTop:'#0B1436',skyMid:'#152352',skyLow:'#22315F',seaDeep:'#0A1730',seaShallow:'#1B2C4C',foam:'#B9C7DA',sandNear:'#33405A',sandWet:'#243350',grass:'#1D3040',disc:'#E8EEFF',glow:[0.823,0.882,1,0.26],ambient:[0.039,0.078,0.196,0.34],energy:0.70,elev:32,azim:50,accent:'#FE9D7C',glyph:'☾',night:1}
};
export const ORDER = ['dawn','noon','afternoon','sunset','night'];

function lerp(a,b,t){return a+(b-a)*t;}
function lerpArr(a,b,t){return a.map((v,i)=>lerp(v,b[i],t));}
function pad2(n){return n<10?'0'+n:''+n;}
function shade(hex,f){
  const r=Math.min(255,Math.round(parseInt(hex.slice(1,3),16)*f));
  const g=Math.min(255,Math.round(parseInt(hex.slice(3,5),16)*f));
  const b=Math.min(255,Math.round(parseInt(hex.slice(5,7),16)*f));
  return 'rgb('+r+','+g+','+b+')';
}

const VS = 'attribute vec2 p;varying vec2 vUv;void main(){vUv=p*0.5+0.5;gl_Position=vec4(p,0.0,1.0);}';
const FS=[
'precision highp float;varying vec2 vUv;',
'uniform float uT,uEnergy,uNight,uAspect;',
'uniform vec3 uSkyTop,uSkyMid,uSkyLow,uSeaDeep,uSeaShallow,uFoam,uSandNear,uSandWet,uDisc,uSun;',
'uniform vec4 uGlow,uAmbient;',
'float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}',
'float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);float a=hash(i),b=hash(i+vec2(1.0,0.0)),c=hash(i+vec2(0.0,1.0)),d=hash(i+vec2(1.0,1.0));return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);}',
'float fbm(vec2 p){return vn(p)*0.62+vn(p*2.13+7.3)*0.38;}',
'float waves(vec2 pos,float shoal,float hf,out vec2 grad){',
' float amps[6];float lens[6];float dirs[6];float sps[6];',
' amps[0]=0.95;amps[1]=0.58;amps[2]=0.30;amps[3]=0.14;amps[4]=0.05;amps[5]=0.02;',
' lens[0]=26.0;lens[1]=17.0;lens[2]=11.0;lens[3]=6.5;lens[4]=3.4;lens[5]=1.8;',
' dirs[0]=-0.14;dirs[1]=0.19;dirs[2]=-0.38;dirs[3]=0.45;dirs[4]=-0.72;dirs[5]=0.84;',
' sps[0]=6.4;sps[1]=5.1;sps[2]=3.8;sps[3]=2.9;sps[4]=2.0;sps[5]=1.4;',
' float h=0.0;grad=vec2(0.0);',
' for(int i=0;i<6;i++){',
'  float a=amps[i]*uEnergy*shoal*mix(1.0,hf,float(i)/5.0);float L=mix(lens[i]*0.6,lens[i],shoal);float k=6.28318/L;',
'  vec2 d=vec2(sin(dirs[i]),-cos(dirs[i]));float ph=dot(d,pos)*k+uT*sps[i]*k*0.16;',
'  h+=a*sin(ph);grad+=a*k*d*cos(ph);',
' } return h;}',
'vec3 sky(vec3 d){',
' float y=clamp(d.y,-0.2,1.0);',
' vec3 c=mix(uSkyLow,uSkyMid,smoothstep(0.0,0.22,y));',
' c=mix(c,uSkyTop,smoothstep(0.16,0.72,y));',
' float sd=max(dot(normalize(d),uSun),0.0);',
' c+=uGlow.rgb*uGlow.a*pow(sd,10.0)*1.1;',
' c+=uGlow.rgb*uGlow.a*0.5*pow(sd,120.0);',
' float ang=acos(clamp(sd,-1.0,1.0));',
' float r=mix(0.026,0.020,uNight);',
' float disc=1.0-smoothstep(r*0.86,r,ang);',
' if(uNight>0.5){vec3 off=normalize(uSun+vec3(0.030,0.016,0.0));float m=1.0-smoothstep(r*0.86,r,acos(clamp(dot(normalize(d),off),-1.0,1.0)));disc=clamp(disc-m,0.0,1.0);}',
' c=mix(c,uDisc,disc);',
' float cl=fbm(vec2(d.x/max(d.y,0.06)*0.9+uT*0.012,d.z/max(d.y,0.06)*0.9));',
' float cm=smoothstep(0.52,0.86,cl)*smoothstep(0.02,0.30,d.y)*0.78;',
' c=mix(c,mix(vec3(1.0),uSkyLow,0.25)*mix(1.0,0.35,uNight),cm);',
' return c;}',
'void main(){',
' vec2 uv=vUv*2.0-1.0;uv.x*=uAspect;',
' vec3 eye=vec3(0.0,7.0,10.0);vec3 fwd=normalize(vec3(0.0,0.0,-70.0)-eye);',
' vec3 rgt=normalize(cross(vec3(0.0,1.0,0.0),fwd));vec3 up=cross(fwd,rgt);',
' float f=1.0/tan(radians(19.0));',
' vec3 dir=normalize(fwd*f+rgt*uv.x+up*uv.y);',
' vec3 col;',
' if(dir.y>-0.002){col=sky(dir);}else{',
'  float t=-eye.y/dir.y;vec3 p=eye+dir*t;float zf=-p.z;',
'  float edge=27.0+2.6*sin(uT*0.22)+1.5*sin(uT*0.13+1.7)+6.5*fbm(vec2(p.x*0.028,uT*0.045))+2.6*fbm(vec2(p.x*0.11,uT*0.085+3.1));',
'  if(zf<edge){',
'   float back=edge-zf;',
'   float wet=exp(-back/4.5);',
'   vec3 s=mix(uSandNear,uSandWet,clamp(wet*1.2,0.0,1.0));',
'   float rip=sin(back*1.15+fbm(vec2(p.x*0.10,p.z*0.05))*3.2)*0.5+0.5;',
'   s*=0.93+0.14*rip*smoothstep(1.5,9.0,back)*exp(-back/26.0);',
'   float dune=fbm(vec2(p.x*0.05,p.z*0.07));',
'   s*=0.92+0.16*dune;',
'   float damp=smoothstep(0.55,0.85,fbm(vec2(p.x*0.16,p.z*0.2)))*smoothstep(14.0,2.0,back);',
'   s*=1.0-0.10*damp;',
'   float gsc=mix(30.0,7.0,smoothstep(0.0,26.0,zf));',
'   float gr=hash(floor(p.xz*gsc));',
'   float gr2=hash(floor(p.xz*gsc*2.7)+31.7);',
'   s*=1.0+((gr-0.5)*0.13+(gr2-0.5)*0.07)*exp(-zf/34.0);',
'   float drain=smoothstep(0.58,0.96,fbm(vec2(p.x*1.05,back*0.13)));',
'   s*=1.0-drain*wet*0.16;',
'   vec3 up=normalize(vec3(0.012*sin(p.x*0.7+uT*0.3),1.0,0.012*sin(back*0.9)));',
'   vec3 wr=reflect(dir,up);',
'   float sheen=pow(max(dot(wr,uSun),0.0),16.0)*wet;',
'   float col2=0.55+0.45*fbm(vec2(p.x*1.6,back*0.3+uT*0.3));',
'   s+=uDisc*sheen*col2*1.15;',
'   s=mix(s,mix(s,sky(wr),0.30),wet);',
'   float sw=sin(back*0.8+fbm(vec2(p.x*0.07,0.0))*5.0);',
'   s*=1.0+0.055*smoothstep(0.55,1.0,sw)*smoothstep(2.5,13.0,back);',
'   float fe=fbm(vec2(p.x*0.26+uT*0.18,uT*0.42));',
'   float fw=3.6+4.4*fe;',
'   float band=1.0-smoothstep(0.0,fw,back);',
'   float lace=fbm(vec2(p.x*0.85,p.z*0.75+uT*0.6))*0.65+fbm(vec2(p.x*2.4,p.z*2.1+uT*1.1))*0.35;',
'   float bub=step(0.72,hash(floor(p.xz*vec2(13.0,19.0))+floor(uT*3.0)));',
'   float fm=band*smoothstep(0.22,0.78,lace+0.30*band)+band*bub*0.45;',
'   fm+=(1.0-smoothstep(0.0,1.4,back))*0.85;',
'   float swash=(1.0-smoothstep(1.2,3.4,abs(back-fw-3.2-2.0*fe)))*smoothstep(0.42,0.8,lace)*0.35;',
'   col=mix(s,uFoam,clamp(fm+swash,0.0,0.96));',
'  }else{',
'   vec2 grad;float shoal=smoothstep(0.0,26.0,zf-edge);float hf=exp(-zf/150.0);',
'   for(int i=0;i<4;i++){float hh=waves(p.xz,shoal,hf,grad);t=(hh-eye.y)/dir.y;p=eye+dir*t;zf=-p.z;shoal=smoothstep(0.0,26.0,zf-edge);hf=exp(-zf/150.0);}',
'   float h=waves(p.xz,shoal,hf,grad);',
'   vec3 n=normalize(vec3(-grad.x,1.0,-grad.y));',
'   vec3 v=-dir;float fr=pow(1.0-max(dot(n,v),0.0),5.0);fr=mix(0.02,0.85,fr);',
'   vec3 refl=reflect(dir,n);refl.y=abs(refl.y);',
'   vec3 deep=mix(uSeaShallow,uSeaDeep,smoothstep(0.0,70.0,zf-edge));',
'   deep+=uSeaShallow*clamp(h,0.0,1.5)*0.35;',
'   deep*=1.0+0.10*clamp(-grad.y*2.0,-0.4,0.4);',
'   vec3 rf=mix(uSeaShallow,sky(refl),0.65);',
'   col=mix(deep,rf,clamp(fr*0.55,0.0,1.0));',
'   float sp=pow(max(dot(refl,uSun),0.0),190.0);',
'   col+=uDisc*sp*mix(1.4,0.7,uNight);',
'   float glit=pow(max(dot(refl,uSun),0.0),22.0)*0.24*exp(-max(zf-edge,0.0)/120.0);',
'   col+=uDisc*glit*(0.4+0.6*fbm(p.xz*1.1+uT*0.4));',
'   float crest=smoothstep(0.46,0.98,h/max(0.95*uEnergy,0.01));',
'   float cf=crest*smoothstep(0.36,0.84,fbm(p.xz*0.55+vec2(uT*0.5,0.0)))*exp(-max(zf-edge,0.0)/150.0);',
'   float sw2=zf-edge;',
'   float brk=0.0;',
'   for(int b=0;b<4;b++){',
'    float ph=fract(uT*0.055+float(b)*0.25);',
'    float ease=1.0-pow(1.0-ph,1.7);',
'    float bd=mix(96.0,0.0,ease)+2.4*fbm(vec2(p.x*0.03,float(b)*3.7));',
'    float dst=sw2-bd;',
'    float born=smoothstep(0.0,0.16,ph);',
'    float die=smoothstep(1.0,0.82,ph);',
'    float grow=0.45+0.75*smoothstep(70.0,10.0,bd);',
'    float cw=(1.4+2.6*smoothstep(80.0,8.0,bd))+1.6*fbm(vec2(p.x*0.3+uT*0.2,float(b)));',
'    float crest=1.0-smoothstep(0.0,cw,abs(dst));',
'    float tail=(1.0-smoothstep(0.0,9.0,max(-dst,0.0)))*0.32;',
'    float tex=smoothstep(0.25,0.8,fbm(vec2(p.x*0.6,dst*0.7+uT*0.4)));',
'    brk=max(brk,(crest*(0.55+0.55*tex)+tail*tex)*born*die*grow*smoothstep(430.0,150.0,zf));',
'   }',
'   float sfw=5.0+4.5*fbm(vec2(p.x*0.33+uT*0.2,uT*0.5));',
'   float sf=(1.0-smoothstep(0.0,sfw,sw2))*smoothstep(0.18,0.62,fbm(vec2(p.x*0.55+uT*0.3,p.z*0.5+uT*0.45)));',
'   sf=max(sf,(1.0-smoothstep(0.0,1.2,sw2))*0.85);',
'   col=mix(col,uFoam,clamp(max(max(cf*0.70,brk*0.95),sf*0.92),0.0,0.95));',
'   col*=mix(0.90,1.0,smoothstep(0.0,140.0,zf));',
'   float far=smoothstep(110.0,480.0,zf);',
'   col=mix(col,mix(uSeaDeep,uSkyLow,0.42),far*0.88);',
'  }',
' }',
' col=mix(col,col*uAmbient.rgb,uAmbient.a);',
' float d=length((vUv-vec2(0.5,0.6))*vec2(1.05,1.25));',
' col=mix(col,vec3(0.031,0.063,0.086),smoothstep(0.34,0.92,d)*0.42);',
' gl_FragColor=vec4(pow(clamp(col,0.0,1.0),vec3(0.94)),1.0);',
'}'].join('\n');

// ── helpers the draw call needs ───────────────────────────────────────────────
const hex2rgb = (h) => new Float32Array([
  parseInt(h.slice(1, 3), 16) / 255,
  parseInt(h.slice(3, 5), 16) / 255,
  parseInt(h.slice(5, 7), 16) / 255,
])

/** Sun/twilight times for today, in local decimal hours. No network. */
export function solarEvents(geo = LOCATION) {
  const now = new Date()
  const doy = Math.floor((now - new Date(now.getFullYear(), 0, 0)) / 864e5)
  const decl = -23.44 * Math.cos(2 * Math.PI / 365 * (doy + 10)) * Math.PI / 180
  const latR = geo.lat * Math.PI / 180
  const eqt = -7.66 * Math.sin(2 * Math.PI / 365 * (doy - 3))
            - 9.87 * Math.sin(4 * Math.PI / 365 * (doy - 81))
  const noon = 12 - geo.lon / 15 - eqt / 60 + (-now.getTimezoneOffset() / 60)
  const ha = (z) => {
    const c = (Math.cos(z * Math.PI / 180) - Math.sin(latR) * Math.sin(decl))
            / (Math.cos(latR) * Math.cos(decl))
    return (c > 1 || c < -1) ? null : Math.acos(c) * 180 / Math.PI / 15
  }
  const h0 = ha(90.833), h6 = ha(96)
  return {
    noon,
    sunrise: h0 === null ? null : noon - h0,
    sunset:  h0 === null ? null : noon + h0,
    dawn:    h6 === null ? null : noon - h6,
    dusk:    h6 === null ? null : noon + h6,
    // Polar day/night: no sunrise at all, so the state is clamped.
    polarDay: Math.sin(latR) * Math.sin(decl) > 0,
  }
}

/** Which solar state we are in, and how far through its final crossfade. */
export function currentTod(geo = LOCATION) {
  const e = solarEvents(geo)
  const d = new Date(), h = d.getHours() + d.getMinutes() / 60
  if (e.sunrise === null) return { tod: e.polarDay ? 'noon' : 'night', t: 0 }
  const win = [
    ['dawn', e.dawn, e.sunrise + 0.75],
    ['noon', e.sunrise + 0.75, e.noon + 1.5],
    ['afternoon', e.noon + 1.5, e.sunset - 1],
    ['sunset', e.sunset - 1, e.dusk],
  ]
  for (const w of win) {
    if (h >= w[1] && h < w[2]) {
      const t = (h - w[1]) / (w[2] - w[1])
      // Only the last 12% of a window blends into the next state.
      return { tod: w[0], t: t > 0.88 ? (t - 0.88) / 0.12 : 0 }
    }
  }
  return { tod: 'night', t: 0 }
}

/** Interpolated token set for right now. */
export function todColors(geo = LOCATION) {
  const { tod, t } = currentTod(geo)
  const a = TOD[tod] || TOD.noon
  if (t <= 0) return a
  const b = TOD[ORDER[(ORDER.indexOf(tod) + 1) % 5]]
  const m = {}
  for (const k in a) {
    if (k === 'glow' || k === 'ambient') m[k] = lerpArr(a[k], b[k], t)
    else if (typeof a[k] === 'number') m[k] = lerp(a[k], b[k], t)
    else m[k] = t > 0.5 ? b[k] : a[k]
  }
  return m
}

/**
 * Mount the ocean on a canvas.
 *
 * Returns { stop, setPaused, colors }. The caller owns when it runs — the theme
 * pauses it while a game is running and during standby, per the performance
 * rules in docs/themes/README.md §11.
 */
export function createOcean(canvas, opts = {}) {
  const geo = opts.location || LOCATION
  const gl = canvas.getContext('webgl', {
    antialias: false, alpha: false, powerPreference: 'low-power',
  })
  if (!gl) return null

  const mk = (ty, src) => {
    const sh = gl.createShader(ty)
    gl.shaderSource(sh, src); gl.compileShader(sh)
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      console.warn('[summer] shader:', gl.getShaderInfoLog(sh)); return null
    }
    return sh
  }
  const vs = mk(gl.VERTEX_SHADER, VS), fs = mk(gl.FRAGMENT_SHADER, FS)
  if (!vs || !fs) return null

  const pr = gl.createProgram()
  gl.attachShader(pr, vs); gl.attachShader(pr, fs); gl.linkProgram(pr)
  if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) {
    console.warn('[summer] link:', gl.getProgramInfoLog(pr)); return null
  }
  gl.useProgram(pr)

  const buf = gl.createBuffer()
  gl.bindBuffer(gl.ARRAY_BUFFER, buf)
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
  const loc = gl.getAttribLocation(pr, 'p')
  gl.enableVertexAttribArray(loc)
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)

  const u = {}
  for (const n of ['uT', 'uEnergy', 'uNight', 'uAspect', 'uSkyTop', 'uSkyMid', 'uSkyLow',
                   'uSeaDeep', 'uSeaShallow', 'uFoam', 'uSandNear', 'uSandWet', 'uDisc',
                   'uGlow', 'uAmbient', 'uSun']) u[n] = gl.getUniformLocation(pr, n)

  let scale = 1
  const setRes = () => {
    canvas.width = Math.round(1920 * scale)
    canvas.height = Math.round(1080 * scale)
    gl.viewport(0, 0, canvas.width, canvas.height)
  }
  setRes()

  const t0 = performance.now()
  let raf = 0, last = 0, paused = false, slow = 0, tier = 0, dead = false

  const draw = (secs) => {
    const c = todColors(geo)
    gl.uniform1f(u.uT, secs)
    gl.uniform1f(u.uEnergy, c.energy * (opts.waveEnergy ?? 1))
    gl.uniform1f(u.uNight, c.night)
    gl.uniform1f(u.uAspect, 1920 / 1080)
    gl.uniform3fv(u.uSkyTop, hex2rgb(c.skyTop));   gl.uniform3fv(u.uSkyMid, hex2rgb(c.skyMid))
    gl.uniform3fv(u.uSkyLow, hex2rgb(c.skyLow));   gl.uniform3fv(u.uSeaDeep, hex2rgb(c.seaDeep))
    gl.uniform3fv(u.uSeaShallow, hex2rgb(c.seaShallow)); gl.uniform3fv(u.uFoam, hex2rgb(c.foam))
    gl.uniform3fv(u.uSandNear, hex2rgb(c.sandNear)); gl.uniform3fv(u.uSandWet, hex2rgb(c.sandWet))
    gl.uniform3fv(u.uDisc, hex2rgb(c.disc))
    gl.uniform4fv(u.uGlow, new Float32Array(c.glow))
    gl.uniform4fv(u.uAmbient, new Float32Array(c.ambient))
    const el = c.elev * Math.PI / 180, az = c.azim * Math.PI / 180
    gl.uniform3fv(u.uSun, new Float32Array([
      Math.sin(az) * Math.cos(el), Math.sin(el), -Math.cos(az) * Math.cos(el),
    ]))
    gl.drawArrays(gl.TRIANGLES, 0, 3)
  }

  const tick = (now) => {
    if (dead) return
    raf = requestAnimationFrame(tick)
    // Paused: hold the last frame. The sea is still there, it just stops
    // costing anything while a game owns the machine.
    if (paused) return
    if (last && now - last < 33.3) return          // 30 fps cap
    const dt = last ? now - last : 0
    last = now
    const start = performance.now()
    draw((now - t0) / 1000)
    // Two strikes and the render scale drops. A launcher must never be the
    // reason a box feels slow.
    if (tier < 2 && opts.autoQuality !== false) {
      const cost = performance.now() - start
      if (dt > 60 || cost > 28) slow++; else slow = Math.max(0, slow - 2)
      if (slow > 150) { slow = 0; tier++; scale = tier === 1 ? 0.75 : 0.55; setRes() }
    }
  }
  raf = requestAnimationFrame(tick)

  return {
    setPaused: (v) => { paused = !!v; if (!v) last = 0 },
    stop: () => { dead = true; cancelAnimationFrame(raf) },
  }
}
