import { useEffect, useRef } from "react";
import * as THREE from "three";
import { usePageTransition } from "./PageTransitionContext";

/**
 * Full-viewport Three.js canvas that renders a flip-clock page transition.
 * - Captures the current page via html2canvas-style approach (actually uses
 *   a CSS snapshot rendered into a canvas texture).
 * - Flips the captured texture out (rotateX 0→-90 for "down", 0→+90 for "up"),
 *   then flips the new page in (90→0 or -90→0).
 * - Sits as a fixed overlay; pointer-events:none when idle.
 */
export function FlipTransition({ appRef }: { appRef: React.RefObject<HTMLElement | null> }) {
  const { flipping, flipDirection, endFlip } = usePageTransition();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.OrthographicCamera | null>(null);
  const meshRef = useRef<THREE.Mesh | null>(null);
  const rafRef = useRef(0);
  const snapshotTexRef = useRef<THREE.CanvasTexture | null>(null);
  const newPageTexRef = useRef<THREE.CanvasTexture | null>(null);
  const phaseRef = useRef<"idle" | "out" | "in">("idle");
  const angleRef = useRef(0);
  const dirRef = useRef<1 | -1>(1); // +1 = flip down (out goes -90), -1 = flip up (out goes +90)

  // Bootstrap Three.js once
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(window.innerWidth, window.innerHeight);
    rendererRef.current = renderer;

    const scene = new THREE.Scene();
    sceneRef.current = scene;

    const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
    cam.position.z = 1;
    cameraRef.current = cam;

    const geo = new THREE.PlaneGeometry(2, 2);
    const mat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0 });
    const mesh = new THREE.Mesh(geo, mat);
    scene.add(mesh);
    meshRef.current = mesh;

    const onResize = () => {
      renderer.setSize(window.innerWidth, window.innerHeight);
    };
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(rafRef.current);
      renderer.dispose();
    };
  }, []);

  // Trigger flip when `flipping` becomes true
  useEffect(() => {
    if (!flipping) return;

    const app = appRef.current;
    const mesh = meshRef.current;
    const renderer = rendererRef.current;
    const scene = sceneRef.current;
    const cam = cameraRef.current;
    if (!app || !mesh || !renderer || !scene || !cam) return;

    // Capture current page into an offscreen canvas
    const w = window.innerWidth;
    const h = window.innerHeight;
    const offscreen = document.createElement("canvas");
    offscreen.width = w;
    offscreen.height = h;
    const ctx2d = offscreen.getContext("2d");
    if (!ctx2d) return;

    // Draw a solid background matching --bg
    const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() || "#0f1117";
    ctx2d.fillStyle = bg;
    ctx2d.fillRect(0, 0, w, h);

    // Snapshot via foreignObject SVG trick
    const svgData = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
      <foreignObject width="100%" height="100%">
        <div xmlns="http://www.w3.org/1999/xhtml" style="width:${w}px;height:${h}px;overflow:hidden;">
          ${app.outerHTML}
        </div>
      </foreignObject>
    </svg>`;

    const img = new Image();
    const blob = new Blob([svgData], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);

    img.onload = () => {
      ctx2d.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);

      const tex = new THREE.CanvasTexture(offscreen);
      snapshotTexRef.current = tex;

      const mat = mesh.material as THREE.MeshBasicMaterial;
      mat.map = tex;
      mat.opacity = 1;
      mat.needsUpdate = true;

      dirRef.current = flipDirection === "down" ? 1 : -1;
      phaseRef.current = "out";
      angleRef.current = 0;
      mesh.rotation.x = 0;

      cancelAnimationFrame(rafRef.current);
      animate();
    };

    img.onerror = () => {
      URL.revokeObjectURL(url);
      // Fallback: skip visual, just end
      endFlip();
    };

    img.src = url;

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flipping]);

  function animate() {
    const mesh = meshRef.current;
    const renderer = rendererRef.current;
    const scene = sceneRef.current;
    const cam = cameraRef.current;
    if (!mesh || !renderer || !scene || !cam) return;

    const SPEED = Math.PI / 0.42; // radians per second → ~420ms per half
    const dt = 1 / 60;

    const tick = () => {
      angleRef.current += SPEED * dt;
      const mat = mesh.material as THREE.MeshBasicMaterial;

      if (phaseRef.current === "out") {
        // Rotate from 0 → -π/2 (flip down) or 0 → +π/2 (flip up)
        const target = (Math.PI / 2) * dirRef.current;
        mesh.rotation.x = (angleRef.current / (Math.PI / 2)) * target;

        if (angleRef.current >= Math.PI / 2) {
          // Halfway: swap to new page texture if available, else just transparent
          mesh.rotation.x = target;
          mat.opacity = 0;
          mat.needsUpdate = true;

          // Signal that the route can now render the new page
          // (startFlip already resolved at 420ms; here we start the in-phase)
          phaseRef.current = "in";
          angleRef.current = 0;

          // Capture new page after a brief paint delay
          setTimeout(() => captureNewPage(), 80);
        }
      } else if (phaseRef.current === "in") {
        const startAngle = -(Math.PI / 2) * dirRef.current;
        mesh.rotation.x = startAngle + (angleRef.current / (Math.PI / 2)) * (-startAngle);
        mat.opacity = Math.min(1, angleRef.current / (Math.PI / 2));
        mat.needsUpdate = true;

        if (angleRef.current >= Math.PI / 2) {
          mesh.rotation.x = 0;
          mat.opacity = 0; // Reveal real page
          mat.needsUpdate = true;
          phaseRef.current = "idle";
          renderer.render(scene, cam);
          endFlip();
          return;
        }
      }

      renderer.render(scene, cam);
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
  }

  function captureNewPage() {
    const app = appRef.current;
    const mesh = meshRef.current;
    if (!app || !mesh) return;

    const w = window.innerWidth;
    const h = window.innerHeight;
    const offscreen = document.createElement("canvas");
    offscreen.width = w;
    offscreen.height = h;
    const ctx2d = offscreen.getContext("2d");
    if (!ctx2d) return;

    const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() || "#0f1117";
    ctx2d.fillStyle = bg;
    ctx2d.fillRect(0, 0, w, h);

    const svgData = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
      <foreignObject width="100%" height="100%">
        <div xmlns="http://www.w3.org/1999/xhtml" style="width:${w}px;height:${h}px;overflow:hidden;">
          ${app.outerHTML}
        </div>
      </foreignObject>
    </svg>`;

    const img = new Image();
    const blob = new Blob([svgData], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);

    img.onload = () => {
      ctx2d.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);

      snapshotTexRef.current?.dispose();
      const tex = new THREE.CanvasTexture(offscreen);
      newPageTexRef.current = tex;

      const mat = mesh.material as THREE.MeshBasicMaterial;
      mat.map = tex;
      mat.opacity = 0;
      mat.needsUpdate = true;
    };

    img.onerror = () => URL.revokeObjectURL(url);
    img.src = url;
  }

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        pointerEvents: "none",
        display: flipping ? "block" : "none",
      }}
    />
  );
}
