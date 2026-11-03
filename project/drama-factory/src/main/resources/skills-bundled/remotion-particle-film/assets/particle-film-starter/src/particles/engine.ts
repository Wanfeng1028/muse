/**
 * Minimal WebGL2 particle renderer.
 *
 * Deliberately dependency free: one BufferGeometry-equivalent vertex buffer set,
 * one ShaderMaterial-equivalent program, additive point rendering, and a small
 * bloom/composite chain. Nothing is animated by the browser clock - every draw
 * is a pure function of the frame number.
 */

import { FAR, NEAR } from "../config";
import type { FrameState } from "../timeline";
import type { GlyphTargets } from "./glyph";
import {
  BLUR_FRAG,
  BRIGHT_FRAG,
  COMPOSITE_FRAG,
  POINT_FRAG,
  POINT_VERT,
  QUAD_VERT,
} from "./shaders";

// ---------------------------------------------------------------------------
// tiny math
// ---------------------------------------------------------------------------

const perspective = (fovy: number, aspect: number, near: number, far: number) => {
  const t = 1 / Math.tan(fovy / 2);
  const nf = 1 / (near - far);
  return new Float32Array([
    t / aspect, 0, 0, 0,
    0, t, 0, 0,
    0, 0, (far + near) * nf, -1,
    0, 0, 2 * far * near * nf, 0,
  ]);
};

const lookAt = (
  eye: readonly [number, number, number],
  center: readonly [number, number, number],
) => {
  let zx = eye[0] - center[0];
  let zy = eye[1] - center[1];
  let zz = eye[2] - center[2];
  let len = Math.hypot(zx, zy, zz) || 1;
  zx /= len;
  zy /= len;
  zz /= len;
  // x = normalize(cross(up, z)) with up = (0, 1, 0)
  let xx = zz;
  let xy = 0;
  let xz = -zx;
  len = Math.hypot(xx, xy, xz) || 1;
  xx /= len;
  xy /= len;
  xz /= len;
  // y = cross(z, x)
  const yx = zy * xz - zz * xy;
  const yy = zz * xx - zx * xz;
  const yz = zx * xy - zy * xx;
  return new Float32Array([
    xx, yx, zx, 0,
    xy, yy, zy, 0,
    xz, yz, zz, 0,
    -(xx * eye[0] + xy * eye[1] + xz * eye[2]),
    -(yx * eye[0] + yy * eye[1] + yz * eye[2]),
    -(zx * eye[0] + zy * eye[1] + zz * eye[2]),
    1,
  ]);
};

const multiply = (a: Float32Array, b: Float32Array) => {
  const out = new Float32Array(16);
  for (let c = 0; c < 4; c++) {
    for (let r = 0; r < 4; r++) {
      out[c * 4 + r] =
        a[0 * 4 + r] * b[c * 4 + 0] +
        a[1 * 4 + r] * b[c * 4 + 1] +
        a[2 * 4 + r] * b[c * 4 + 2] +
        a[3 * 4 + r] * b[c * 4 + 3];
    }
  }
  return out;
};

/**
 * Deterministic per-channel hash.
 *
 * Using four consecutive PRNG outputs would look fine for a starfield but is
 * catastrophic for grouped structures: selecting 1/64 of the particles by
 * channel 0 also selects a single slice of the PRNG stream, so the other three
 * channels stop being independent and each "planet" collapses into a 1-D curve.
 * Hashing (index, channel) keeps every channel independent.
 */
const hash = (index: number, channel: number): number => {
  let t = (Math.imul(index, 0x9e3779b1) + Math.imul(channel, 0x85ebca6b)) >>> 0;
  t ^= t >>> 15;
  t = Math.imul(t, 0x2c1b3c6d);
  t ^= t >>> 12;
  t = Math.imul(t, 0x297a2d39);
  t ^= t >>> 15;
  return (t >>> 0) / 4294967296;
};

// ---------------------------------------------------------------------------

type Target = {
  readonly texture: WebGLTexture;
  readonly framebuffer: WebGLFramebuffer;
  width: number;
  height: number;
};

export class ParticleEngine {
  public readonly info: string;

