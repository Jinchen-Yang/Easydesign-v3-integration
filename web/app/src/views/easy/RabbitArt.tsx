import { useEffect, useRef, useState } from 'react';
import type { RabbitStage } from './RabbitActor';
const ART = `${import.meta.env.BASE_URL}mascot/rabbit/rabbit-mascot.png`;
const PHASES = ['Idle', 'Target', 'Site', 'Design', 'Pilot', 'Scale', 'Candidates'];

// A continuous textured mesh bends the original PNG without cut seams, duplicate ears,
// a new face, or generated frames. GPU rendering here is only a tiny local UI canvas.
const VERTEX = `
attribute vec2 uv;
varying vec2 textureUV;
uniform float time;
uniform float phase;
vec2 turn(vec2 p, vec2 pivot, float angle) {
  float c=cos(angle), s=sin(angle); vec2 q=p-pivot;
  return pivot+vec2(c*q.x-s*q.y,s*q.x+c*q.y);
}
void main() {
  vec2 p=uv;
  float earY=smoothstep(.18,.30,uv.y)*(1.-smoothstep(.56,.615,uv.y));
  float left=(1.-smoothstep(.24,.315,uv.x))*earY;
  float right=smoothstep(.685,.76,uv.x)*earY;
  p=mix(p,turn(p,vec2(.32,.25),sin(time*3.1)*.22),left);
  p=mix(p,turn(p,vec2(.68,.25),sin(time*3.1+.7)*-.22),right);
  float head=1.-smoothstep(.48,.57,uv.y);
  float look=sin(time*2.)*.065;
  if(phase==1.) look=sin(time*2.8)*.09;
  p=mix(p,turn(p,vec2(.5,.52),look),head);
  vec2 paw=(uv-vec2(.687,.646))/vec2(.087,.09);
  float hand=exp(-dot(paw,paw)*2.);
  float speed=(phase==3.)?14.:((phase==6.)?9.:4.);
  p.y-=hand*(.02+.035*sin(time*speed));
  p.x+=hand*sin(time*speed)*.012;
  textureUV=uv;
  vec2 frame=(p*1254.+vec2(100.,150.))/1454.;
  gl_Position=vec4(frame.x*2.-1.,1.-frame.y*2.,0.,1.);
}`;
const FRAGMENT = `precision mediump float; varying vec2 textureUV; uniform sampler2D art; void main(){ gl_FragColor=texture2D(art,textureUV); }`;

export function RabbitArt({ stage, active }: { stage: RabbitStage; active: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const running = useRef(active);
  running.current = active;
  const [fallback, setFallback] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const gl = node.getContext('webgl', {
      alpha: true,
      premultipliedAlpha: false,
      antialias: true,
    });
    if (!gl) {
      setFallback(true);
      return;
    }
    let frame = 0,
      disposed = false,
      elapsed = 0,
      last = 0,
      lastPaint = -100;
    const shaders: WebGLShader[] = [];
    const compile = (type: number, source: string) => {
      const shader = gl.createShader(type)!;
      shaders.push(shader);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS))
        throw new Error('Rabbit shader unavailable');
      return shader;
    };
    const program = gl.createProgram()!;
    const buffer = gl.createBuffer();
    const texture = gl.createTexture();
    const image = new Image();
    const lost = (event: Event) => {
      event.preventDefault();
      setFallback(true);
      cancelAnimationFrame(frame);
    };
    node.addEventListener('webglcontextlost', lost);
    const dispose = () => {
      disposed = true;
      cancelAnimationFrame(frame);
      image.onload = null;
      image.onerror = null;
      node.removeEventListener('webglcontextlost', lost);
      gl.deleteTexture(texture);
      gl.deleteBuffer(buffer);
      gl.deleteProgram(program);
      shaders.forEach((shader) => gl.deleteShader(shader));
    };
    try {
      gl.attachShader(program, compile(gl.VERTEX_SHADER, VERTEX));
      gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAGMENT));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS))
        throw new Error('Rabbit renderer unavailable');
      gl.useProgram(program);
      const vertices: number[] = [];
      const count = 48;
      for (let y = 0; y < count; y++)
        for (let x = 0; x < count; x++) {
          const l = x / count,
            r = (x + 1) / count,
            t = y / count,
            b = (y + 1) / count;
          vertices.push(l, t, r, t, l, b, r, t, r, b, l, b);
        }
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);
      const uv = gl.getAttribLocation(program, 'uv');
      gl.enableVertexAttribArray(uv);
      gl.vertexAttribPointer(uv, 2, gl.FLOAT, false, 0, 0);
      gl.uniform1f(gl.getUniformLocation(program, 'phase'), PHASES.indexOf(stage));
      const clock = gl.getUniformLocation(program, 'time');
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      image.onload = () => {
        if (disposed) return;
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
        const draw = (now: number) => {
          if (disposed) return;
          const delta = last ? Math.min(50, now - last) : 0;
          last = now;
          if (running.current) elapsed += delta;
          if (lastPaint < 0 || (running.current && now - lastPaint >= 32)) {
            const size = Math.min(
              512,
              Math.max(200, Math.round(node.getBoundingClientRect().width * devicePixelRatio)),
            );
            if (node.width !== size) {
              node.width = size;
              node.height = size;
            }
            gl.viewport(0, 0, node.width, node.height);
            gl.clearColor(0, 0, 0, 0);
            gl.clear(gl.COLOR_BUFFER_BIT);
            gl.uniform1f(clock, elapsed / 1000);
            gl.drawArrays(gl.TRIANGLES, 0, vertices.length / 2);
            node.dataset.frame = String(Math.round(elapsed));
            lastPaint = now;
          }
          frame = requestAnimationFrame(draw);
        };
        frame = requestAnimationFrame(draw);
      };
      image.onerror = () => {
        if (!disposed) setFailed(true);
      };
      image.src = ART;
    } catch {
      setFallback(true);
    }
    return dispose;
  }, [stage]);
  if (failed) return <span className="rabbit-fallback">🐰</span>;
  if (fallback)
    return (
      <img
        className="rabbit-original-fallback"
        src={ART}
        alt=""
        draggable="false"
        onError={() => setFailed(true)}
      />
    );
  return <canvas ref={canvas} className="rabbit-mesh" aria-hidden="true" />;
}
