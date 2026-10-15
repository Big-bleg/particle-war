SHAPE_VS = """
#version 330
uniform vec2 uScreen;
uniform float uScale;
in vec2 in_corner;
in vec4 a; in vec4 b; in vec4 c;
out vec2 vLocal; out float vLen; out vec4 vB; out vec4 vC; out vec2 vBox;
void main(){
  vec2 p0 = a.xy, p1 = a.zw; float r = b.x, soft = b.y; int kind = int(b.z + .5);
  vec2 pos;
  vB = b; vC = c;
  if (kind >= 5) {                         // box kinds: a = (x0,y0,x1,y1)
    vec2 lo = min(p0,p1) - soft - 2.0, hi = max(p0,p1) + soft + 2.0;
    vec2 t = in_corner * .5 + .5;
    pos = mix(lo, hi, t);
    vLocal = pos - (p0 + p1) * .5; vBox = abs(p1 - p0) * .5; vLen = (pos.y - min(p0.y,p1.y)) / max(1.0, abs(p1.y - p0.y));
  } else {
    vec2 d = p1 - p0; float L = length(d); vec2 dir = L > 1e-4 ? d / L : vec2(1.0, 0.0); vec2 nrm = vec2(-dir.y, dir.x);
    float pad = r + soft + 2.0;
    float u = in_corner.x < 0.0 ? -pad : L + pad; float v = in_corner.y * pad;
    pos = p0 + dir * u + nrm * v;
    vLocal = vec2(u, v); vLen = L; vBox = vec2(0.0);
  }
  pos *= uScale;
  gl_Position = vec4(pos.x / uScreen.x * 2.0 - 1.0, 1.0 - pos.y / uScreen.y * 2.0, 0.0, 1.0);
}
"""

SHAPE_FS = """
#version 330
in vec2 vLocal; in float vLen; in vec4 vB; in vec4 vC; in vec2 vBox;
out vec4 frag;
uniform float uScale;
void main(){
  float r = vB.x, soft = max(vB.y, 0.0); int kind = int(vB.z + .5); float p = vB.w;
  float aa = 0.75 / uScale;
  vec4 col = vC; float alpha = 0.0;
  if (kind >= 5) {
    vec2 q = abs(vLocal) - vBox + r; float d = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
    if (kind == 5) alpha = 1.0 - smoothstep(-aa - soft, aa, d);                       // rounded box
    else if (kind == 6) { alpha = 1.0 - smoothstep(-aa, aa, d); col.rgb *= mix(1.0, p, clamp(vLen, 0.0, 1.0)); }  // vertical gradient box
    else if (kind == 7) alpha = 1.0 - smoothstep(0.0, aa * 2.0, abs(d + p * .5) - p * .5);   // box outline (p = width)
  } else {
    float t = clamp(vLocal.x, 0.0, vLen);
    vec2 cp = vec2(vLocal.x - t, vLocal.y); float d = length(cp);
    if (kind == 0) alpha = 1.0 - smoothstep(r - aa - soft, r + aa, d);                // capsule / disc
    else if (kind == 1) alpha = 1.0 - smoothstep(p * .5 - aa, p * .5 + aa + soft, abs(d - r)); // ring
    else if (kind == 2) { float x = d / max(r, 1e-3); alpha = exp(-x * x * 3.0) * step(x, 1.6); }   // soft glow
    else if (kind == 3) {                                                             // shaded sphere
      vec2 n = cp / max(r, 1e-3);
      float l = clamp(1.0 - length(n - vec2(-.35, -.42)) * .85, 0.0, 1.0);
      col.rgb = col.rgb * (.45 + .75 * l) + vec3(1.0) * pow(l, 6.0) * .55;
      col.rgb = mix(col.rgb, col.rgb * .55, smoothstep(.75, 1.0, length(n)));
      alpha = 1.0 - smoothstep(r - aa, r + aa, d);
    } else if (kind == 4) {                                                           // tapered streak tail->head
      float f = vLen > 0.0 ? clamp(vLocal.x / vLen, 0.0, 1.0) : 1.0;
      float w = r * (.25 + .75 * f);
      alpha = (1.0 - smoothstep(w - aa, w + aa, d)) * (f * f);
    }
  }
  frag = vec4(col.rgb, col.a * alpha);
}
"""

TEXT_VS = """
#version 330
uniform vec2 uScreen;
in vec2 in_corner;
in vec4 rect; in vec4 uv; in vec4 col; in vec4 ocol;
out vec2 vUV; out vec4 vCol; out vec4 vO;
void main(){
  vec2 t = in_corner * .5 + .5;
  vec2 pos = rect.xy - 2.0 + (rect.zw + 4.0) * t;
  vec2 texel = (uv.zw - uv.xy) / rect.zw;
  vUV = uv.xy + (pos - rect.xy) * texel;
  vCol = col; vO = ocol;
  gl_Position = vec4(pos.x / uScreen.x * 2.0 - 1.0, 1.0 - pos.y / uScreen.y * 2.0, 0.0, 1.0);
}
"""