  private readonly gl: WebGL2RenderingContext;
  private readonly canvas: HTMLCanvasElement;
  private readonly count: number;
  private readonly pointProgram: WebGLProgram;
  private readonly brightProgram: WebGLProgram;
  private readonly blurProgram: WebGLProgram;
  private readonly compositeProgram: WebGLProgram;
  private readonly pointUniforms: Record<string, WebGLUniformLocation | null>;
  private readonly brightUniforms: Record<string, WebGLUniformLocation | null>;
  private readonly blurUniforms: Record<string, WebGLUniformLocation | null>;
  private readonly compositeUniforms: Record<string, WebGLUniformLocation | null>;
  private readonly vao: WebGLVertexArrayObject;
  private readonly quadVao: WebGLVertexArrayObject;
  private readonly buffers: WebGLBuffer[] = [];
  private readonly fbos: Target[] = [];
  private halfFloat: boolean;
  private glyphTexture: WebGLTexture;
  private glyphCount = 1;
  private glyphW = 1;
  private glyphH = 1;
  private glyphJitter = 0.2;
  private width = 0;
  private height = 0;

  constructor(canvas: HTMLCanvasElement, count: number) {
    this.canvas = canvas;
    this.count = count;
    const gl = canvas.getContext("webgl2", {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      premultipliedAlpha: false,
      preserveDrawingBuffer: true,
      powerPreference: "high-performance",
    });
    if (!gl) {
      throw new Error("WebGL2 is not available in this browser");
    }
    this.gl = gl;
    this.info = (() => {
      const dbg = gl.getExtension("WEBGL_debug_renderer_info");
      return dbg
        ? String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL))
        : String(gl.getParameter(gl.RENDERER));
    })();
    this.halfFloat = gl.getExtension("EXT_color_buffer_float") !== null;

    this.pointProgram = this.link(POINT_VERT, POINT_FRAG, "points");
    this.brightProgram = this.link(QUAD_VERT, BRIGHT_FRAG, "bright");
    this.blurProgram = this.link(QUAD_VERT, BLUR_FRAG, "blur");
    this.compositeProgram = this.link(QUAD_VERT, COMPOSITE_FRAG, "composite");

    const names = [
      "uViewProj", "uCamPos", "uTime", "uStateA", "uStateB", "uBlend", "uStagger",
      "uPointSize", "uOpacity", "uReveal", "uTurbAmp", "uFlowScale", "uExposure",
      "uBlackHole", "uStreak", "uTapIndex", "uTaps", "uGather", "uBurst",
      "uParticleCount", "uGlyph", "uGlyphCount", "uGlyphW", "uGlyphH",
      "uGlyphJitter", "uSwirl",
    ];
    const u: Record<string, WebGLUniformLocation | null> = {};
    for (const n of names) u[n] = gl.getUniformLocation(this.pointProgram, n);
    this.pointUniforms = u;

    const collect = (program: WebGLProgram, list: string[]) => {
      const map: Record<string, WebGLUniformLocation | null> = {};
      for (const n of list) map[n] = gl.getUniformLocation(program, n);
      return map;
    };
    this.brightUniforms = collect(this.brightProgram, ["uScene", "uThreshold"]);
    this.blurUniforms = collect(this.blurProgram, ["uSource", "uDirection"]);
    this.compositeUniforms = collect(this.compositeProgram, [
      "uScene", "uBloom", "uBloomStrength", "uTime", "uResolution",
    ]);

    // 1x1 placeholder so the sampler is always valid before the glyph exists
    const placeholder = gl.createTexture()!;
    gl.bindTexture(gl.TEXTURE_2D, placeholder);
    gl.texImage2D(
      gl.TEXTURE_2D, 0, gl.RGBA32F, 1, 1, 0, gl.RGBA, gl.FLOAT,
      new Float32Array([0, 0, 0, 1]),
    );
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    this.glyphTexture = placeholder;

    this.vao = gl.createVertexArray()!;
    gl.bindVertexArray(this.vao);
    const seeds = new Float32Array(count * 4);
    const indices = new Float32Array(count);
    const births = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      seeds[i * 4 + 0] = hash(i, 0);
      seeds[i * 4 + 1] = hash(i, 1);
      seeds[i * 4 + 2] = hash(i, 2);
      seeds[i * 4 + 3] = hash(i, 3);
      indices[i] = i;
      births[i] = hash(i, 4);
    }
    const attach = (data: Float32Array, size: number, location: number) => {
      const buf = gl.createBuffer()!;
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(location);
      gl.vertexAttribPointer(location, size, gl.FLOAT, false, 0, 0);
      this.buffers.push(buf);
    };
    attach(seeds, 4, 0);
    attach(indices, 1, 1);
    attach(births, 1, 2);
    gl.bindVertexArray(null);

    this.quadVao = gl.createVertexArray()!;
  }

  get renderer(): string {
    return this.info;
  }

  get supportsFloatTargets(): boolean {
    return this.halfFloat;
  }

  private link(vert: string, frag: string, label: string): WebGLProgram {
    const gl = this.gl;
    const compile = (type: number, src: string) => {
      const sh = gl.createShader(type)!;
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        const log = gl.getShaderInfoLog(sh);
        throw new Error(`[${label}] shader compile failed: ${log}`);
      }
      return sh;
    };
    const program = gl.createProgram()!;
    gl.attachShader(program, compile(gl.VERTEX_SHADER, vert));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, frag));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(`[${label}] link failed: ${gl.getProgramInfoLog(program)}`);
    }
    return program;
  }

  setGlyph(targets: GlyphTargets): void {
    const gl = this.gl;
    gl.deleteTexture(this.glyphTexture);
    const tex = gl.createTexture()!;
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      gl.RGBA32F,
      targets.texWidth,
      targets.texHeight,
      0,
      gl.RGBA,
      gl.FLOAT,
      targets.data,
    );
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    this.glyphTexture = tex;
    this.glyphCount = targets.count;
    this.glyphW = targets.texWidth;
    this.glyphH = targets.texHeight;
    // half the mean sample distance: enough to break up the grid, small enough
    // that the strokes stay crisp
    this.glyphJitter = Math.max(targets.spacing * 0.5, 0.02);
  }

  private makeTarget(width: number, height: number): Target {
    const gl = this.gl;
    const texture = gl.createTexture()!;
    gl.bindTexture(gl.TEXTURE_2D, texture);
    const internal = this.halfFloat ? gl.RGBA16F : gl.RGBA8;
    const type = this.halfFloat ? gl.HALF_FLOAT : gl.UNSIGNED_BYTE;
    gl.texImage2D(gl.TEXTURE_2D, 0, internal, width, height, 0, gl.RGBA, type, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const framebuffer = gl.createFramebuffer()!;
    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
    gl.framebufferTexture2D(
      gl.FRAMEBUFFER,
      gl.COLOR_ATTACHMENT0,
      gl.TEXTURE_2D,
      texture,
      0,
    );
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return { texture, framebuffer, width, height };
  }

  private resize(width: number, height: number): void {
    if (this.width === width && this.height === height) return;
    const gl = this.gl;
    for (const t of this.fbos) {
      gl.deleteTexture(t.texture);
      gl.deleteFramebuffer(t.framebuffer);
    }
    this.fbos.length = 0;
    this.width = width;
    this.height = height;
    this.canvas.width = width;
    this.canvas.height = height;
    this.fbos.push(this.makeTarget(width, height));
    this.fbos.push(this.makeTarget(Math.ceil(width / 4), Math.ceil(height / 4)));
    this.fbos.push(this.makeTarget(Math.ceil(width / 4), Math.ceil(height / 4)));
  }

  render(state: FrameState, width: number, height: number): void {
    const gl = this.gl;
    this.resize(width, height);
    const [scene, bloomA, bloomB] = this.fbos;

    const proj = perspective(
      state.fov,
      this.width / this.height,
      NEAR,
      FAR,
    );
    const view = lookAt(state.camPos, state.camTarget);
    const viewProj = multiply(proj, view);

    // ---- pass 1: particles -------------------------------------------------
    gl.bindFramebuffer(gl.FRAMEBUFFER, scene.framebuffer);
    gl.viewport(0, 0, this.width, this.height);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.disable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);

    const u = this.pointUniforms;
    gl.useProgram(this.pointProgram);
    gl.bindVertexArray(this.vao);
    gl.uniformMatrix4fv(u.uViewProj!, false, viewProj);
    gl.uniform3f(u.uCamPos!, state.camPos[0], state.camPos[1], state.camPos[2]);
    gl.uniform1f(u.uTime!, state.time);
    gl.uniform1f(u.uStateA!, state.stateA);
    gl.uniform1f(u.uStateB!, state.stateB);
    gl.uniform1f(u.uBlend!, state.blend);
    gl.uniform1f(u.uStagger!, 0.42);
    gl.uniform1f(u.uPointSize!, state.pointSize);
    gl.uniform1f(u.uOpacity!, state.opacity);
    gl.uniform1f(u.uReveal!, state.reveal);
    gl.uniform1f(u.uTurbAmp!, state.scale * 0.02);
    gl.uniform1f(u.uFlowScale!, Math.max(state.scale, 0.5));
    gl.uniform1f(u.uExposure!, state.exposure);
    gl.uniform1f(u.uBlackHole!, state.blackHole);
    gl.uniform1f(u.uStreak!, state.streak);
    gl.uniform1f(u.uSwirl!, state.swirl);
    gl.uniform1f(u.uGather!, state.gather);
    gl.uniform1f(u.uBurst!, state.burst);
    gl.uniform1f(u.uParticleCount!, this.count);
    gl.uniform1f(u.uGlyphCount!, this.glyphCount);
    gl.uniform1f(u.uGlyphW!, this.glyphW);
    gl.uniform1f(u.uGlyphH!, this.glyphH);
    gl.uniform1f(u.uGlyphJitter!, this.glyphJitter);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.glyphTexture);
    gl.uniform1i(u.uGlyph!, 0);

    // Motion blur is needed both for the radial dolly and for the orbital
    // trails inside the accretion flow.
    const taps = state.streak > 0.004 || state.swirl > 0.004 ? 4 : 1;
    gl.uniform1f(u.uTaps!, taps);
    for (let tap = 0; tap < taps; tap++) {
      gl.uniform1f(u.uTapIndex!, tap);
      gl.drawArrays(gl.POINTS, 0, this.count);
    }

    // ---- pass 2: bright pass into quarter res ------------------------------
    gl.disable(gl.BLEND);
    gl.bindFramebuffer(gl.FRAMEBUFFER, bloomA.framebuffer);
    gl.viewport(0, 0, bloomA.width, bloomA.height);
    gl.useProgram(this.brightProgram);
    gl.bindVertexArray(this.quadVao);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, scene.texture);
    gl.uniform1i(this.brightUniforms.uScene!, 0);
    gl.uniform1f(this.brightUniforms.uThreshold!, state.bloom);
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    // ---- pass 3: separable blur, twice -------------------------------------
    gl.useProgram(this.blurProgram);
    const dirLoc = this.blurUniforms.uDirection!;
    const srcLoc = this.blurUniforms.uSource!;
    gl.uniform1i(srcLoc, 0);
    for (let i = 0; i < 2; i++) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, bloomB.framebuffer);
      gl.viewport(0, 0, bloomB.width, bloomB.height);
      gl.bindTexture(gl.TEXTURE_2D, bloomA.texture);
      gl.uniform2f(dirLoc, 1 / bloomA.width, 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);

      gl.bindFramebuffer(gl.FRAMEBUFFER, bloomA.framebuffer);
      gl.viewport(0, 0, bloomA.width, bloomA.height);
      gl.bindTexture(gl.TEXTURE_2D, bloomB.texture);
      gl.uniform2f(dirLoc, 0, 1 / bloomA.height);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    // ---- pass 4: composite -------------------------------------------------
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, this.width, this.height);
    gl.useProgram(this.compositeProgram);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, scene.texture);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, bloomA.texture);
    gl.uniform1i(this.compositeUniforms.uScene!, 0);
    gl.uniform1i(this.compositeUniforms.uBloom!, 1);
    gl.uniform1f(this.compositeUniforms.uBloomStrength!, 0.72);
    gl.uniform1f(this.compositeUniforms.uTime!, state.time * 60);
    gl.uniform2f(this.compositeUniforms.uResolution!, this.width, this.height);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindVertexArray(null);
    gl.activeTexture(gl.TEXTURE0);
    gl.finish();
  }

  dispose(): void {
    const gl = this.gl;
    for (const t of this.fbos) {
      gl.deleteTexture(t.texture);
      gl.deleteFramebuffer(t.framebuffer);
    }
    for (const b of this.buffers) gl.deleteBuffer(b);
    if (this.glyphTexture) gl.deleteTexture(this.glyphTexture);
    gl.deleteVertexArray(this.vao);
    gl.deleteVertexArray(this.quadVao);
    gl.deleteProgram(this.pointProgram);
    gl.deleteProgram(this.brightProgram);
    gl.deleteProgram(this.blurProgram);
    gl.deleteProgram(this.compositeProgram);
  }
}
