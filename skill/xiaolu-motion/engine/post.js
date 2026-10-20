/* ==========================================================================
   xiaolu-motion · engine/post.js
   WebGL2 post pipeline: sub-frame accumulation (motion blur), dual-radius
   bloom from a dedicated half-res glow layer, vignette, flash, chromatic
   aberration, fade, grain — in two output modes:

   mode 'overlay' (transparent, default for compositing)
     Output is PREMULTIPLIED RGBA. Everything stays premultiplied end to end
     (canvas upload with UNPACK_PREMULTIPLY_ALPHA, accumulation, blur), so
     antialiased edges carry no black/white fringe. Glow is additive light:
       glow_alpha = 0 ('additive'): rgb += bloom, alpha untouched
                    -> exact under premultiplied "over" (out = O + base*(1-a))
       glow_alpha = 1 ('luma'): alpha += max(bloom.rgb)*(1-a)
                    -> for consumers that clamp rgb <= alpha
     Vignette / flash / fade are expressed as layers so that
       overlay over a flat background == opaque render on that background
     (verified by qa/alpha_selftest.py). Fully transparent pixels stay 0,0,0,0.
   mode 'opaque' : procedural background from tokens, as in the original film.

   Ported from 《在我开口之前》 src/post.js; 3D plane pass and the film-specific
   warm front were dropped (not needed by the component library yet).
   Image convention: framebuffer row 0 == image top, so readPixels is top-down.
   ========================================================================== */
import { gl3 } from './core.js';