TEXT_FS = """
#version 330
uniform sampler2D uAtlas;
uniform vec2 uTexel;
in vec2 vUV; in vec4 vCol; in vec4 vO;
out vec4 frag;
void main(){
  float a = texture(uAtlas, vUV).r;
  float o = 0.0;
  if (vO.a > 0.0) {
    for (int i = 0; i < 12; i++) { float an = float(i) * 0.5236; o = max(o, texture(uAtlas, vUV + vec2(cos(an), sin(an)) * uTexel * 1.6).r); }
  }
  vec3 rgb = mix(vO.rgb, vCol.rgb, a);
  float al = max(a * vCol.a, o * vO.a);
  frag = vec4(rgb, al);
}
"""

TERR_VS = """
#version 330
uniform vec2 uScreen; uniform vec4 uRect;
in vec2 in_corner;
out vec2 vUV; out vec2 vPix;
void main(){
  vec2 t = in_corner * .5 + .5;
  vec2 pos = uRect.xy + uRect.zw * t;
  vUV = t; vPix = pos - uRect.xy;
  gl_Position = vec4(pos.x / uScreen.x * 2.0 - 1.0, 1.0 - pos.y / uScreen.y * 2.0, 0.0, 1.0);
}
"""

TERR_FS = """
#version 330
uniform sampler2D uMask; uniform sampler2D uHeat;
uniform vec3 uCol[4]; uniform vec3 uHi[4];
uniform float uTime; uniform vec2 uBase[4];
in vec2 vUV; in vec2 vPix;
out vec4 frag;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
  return mix(mix(hash(i), hash(i+vec2(1,0)), f.x), mix(hash(i+vec2(0,1)), hash(i+vec2(1,1)), f.x), f.y); }
void main(){
  vec4 m = texture(uMask, vUV);
  vec4 mb = textureLod(uMask, vUV, 3.0);
  int t = 0; float mv = m.r;
  if (m.g > mv) { t = 1; mv = m.g; } if (m.b > mv) { t = 2; mv = m.b; } if (m.a > mv) { t = 3; mv = m.a; }
  float w = max(fwidth(mv) * .8, 1e-3);
  float fill = smoothstep(.5 - w, .5 + w, mv);
  float wideOwn = t == 0 ? mb.r : t == 1 ? mb.g : t == 2 ? mb.b : mb.a;
  vec3 c = uCol[t], hi = uHi[t];
  vec2 rel = vPix - uBase[t];
  float ang = atan(rel.y, rel.x), rad = length(rel);
  float fib = noise(vec2(ang * 70.0, rad * .018)) * .65 + noise(vec2(ang * 190.0, rad * .05)) * .35;   // radial fibres
  float n = noise(vPix * .045);
  vec3 interior = c * (.12 + .24 * fib + .06 * n);
  float rimIn = 1.0 - smoothstep(.5, .9, mv);                   // crisp neon line right at the frontier
  float rimWide = clamp((1.0 - wideOwn) * 1.7, 0.0, 1.0);       // gradient band behind the front
  vec3 col = interior;
  col = mix(col, c * (.8 + .4 * fib), pow(rimWide, .8) * .85);
  col = mix(col, mix(c, hi, .6) * 1.35, rimIn);
  float h = texture(uHeat, vUV).r;
  col += hi * h * .45;
  // neutral background + grid
  vec3 bg = vec3(.022, .04, .07) + vec3(.01, .02, .03) * noise(vPix * .02);
  vec3 outc = mix(bg, col, fill);
  vec2 g = abs(fract(vPix / 100.0 + .5) - .5) * 100.0;
  float gl = 1.0 - smoothstep(.0, 1.2, min(g.x, g.y));
  outc += vec3(.6, .75, .9) * gl * .05;
  frag = vec4(outc, 1.0);
}
"""

QUAD_VS = """
#version 330
in vec2 in_corner;
out vec2 vUV;
void main(){ vUV = in_corner * .5 + .5; gl_Position = vec4(in_corner, 0.0, 1.0); }
"""

BLUR_FS = """
#version 330
uniform sampler2D uTex; uniform vec2 uDir;
in vec2 vUV; out vec4 frag;
void main(){
  vec4 s = texture(uTex, vUV) * .227027;
  s += (texture(uTex, vUV + uDir * 1.3846) + texture(uTex, vUV - uDir * 1.3846)) * .3162162;
  s += (texture(uTex, vUV + uDir * 3.2308) + texture(uTex, vUV - uDir * 3.2308)) * .0702703;
  frag = s;
}
"""

COMP_FS = """
#version 330
uniform sampler2D uScene; uniform sampler2D uGlow; uniform float uGlowK;
in vec2 vUV; out vec4 frag;
void main(){
  vec3 c = texture(uScene, vUV).rgb + texture(uGlow, vUV).rgb * uGlowK;
  frag = vec4(min(c, vec3(1.0)), 1.0);
}
"""
