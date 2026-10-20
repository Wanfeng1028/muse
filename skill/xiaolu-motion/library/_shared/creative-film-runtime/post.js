'use strict';
/* ==========================================================================
   WebGL2 pipeline: sub-frame accumulation (motion blur), 3D planes,
   bloom (dedicated glow layer, dual radius), procedural background with the
   cold->warm "ink in water" front, vignette, UI overlay, flash, dither.
   Image convention: framebuffer row 0 == image top (so readPixels is top-down).
   ========================================================================== */
const GLX = (() => {
  const cv = mkCanvas(W, H);
  const gl = cv.getContext('webgl2', { alpha: false, antialias: false, depth: false, stencil: false, premultipliedAlpha: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  if (!gl) throw new Error('WebGL2 unavailable');
  if (!gl.getExtension('EXT_color_buffer_float')) throw new Error('EXT_color_buffer_float unavailable');
  gl.getExtension('OES_texture_float_linear');
  const ANISO = gl.getExtension('EXT_texture_filter_anisotropic');
  const HW = W / 2, HH = H / 2, QW = W / 4, QH = H / 4;

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
  function fbo(w, h) {
    const t = tex(w, h, gl.RGBA16F, gl.RGBA, gl.HALF_FLOAT);
    const f = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, f);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
    if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) throw new Error('FBO incomplete');
    return { f, t, w, h };
  }

  /* ---------------- shaders ---------------- */
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
  const VS_PLANE = `#version 300 es
  layout(location=0) in vec4 a_clip; layout(location=1) in vec2 a_uv; out vec2 v_uv;
  void main(){ v_uv = a_uv; gl_Position = a_clip; }`;
  const FS_PLANE = `#version 300 es
  precision highp float; in vec2 v_uv; out vec4 o; uniform sampler2D u_tex; uniform vec3 u_tint; uniform float u_alpha; uniform float u_add; uniform float u_thr;
  void main(){
    vec4 c = texture(u_tex, v_uv);
    vec3 rgb = c.rgb * u_tint;
    if (u_thr > 0.0) { float l = max(max(rgb.r, rgb.g), rgb.b); rgb *= smoothstep(u_thr, u_thr + 0.35, l); }
    o = vec4(rgb * u_alpha, c.a * u_alpha * (1.0 - u_add));
  }`;
  const FS_FINAL = `#version 300 es
  precision highp float; in vec2 v_uv; out vec4 o;
  uniform sampler2D u_world, u_ui, u_bA, u_bB;
  uniform vec2 u_res; uniform float u_time, u_frame;
  uniform vec3 u_c0, u_c1, u_w0, u_w1;       // cold base/glow, warm base/glow
  uniform vec4 u_front;                        // cx, cy, radius, rimAmount
  uniform float u_warm;                        // 1 = fully warm (skip mask)
  uniform vec2 u_bloom;                        // gain small, gain large
  uniform float u_vig, u_flash, u_ca, u_fade, u_dither, u_bgGlow;
  uniform vec3 u_amber;
  float h12(vec2 p){ vec3 p3 = fract(vec3(p.xyx)*.1031); p3 += dot(p3, p3.yzx+33.33); return fract((p3.x+p3.y)*p3.z); }
  float vn(vec2 p){ vec2 i=floor(p), f=fract(p); vec2 u=f*f*(3.-2.*f);
    return mix(mix(h12(i),h12(i+vec2(1,0)),u.x), mix(h12(i+vec2(0,1)),h12(i+vec2(1,1)),u.x), u.y); }
  float fbm(vec2 p){ float s=0., a=.5; for(int i=0;i<5;i++){ s+=a*vn(p); p=p*2.03+vec2(1.7,9.2); a*=.5; } return s; }
  float warmMask(vec2 px, out float ink){
    ink = 0.0;
    if (u_warm >= 1.0) return 1.0;
    if (u_front.z <= 0.0) return 0.0;
    vec2 d = px - u_front.xy; float r = length(d);
    vec2 dir = d/max(r,1e-3);
    // soft radial bloom of warm light; only a fine, low-amplitude noise on the edge
    float n1 = fbm(dir*3.1 + vec2(u_time*0.4, 3.1));
    float n2 = fbm(px*0.011 + vec2(0.0, u_time*0.3));
    float edge = u_front.z * (1.0 + 0.10*(n1-0.5)) + (n2-0.5)*48.0;
    float m = 1.0 - smoothstep(edge - 170.0, edge + 10.0, r);
    // faint warm light just inside the front (well under a third of the old smoke density)
    float din = edge - r;
    float band = smoothstep(-40.0, 30.0, din) * (1.0 - smoothstep(30.0, 280.0, din));
    ink = band * (0.55 + 0.45*fbm(px*0.009 + vec2(u_time*0.5, 1.0))) * u_front.w;
    return m;
  }
  vec3 background(vec2 px, out float rim){
    vec2 q = (px - vec2(540.0, 920.0)) / vec2(760.0, 1150.0);
    float g = exp(-dot(q,q)*1.7) * u_bgGlow;
    vec3 cold = mix(u_c0, u_c1, g);
    vec3 warm = mix(u_w0, u_w1, g);
    float m = warmMask(px, rim);
    return mix(cold, warm, m);
  }
  vec3 scene(vec2 uv){
    vec2 px = uv*u_res;
    float rim;
    vec3 bg = background(px, rim);
    vec4 w = texture(u_world, uv);
    vec3 c = bg*(1.0 - w.a) + w.rgb;
    c += mix(u_amber, vec3(0.91, 0.38, 0.24), 0.25) * rim * 0.075;
    c += texture(u_bA, uv).rgb*u_bloom.x + texture(u_bB, uv).rgb*u_bloom.y;
    return c;
  }
  void main(){
    vec2 uv = v_uv;
    vec3 c;
    if (u_ca > 0.0) { vec2 d = (uv-0.5); c = vec3(scene(uv + d*u_ca).r, scene(uv).g, scene(uv - d*u_ca).b); }
    else c = scene(uv);
    vec2 q = (uv-0.5)*vec2(1.0, 1.0); q.x *= 1.25;
    float vr = length(q);
    c *= 1.0 - u_vig*smoothstep(0.30, 0.78, vr);
    vec4 ui = texture(u_ui, uv);
    c = c*(1.0-ui.a) + ui.rgb;
    if (u_flash > 0.0) {
      vec2 fq = (uv - vec2(0.5)) * vec2(1.0, 1.7);
      float fa = u_flash * (0.1 + 0.9 * exp(-dot(fq, fq) * 6.0));
      c = vec3(1.0) - (vec3(1.0) - c) * (1.0 - fa * vec3(0.93, 0.98, 1.0));
    }
    c *= u_fade;
    float n = h12(gl_FragCoord.xy + vec2(u_frame*13.1, u_frame*7.7)) + h12(gl_FragCoord.xy*1.37 + vec2(u_frame*3.3, 91.0)) - 1.0;
    c += n*u_dither/255.0;
    o = vec4(clamp(c, 0.0, 1.0), 1.0);
  }`;

  const P_COPY = program(VS, FS_COPY), P_BLUR = program(VS, FS_BLUR), P_DOWN = program(VS, FS_DOWN);
  const P_PLANE = program(VS_PLANE, FS_PLANE), P_FINAL = program(VS, FS_FINAL);

  /* full screen triangle */
  const vaoFS = gl.createVertexArray(); gl.bindVertexArray(vaoFS);
  const vbFS = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, vbFS);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  /* plane quad buffer */
  const vaoPL = gl.createVertexArray(); gl.bindVertexArray(vaoPL);
  const vbPL = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, vbPL);
  gl.bufferData(gl.ARRAY_BUFFER, 4 * 6 * 4, gl.DYNAMIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 4, gl.FLOAT, false, 24, 0);
  gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 24, 16);
  gl.bindVertexArray(null);

  /* textures & targets */
  const texWorld = tex(W, H, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE);
  const texGlow = tex(HW, HH, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE);
  const texUI = tex(W, H, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE);
  const T = fbo(W, H), A = fbo(W, H), GT = fbo(HW, HH), GA = fbo(HW, HH), B1 = fbo(HW, HH), B2 = fbo(HW, HH), Q1 = fbo(QW, QH), Q2 = fbo(QW, QH);

  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);

  function upload(t, canvas) { gl.bindTexture(gl.TEXTURE_2D, t); gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, gl.RGBA, gl.UNSIGNED_BYTE, canvas); }
  function bindTarget(tg) { gl.bindFramebuffer(gl.FRAMEBUFFER, tg ? tg.f : null); gl.viewport(0, 0, tg ? tg.w : W, tg ? tg.h : H); }
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

  /* planes: {tex, corners:[[X,Y,Z] TL,TR,BL,BR], alpha, tint:[r,g,b], add, glow, thr} */
  const F_NEAR = 12, F_FAR = 200000;
  const za = (F_FAR + F_NEAR) / (F_FAR - F_NEAR), zb = -2 * F_FAR * F_NEAR / (F_FAR - F_NEAR);
  const pbuf = new Float32Array(24);
  function drawPlanes(planes, focal, glowPass) {
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(P_PLANE.p);
    gl.bindVertexArray(vaoPL); gl.bindBuffer(gl.ARRAY_BUFFER, vbPL);
    const uvs = [[0, 0], [1, 0], [0, 1], [1, 1]];
    for (const pl of planes) {
      const a = glowPass ? pl.alpha * (pl.glow ?? 0) : pl.alpha;
      if (a <= 0.001) continue;
      for (let i = 0; i < 4; i++) {
        const [X, Y, Z] = pl.corners[i];
        pbuf[i * 6 + 0] = (2 * focal / W) * X; pbuf[i * 6 + 1] = (2 * focal / H) * Y;
        pbuf[i * 6 + 2] = za * Z + zb; pbuf[i * 6 + 3] = Z;
        pbuf[i * 6 + 4] = uvs[i][0]; pbuf[i * 6 + 5] = uvs[i][1];
      }
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, pbuf);
      const useG = glowPass && pl.glowTex;
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, useG ? pl.glowTex : pl.tex); gl.uniform1i(P_PLANE.u.u_tex, 0);
      const tint = pl.tint || [1, 1, 1];
      gl.uniform3f(P_PLANE.u.u_tint, tint[0], tint[1], tint[2]);
      gl.uniform1f(P_PLANE.u.u_alpha, a);
      gl.uniform1f(P_PLANE.u.u_add, glowPass ? 1 : (pl.add || 0));
      gl.uniform1f(P_PLANE.u.u_thr, glowPass && !useG ? (pl.thr || 0.35) : 0);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
    gl.disable(gl.BLEND); gl.bindVertexArray(null);
  }
  function makePlaneTex(canvas) {
    const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, canvas);
    gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    if (ANISO) gl.texParameterf(gl.TEXTURE_2D, ANISO.TEXTURE_MAX_ANISOTROPY_EXT, Math.min(8, gl.getParameter(ANISO.MAX_TEXTURE_MAX_ANISOTROPY_EXT)));
    return t;
  }
  function updatePlaneTex(t, canvas) {
    gl.bindTexture(gl.TEXTURE_2D, t); gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, gl.RGBA, gl.UNSIGNED_BYTE, canvas); gl.generateMipmap(gl.TEXTURE_2D);
  }

  let nSub = 1;
  function begin(n) { nSub = n; clearTarget(A); clearTarget(GA); }
  function addSub(world, glow, planes, focal) {
    upload(texWorld, world); upload(texGlow, glow);
    const g = 1 / nSub;
    if (planes && planes.length) {
      copyTo(T, texWorld, 1, null); drawPlanes(planes, focal, false);
      copyTo(A, T.t, g, 'add');
      copyTo(GT, texGlow, 1, null); drawPlanes(planes, focal, true);
      copyTo(GA, GT.t, g, 'add');
    } else {
      copyTo(A, texWorld, g, 'add');
      copyTo(GA, texGlow, g, 'add');
    }
  }
  function blur(src, tmp, sigma) {
    const rad = Math.min(48, Math.ceil(sigma * 3));
    bindTarget(tmp); gl.useProgram(P_BLUR.p);
    gl.uniform2f(P_BLUR.u.u_dir, 1, 0); gl.uniform1f(P_BLUR.u.u_sigma, sigma); gl.uniform1i(P_BLUR.u.u_rad, rad);
    fsDraw(P_BLUR, [['u_tex', src.t]]);
    bindTarget(src); gl.useProgram(P_BLUR.p);
    gl.uniform2f(P_BLUR.u.u_dir, 0, 1); gl.uniform1f(P_BLUR.u.u_sigma, sigma); gl.uniform1i(P_BLUR.u.u_rad, rad);
    fsDraw(P_BLUR, [['u_tex', tmp.t]]);
  }
  function finish(ui, U) {
    upload(texUI, ui);
    // bloom: small radius at half res, large radius at quarter res
    copyTo(B1, GA.t, 1, null); blur(B1, B2, U.sigA || 4.0);
    bindTarget(Q1); gl.useProgram(P_DOWN.p); fsDraw(P_DOWN, [['u_tex', GA.t]]);
    blur(Q1, Q2, U.sigB || 8.0);
    bindTarget(null);
    gl.useProgram(P_FINAL.p);
    const u = P_FINAL.u;
    gl.uniform2f(u.u_res, W, H); gl.uniform1f(u.u_time, U.time); gl.uniform1f(u.u_frame, U.frame);
    gl.uniform3fv(u.u_c0, gl3(COL.bg)); gl.uniform3fv(u.u_c1, gl3(COL.bgGlow));
    gl.uniform3fv(u.u_w0, gl3(COL.wbg)); gl.uniform3fv(u.u_w1, gl3(COL.wbgGlow));
    gl.uniform3fv(u.u_amber, gl3(COL.amber));
    gl.uniform4f(u.u_front, U.front[0], U.front[1], U.front[2], U.front[3]);
    gl.uniform1f(u.u_warm, U.warm); gl.uniform2f(u.u_bloom, U.bloomA, U.bloomB);
    gl.uniform1f(u.u_vig, U.vig); gl.uniform1f(u.u_flash, U.flash); gl.uniform1f(u.u_ca, U.ca);
    gl.uniform1f(u.u_fade, U.fade); gl.uniform1f(u.u_dither, U.dither); gl.uniform1f(u.u_bgGlow, U.bgGlow);
    fsDraw(P_FINAL, [['u_world', A.t], ['u_ui', texUI], ['u_bA', B1.t], ['u_bB', Q1.t]]);
  }
  function read(buf) { gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, buf); }
  function info() { const d = gl.getExtension('WEBGL_debug_renderer_info'); return d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER); }
  return { begin, addSub, finish, read, makePlaneTex, updatePlaneTex, info, canvas: cv, gl };
})();