export function createPost(W, H) {
  const cv = (typeof OffscreenCanvas !== 'undefined') ? new OffscreenCanvas(W, H) : Object.assign(document.createElement('canvas'), { width: W, height: H });
  const gl = cv.getContext('webgl2', { alpha: true, antialias: false, depth: false, stencil: false, premultipliedAlpha: true, preserveDrawingBuffer: false, powerPreference: 'high-performance' });
  if (!gl) throw new Error('WebGL2 unavailable');
  if (!gl.getExtension('EXT_color_buffer_float')) throw new Error('EXT_color_buffer_float unavailable');
  gl.getExtension('OES_texture_float_linear');
  const HW = Math.max(1, W >> 1), HH = Math.max(1, H >> 1), QW = Math.max(1, W >> 2), QH = Math.max(1, H >> 2);

  function shader(type, src) {
    const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  function program(vs, fs) {
    const p = gl.createProgram();
    gl.attachShader(p, shader(gl.VERTEX_SHADER, vs)); gl.attachShader(p, shader(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    const u = {};
    const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < n; i++) { const info = gl.getActiveUniform(p, i); u[info.name.replace(/\[0\]$/, '')] = gl.getUniformLocation(p, info.name); }
    return { p, u };
  }
  function tex(w, h, internal, format, type, filter = gl.LINEAR) {
    const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, internal, w, h, 0, format, type, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return t;
  }
  function fbo(w, h, internal = gl.RGBA16F, type = gl.HALF_FLOAT) {
    const t = tex(w, h, internal, gl.RGBA, type);
    const f = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, f);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
    if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) throw new Error('FBO incomplete');
    return { f, t, w, h };
  }

  const VS = `#version 300 es
  layout(location=0) in vec2 a_pos; out vec2 v_uv;
  void main(){ v_uv = a_pos*0.5+0.5; gl_Position = vec4(a_pos,0.0,1.0); }`;
  const FS_COPY = `#version 300 es
  precision highp float; in vec2 v_uv; out vec4 o; uniform sampler2D u_tex; uniform float u_gain;
  void main(){ o = texture(u_tex, v_uv) * u_gain; }`;
  const FS_BLUR = `#version 300 es
  precision highp float; in vec2 v_uv; out vec4 o; uniform sampler2D u_tex; uniform vec2 u_dir; uniform float u_sigma; uniform int u_rad;
  void main(){
    vec2 texel = 1.0/vec2(textureSize(u_tex,0));
    vec4 acc = texture(u_tex, v_uv); float ws = 1.0;
    float inv = 0.5/(u_sigma*u_sigma);
    for(int i=1;i<=48;i++){
      if(i>u_rad) break;
      float fi = float(i); float w = exp(-fi*fi*inv);
      acc += (texture(u_tex, v_uv + u_dir*texel*fi) + texture(u_tex, v_uv - u_dir*texel*fi))*w; ws += 2.0*w;
    }
    o = acc/ws;
  }`;
  const FS_DOWN = `#version 300 es
  precision highp float; in vec2 v_uv; out vec4 o; uniform sampler2D u_tex;
  void main(){ vec2 t = 1.0/vec2(textureSize(u_tex,0));
    o = 0.25*(texture(u_tex, v_uv+vec2(-t.x,-t.y)*0.5)+texture(u_tex, v_uv+vec2(t.x,-t.y)*0.5)+texture(u_tex, v_uv+vec2(-t.x,t.y)*0.5)+texture(u_tex, v_uv+vec2(t.x,t.y)*0.5)); }`;
  const FS_FINAL = `#version 300 es
  precision highp float; in vec2 v_uv; out vec4 o;
  uniform sampler2D u_world, u_bA, u_bB;
  uniform vec2 u_res; uniform float u_frame;
  uniform int u_mode;                 // 0 overlay (premultiplied, transparent), 1 opaque
  uniform vec3 u_c0, u_c1;            // opaque background base / glow
  uniform vec2 u_bloom;               // gain small radius, gain large radius
  uniform float u_glowAlpha;          // 0 additive, 1 luma-keyed
  uniform float u_vig, u_flash, u_ca, u_fade, u_grain;
  uniform vec2 u_vigR;                // vignette inner/outer radius
  uniform vec3 u_flashTint;
  float h12(vec2 p){ vec3 p3 = fract(vec3(p.xyx)*.1031); p3 += dot(p3, p3.yzx+33.33); return fract((p3.x+p3.y)*p3.z); }
  vec4 content(vec2 uv){
    vec4 w = texture(u_world, uv);                                    // premultiplied
    vec3 b = texture(u_bA, uv).rgb*u_bloom.x + texture(u_bB, uv).rgb*u_bloom.y;   // additive light
    float ga = u_glowAlpha * clamp(max(b.r, max(b.g, b.b)), 0.0, 1.0);
    return vec4(w.rgb + b, w.a + ga*(1.0 - w.a));
  }
  void main(){
    vec2 uv = v_uv;
    vec4 c;
    if (u_ca > 0.0) { vec2 d = (uv-0.5)*u_ca; vec4 r = content(uv + d), g = content(uv), bb = content(uv - d);
      c = vec4(r.r, g.g, bb.b, max(max(r.a, g.a), bb.a)); }
    else c = content(uv);
    // vignette distance keeps the original 9:16 shape (x weighted 1.25 in uv at 9:16) for any aspect
    float v = u_vig * smoothstep(u_vigR.x, u_vigR.y, length((uv-0.5)*vec2(1.25*u_res.x/u_res.y/0.5625, 1.0)));
    float n = h12(gl_FragCoord.xy + vec2(u_frame*13.1, u_frame*7.7)) + h12(gl_FragCoord.xy*1.37 + vec2(u_frame*3.3, 91.0)) - 1.0;
    if (u_mode == 1) {
      vec2 px = uv*u_res;
      vec2 gq = (px - u_res*vec2(0.5, 0.48)) / (u_res*vec2(0.70, 0.60));
      vec3 bg = mix(u_c0, u_c1, exp(-dot(gq,gq)*1.7));
      vec3 col = bg*(1.0 - c.a) + c.rgb;
      col *= 1.0 - v;
      col = col + u_flash*u_flashTint*(1.0 - col);
      col *= u_fade;
      col += n*u_grain/255.0;
      o = vec4(clamp(col, 0.0, 1.0), 1.0);
    } else {
      vec3 rgb = c.rgb*(1.0 - v);          // content over a black vignette layer of alpha v
      float a = c.a + v*(1.0 - c.a);
      rgb = rgb*(1.0 - u_flash) + u_flash*u_flashTint;   // white flash layer on top
      a = a + u_flash*(1.0 - a);
      rgb *= u_fade; a *= u_fade;          // layer opacity
      rgb += n*u_grain/255.0 * a;          // grain only where there is coverage: empty stays exactly 0
      o = vec4(clamp(rgb, 0.0, 1.0), clamp(a, 0.0, 1.0));
    }
  }`;

  const P_COPY = program(VS, FS_COPY), P_BLUR = program(VS, FS_BLUR), P_DOWN = program(VS, FS_DOWN), P_FINAL = program(VS, FS_FINAL);
  const vaoFS = gl.createVertexArray(); gl.bindVertexArray(vaoFS);
  const vbFS = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, vbFS);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  gl.bindVertexArray(null);

  const texWorld = tex(W, H, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE);
  const texGlow = tex(HW, HH, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE);
  const A = fbo(W, H), GA = fbo(HW, HH), B1 = fbo(HW, HH), B2 = fbo(HW, HH), Q1 = fbo(QW, QH), Q2 = fbo(QW, QH);
  const OUT = fbo(W, H, gl.RGBA8, gl.UNSIGNED_BYTE);

  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);   // canvas data stays premultiplied
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);             // texture row 0 = canvas top

  function upload(t, canvas) { gl.bindTexture(gl.TEXTURE_2D, t); gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, gl.RGBA, gl.UNSIGNED_BYTE, canvas); }
  function bindTarget(tg) { gl.bindFramebuffer(gl.FRAMEBUFFER, tg.f); gl.viewport(0, 0, tg.w, tg.h); }
  function fsDraw(P, texs) {
    gl.useProgram(P.p);
    let unit = 0;
    for (const [name, t] of texs) { gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, t); gl.uniform1i(P.u[name], unit); unit++; }
    gl.bindVertexArray(vaoFS); gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
  function copyTo(tg, t, gain, blend) {
    bindTarget(tg);
    if (blend === 'add') { gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE); } else gl.disable(gl.BLEND);
    gl.useProgram(P_COPY.p); gl.uniform1f(P_COPY.u.u_gain, gain);
    fsDraw(P_COPY, [['u_tex', t]]);
    gl.disable(gl.BLEND);
  }
  function clearTarget(tg) { bindTarget(tg); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT); }
  function blur(src, tmp, sigma) {
    const rad = Math.min(48, Math.ceil(sigma * 3));
    bindTarget(tmp); gl.useProgram(P_BLUR.p);
    gl.uniform2f(P_BLUR.u.u_dir, 1, 0); gl.uniform1f(P_BLUR.u.u_sigma, sigma); gl.uniform1i(P_BLUR.u.u_rad, rad);
    fsDraw(P_BLUR, [['u_tex', src.t]]);
    bindTarget(src); gl.useProgram(P_BLUR.p);
    gl.uniform2f(P_BLUR.u.u_dir, 0, 1); gl.uniform1f(P_BLUR.u.u_sigma, sigma); gl.uniform1i(P_BLUR.u.u_rad, rad);
    fsDraw(P_BLUR, [['u_tex', tmp.t]]);
  }

  let nSub = 1;
  function begin(n) { nSub = n; clearTarget(A); clearTarget(GA); }
  function addSub(world, glow) {
    upload(texWorld, world); upload(texGlow, glow);
    const g = 1 / nSub;
    copyTo(A, texWorld, g, 'add');
    copyTo(GA, texGlow, g, 'add');
  }
  /* U: {mode:'overlay'|'opaque', frame, bg, bgGlow, bloom:[a,b], sigma:[a,b], glowAlpha, vig, vigR:[i,o], flash, flashTint, ca, fade, grain} */
  function finish(U) {
    copyTo(B1, GA.t, 1, null); blur(B1, B2, U.sigma[0]);
    bindTarget(Q1); gl.useProgram(P_DOWN.p); fsDraw(P_DOWN, [['u_tex', GA.t]]);
    blur(Q1, Q2, U.sigma[1]);
    bindTarget(OUT); gl.disable(gl.BLEND);
    gl.useProgram(P_FINAL.p);
    const u = P_FINAL.u;
    gl.uniform2f(u.u_res, W, H); gl.uniform1f(u.u_frame, U.frame);
    gl.uniform1i(u.u_mode, U.mode === 'opaque' ? 1 : 0);
    gl.uniform3fv(u.u_c0, gl3(U.bg || '#000000')); gl.uniform3fv(u.u_c1, gl3(U.bgGlow || U.bg || '#000000'));
    gl.uniform2f(u.u_bloom, U.bloom[0], U.bloom[1]);
    gl.uniform1f(u.u_glowAlpha, U.glowAlpha || 0);
    gl.uniform1f(u.u_vig, U.vig || 0); gl.uniform2f(u.u_vigR, U.vigR[0], U.vigR[1]);
    gl.uniform1f(u.u_flash, U.flash || 0); gl.uniform3fv(u.u_flashTint, U.flashTint || [1, 1, 1]);
    gl.uniform1f(u.u_ca, U.ca || 0); gl.uniform1f(u.u_fade, U.fade ?? 1); gl.uniform1f(u.u_grain, U.grain || 0);
    fsDraw(P_FINAL, [['u_world', A.t], ['u_bA', B1.t], ['u_bB', Q1.t]]);
  }
  function read(buf) { gl.bindFramebuffer(gl.FRAMEBUFFER, OUT.f); gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, buf); }
  function info() { const d = gl.getExtension('WEBGL_debug_renderer_info'); return d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER); }
  return { begin, addSub, finish, read, info, gl };
}
