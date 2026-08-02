import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState
} from "react";
import { Application, Assets, Container, Sprite, Texture } from "pixi.js";


export interface ViewerControls {
  fit: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
}

interface PixiViewportProps {
  imageUrl: string;
  imageLabel: string;
  onZoomChange: (percent: number) => void;
}

interface CameraState {
  app: Application;
  content: Container;
  sprite: Sprite;
  fit: () => void;
  setScale: (scale: number) => void;
}

const MIN_SCALE = 0.05;
const MAX_SCALE = 16;

function webgl2Available(): boolean {
  try {
    return Boolean(document.createElement("canvas").getContext("webgl2"));
  } catch {
    return false;
  }
}

export const PixiViewport = forwardRef<ViewerControls, PixiViewportProps>(
  function PixiViewport({ imageUrl, imageLabel, onZoomChange }, ref) {
    const hostRef = useRef<HTMLDivElement>(null);
    const cameraRef = useRef<CameraState | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useImperativeHandle(ref, () => ({
      fit: () => cameraRef.current?.fit(),
      zoomIn: () => {
        const camera = cameraRef.current;
        if (camera) camera.setScale(camera.content.scale.x * 1.2);
      },
      zoomOut: () => {
        const camera = cameraRef.current;
        if (camera) camera.setScale(camera.content.scale.x / 1.2);
      }
    }), []);

    useEffect(() => {
      const host = hostRef.current;
      if (!host) return;
      const mount: HTMLDivElement = host;

      let disposed = false;
      let app: Application | null = null;
      let initialized = false;
      let texture: Texture | null = null;
      const abortController = new AbortController();

      setError(null);
      setLoading(true);

      async function initialize() {
        if (!webgl2Available()) {
          throw new Error("WebGL2 is unavailable on this device. Use the legacy grading view.");
        }

        const pixiApp = new Application();
        app = pixiApp;
        await pixiApp.init({
          resizeTo: mount,
          preference: "webgl",
          antialias: true,
          autoDensity: true,
          resolution: Math.min(window.devicePixelRatio || 1, 2),
          background: "#05070a"
        });
        initialized = true;
        if (disposed) {
          pixiApp.destroy({ removeView: true }, { children: true });
          app = null;
          return;
        }

        pixiApp.canvas.setAttribute("aria-label", imageLabel);
        pixiApp.canvas.setAttribute("role", "img");
        pixiApp.canvas.classList.add("grading-workbench-canvas");
        mount.appendChild(pixiApp.canvas);

        texture = await Assets.load<Texture>({
          src: imageUrl,
          parser: "loadTextures"
        });
        if (disposed) {
          await Assets.unload(imageUrl).catch(() => undefined);
          texture = null;
          return;
        }

        const content = new Container();
        const sprite = new Sprite(texture);
        content.addChild(sprite);
        pixiApp.stage.addChild(content);

        const reportZoom = () => onZoomChange(Math.round(content.scale.x * 100));
        const clampScale = (value: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, value));

        const setScaleAround = (nextScale: number, x?: number, y?: number) => {
          const scale = clampScale(nextScale);
          const pivotX = x ?? pixiApp.renderer.width / 2;
          const pivotY = y ?? pixiApp.renderer.height / 2;
          const localX = (pivotX - content.x) / content.scale.x;
          const localY = (pivotY - content.y) / content.scale.y;
          content.scale.set(scale);
          content.position.set(pivotX - localX * scale, pivotY - localY * scale);
          reportZoom();
        };

        const fit = () => {
          const availableWidth = Math.max(1, pixiApp.renderer.width);
          const availableHeight = Math.max(1, pixiApp.renderer.height);
          const scale = clampScale(
            Math.min(availableWidth / sprite.width, availableHeight / sprite.height) * 0.96
          );
          content.scale.set(scale);
          content.position.set(
            (availableWidth - sprite.width * scale) / 2,
            (availableHeight - sprite.height * scale) / 2
          );
          reportZoom();
        };

        cameraRef.current = {
          app: pixiApp,
          content,
          sprite,
          fit,
          setScale: setScaleAround
        };

        const wheel = (event: WheelEvent) => {
          event.preventDefault();
          const bounds = pixiApp.canvas.getBoundingClientRect();
          const x = (event.clientX - bounds.left) * (pixiApp.renderer.width / bounds.width);
          const y = (event.clientY - bounds.top) * (pixiApp.renderer.height / bounds.height);
          setScaleAround(content.scale.x * (event.deltaY < 0 ? 1.12 : 1 / 1.12), x, y);
        };

        let dragging = false;
        let lastX = 0;
        let lastY = 0;
        const pointerDown = (event: PointerEvent) => {
          if (event.button !== 0) return;
          dragging = true;
          lastX = event.clientX;
          lastY = event.clientY;
          pixiApp.canvas.setPointerCapture(event.pointerId);
          pixiApp.canvas.classList.add("is-panning");
        };
        const pointerMove = (event: PointerEvent) => {
          if (!dragging) return;
          const bounds = pixiApp.canvas.getBoundingClientRect();
          content.x += (event.clientX - lastX) * (pixiApp.renderer.width / bounds.width);
          content.y += (event.clientY - lastY) * (pixiApp.renderer.height / bounds.height);
          lastX = event.clientX;
          lastY = event.clientY;
        };
        const pointerUp = (event: PointerEvent) => {
          dragging = false;
          if (pixiApp.canvas.hasPointerCapture(event.pointerId)) {
            pixiApp.canvas.releasePointerCapture(event.pointerId);
          }
          pixiApp.canvas.classList.remove("is-panning");
        };

        pixiApp.canvas.addEventListener("wheel", wheel, { passive: false, signal: abortController.signal });
        pixiApp.canvas.addEventListener("pointerdown", pointerDown, { signal: abortController.signal });
        pixiApp.canvas.addEventListener("pointermove", pointerMove, { signal: abortController.signal });
        pixiApp.canvas.addEventListener("pointerup", pointerUp, { signal: abortController.signal });
        pixiApp.canvas.addEventListener("pointercancel", pointerUp, { signal: abortController.signal });

        fit();
        setLoading(false);
      }

      initialize().catch((reason: unknown) => {
        if (disposed) return;
        const message = reason instanceof Error ? reason.message : "Unable to initialize the image viewer.";
        setError(message);
        setLoading(false);
      });

      return () => {
        disposed = true;
        abortController.abort();
        cameraRef.current = null;
        if (texture) Assets.unload(imageUrl).catch(() => undefined);
        if (app && initialized) app.destroy({ removeView: true }, { children: true });
      };
    }, [imageLabel, imageUrl, onZoomChange]);

    return (
      <div className="grading-workbench-viewport" ref={hostRef}>
        {loading && <div className="grading-workbench-overlay" role="status">Loading image…</div>}
        {error && <div className="grading-workbench-overlay is-error" role="alert">{error}</div>}
      </div>
    );
  }
);
