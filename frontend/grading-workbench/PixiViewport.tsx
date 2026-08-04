import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState
} from "react";
import {
  Application,
  Assets,
  Container,
  Graphics,
  Sprite,
  Text,
  Texture
} from "pixi.js";

import { makeClinicalImageFilters } from "./ClinicalImageFilter";
import type { ImageAnalysis } from "./imageAnalysis";
import {
  annotationBounds,
  annotationColor,
  annotationContainsPoint,
  eraseBrushMask,
  geometryControlPoints,
  moveGeometry,
  rotateGeometry,
  scaleGeometry,
  type AnnotationClassRef,
  type AnnotationGeometry,
  type Point,
  type ViewerFilters,
  type WorkbenchAnnotation
} from "./workbenchState";
import type { ToolKey } from "./workspace";

export interface ViewerControls {
  fit: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  setZoom: (percent: number) => void;
}

interface PixiViewportProps {
  imageUrl: string;
  imageLabel: string;
  activeTool: ToolKey | null;
  transformEnabled: boolean;
  eraserEnabled: boolean;
  activeClass: AnnotationClassRef | null;
  annotations: WorkbenchAnnotation[];
  selectedAnnotationId: string | null;
  viewerFilters: ViewerFilters;
  imageAnalysis: ImageAnalysis | null;
  loupeEnabled: boolean;
  brushSize: number;
  eraserSize: number;
  onCreateAnnotation: (geometry: AnnotationGeometry) => void;
  onSelectAnnotation: (annotationId: string | null) => void;
  onDuplicateAnnotation: (annotationId: string) => void;
  onDeleteAnnotation: (annotationId: string) => void;
  onUpdateAnnotationGeometry: (annotationId: string, geometry: AnnotationGeometry) => void;
  onToggleAnnotationLock: (annotationId: string) => void;
  onExitToPan: () => void;
  onZoomChange: (percent: number) => void;
}

interface CameraState {
  app: Application;
  content: Container;
  sprite: Sprite;
  annotationLayer: Container;
  preview: Graphics;
  loupeLayer: Container;
  loupeSprite: Sprite;
  loupeMask: Graphics;
  loupeBorder: Graphics;
  fit: () => void;
  setScale: (scale: number, x?: number, y?: number) => void;
  updateSelectionAnchor: () => void;
}

interface DrawingState {
  tool: ToolKey;
  start: Point;
  current: Point;
  points: Point[];
  pointerId: number | null;
}

interface TransformState {
  annotationId: string;
  kind: "move" | "resize" | "rotate" | "erase";
  original: AnnotationGeometry;
  start: Point;
  current: Point;
  center: Point;
  handleIndex?: number;
  eraserPath?: Point[];
}

const MIN_SCALE = 0.05;
const MAX_SCALE = 16;
const LOUPE_RADIUS = 72;
const LOUPE_MAGNIFICATION = 2.4;

function webgl2Available(): boolean {
  try {
    return Boolean(document.createElement("canvas").getContext("webgl2"));
  } catch {
    return false;
  }
}

function clampPoint(point: Point, sprite: Sprite): Point {
  return [
    Math.min(sprite.width, Math.max(0, point[0])),
    Math.min(sprite.height, Math.max(0, point[1]))
  ];
}

function screenToImage(event: PointerEvent, camera: CameraState): Point {
  const bounds = camera.app.canvas.getBoundingClientRect();
  const screenX = (event.clientX - bounds.left) * (camera.app.renderer.width / bounds.width);
  const screenY = (event.clientY - bounds.top) * (camera.app.renderer.height / bounds.height);
  return clampPoint([
    (screenX - camera.content.x) / camera.content.scale.x,
    (screenY - camera.content.y) / camera.content.scale.y
  ], camera.sprite);
}

function normalizedRect(start: Point, end: Point) {
  const x = Math.min(start[0], end[0]);
  const y = Math.min(start[1], end[1]);
  return { x, y, width: Math.abs(end[0] - start[0]), height: Math.abs(end[1] - start[1]) };
}

function pyramidPoints(start: Point, end: Point): Point[] {
  const rect = normalizedRect(start, end);
  return [
    [rect.x + rect.width / 2, rect.y],
    [rect.x + rect.width, rect.y + rect.height * 0.34],
    [rect.x + rect.width, rect.y + rect.height],
    [rect.x, rect.y + rect.height],
    [rect.x, rect.y + rect.height * 0.34]
  ];
}

function drawGeometry(
  graphic: Graphics,
  geometry: AnnotationGeometry,
  color: number,
  selected: boolean,
  alpha = 1,
  editable = true
) {
  const width = selected ? 3 : 2;
  if (geometry.type === "box" || geometry.type === "rect") {
    const corners = geometryControlPoints(geometry);
    const shape = geometry.type === "rect" && geometry.rotation
      ? graphic.poly(corners.flat())
      : graphic.rect(geometry.x, geometry.y, geometry.width, geometry.height);
    shape
      .fill({ color, alpha: geometry.type === "rect" ? 0.12 * alpha : 0.04 * alpha })
      .stroke({ color, width, alpha });
  } else if (geometry.type === "ellipse") {
    const cx = geometry.x + geometry.width / 2;
    const cy = geometry.y + geometry.height / 2;
    const rotation = geometry.rotation ?? 0;
    const cosine = Math.cos(rotation);
    const sine = Math.sin(rotation);
    const points: number[] = [];
    for (let index = 0; index < 48; index += 1) {
      const angle = index / 48 * Math.PI * 2;
      const dx = Math.cos(angle) * geometry.width / 2;
      const dy = Math.sin(angle) * geometry.height / 2;
      points.push(cx + dx * cosine - dy * sine, cy + dx * sine + dy * cosine);
    }
    graphic.poly(points).fill({ color, alpha: 0.1 * alpha }).stroke({ color, width, alpha });
  } else if (geometry.type === "polygon" || geometry.type === "pyramid") {
    if (geometry.points.length > 1) {
      graphic.poly(geometry.points.flat()).fill({ color, alpha: 0.1 * alpha }).stroke({ color, width, alpha });
    }
  } else {
    for (const stroke of geometry.strokes) {
      if (stroke.length < 2) continue;
      graphic.moveTo(stroke[0][0], stroke[0][1]);
      for (const point of stroke.slice(1)) graphic.lineTo(point[0], point[1]);
      graphic.stroke({ color, width: geometry.size, alpha: 0.36 * alpha, cap: "round", join: "round" });
    }
  }

  if (selected && editable) {
    const handles = geometryControlPoints(geometry);
    for (const [x, y] of handles) {
      graphic.circle(x, y, 4).fill({ color: 0xffffff }).stroke({ color, width: 2 });
    }
    if (geometry.type !== "box") {
      const bounds = annotationBounds(geometry);
      const centerX = bounds.x + bounds.width / 2;
      const topY = bounds.y;
      const rotateY = topY - 24;
      graphic.moveTo(centerX, topY).lineTo(centerX, rotateY).stroke({ color, width: 1.5, alpha: 0.8 });
      graphic.circle(centerX, rotateY, 5).fill({ color: 0x101318 }).stroke({ color, width: 2 });
    }
  }
}

export const PixiViewport = forwardRef<ViewerControls, PixiViewportProps>(
  function PixiViewport(props, ref) {
    const {
      imageUrl,
      imageLabel,
      annotations,
      selectedAnnotationId,
      viewerFilters,
      loupeEnabled,
      onZoomChange
    } = props;
    const hostRef = useRef<HTMLDivElement>(null);
    const cameraRef = useRef<CameraState | null>(null);
    const propsRef = useRef(props);
    const drawingRef = useRef<DrawingState | null>(null);
    const transformRef = useRef<TransformState | null>(null);
    const hoveredAnnotationRef = useRef<string | null>(null);
    const preferredTransformRef = useRef<"move" | "rotate" | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [actionAnchor, setActionAnchor] = useState<{ annotationId: string; left: number; top: number } | null>(null);

    useEffect(() => { propsRef.current = props; }, [props]);

    useImperativeHandle(ref, () => ({
      fit: () => cameraRef.current?.fit(),
      zoomIn: () => {
        const camera = cameraRef.current;
        if (camera) camera.setScale(camera.content.scale.x * 1.2);
      },
      zoomOut: () => {
        const camera = cameraRef.current;
        if (camera) camera.setScale(camera.content.scale.x / 1.2);
      },
      setZoom: (percent: number) => cameraRef.current?.setScale(percent / 100)
    }), []);

    useEffect(() => {
      const camera = cameraRef.current;
      if (!camera) return;
      for (const child of camera.annotationLayer.removeChildren()) child.destroy();
      annotations.forEach((annotation, index) => {
        if (!annotation.visible) return;
        const graphic = new Graphics();
        graphic.label = annotation.id;
        drawGeometry(
          graphic,
          annotation.geometry,
          annotationColor(annotation.classRef),
          annotation.id === selectedAnnotationId,
          annotation.locked ? 0.55 : 1,
          !annotation.locked
        );
        const bounds = annotationBounds(annotation.geometry);
        const badge = new Graphics().circle(bounds.x, bounds.y, 12).fill({ color: 0x101318, alpha: 0.94 }).stroke({ color: annotationColor(annotation.classRef), width: 2 });
        const number = new Text({ text: String(index + 1), style: { fill: 0xffffff, fontFamily: "Inter, sans-serif", fontSize: 14, fontWeight: "700" } });
        number.anchor.set(0.5);
        number.position.set(bounds.x, bounds.y);
        camera.annotationLayer.addChild(graphic, badge, number);
      });
      camera.updateSelectionAnchor();
    }, [annotations, selectedAnnotationId]);

    useEffect(() => {
      const camera = cameraRef.current;
      if (!camera) return;
      camera.sprite.filters = makeClinicalImageFilters(viewerFilters, props.imageAnalysis);
      camera.loupeSprite.filters = makeClinicalImageFilters(viewerFilters, props.imageAnalysis);
    }, [props.imageAnalysis, viewerFilters]);

    useEffect(() => {
      const camera = cameraRef.current;
      if (!camera) return;
      camera.loupeLayer.visible = loupeEnabled;
    }, [loupeEnabled]);

    useEffect(() => {
      const host = hostRef.current;
      if (!host) return;
      const mount = host;
      let disposed = false;
      let app: Application | null = null;
      let initialized = false;
      let texture: Texture | null = null;
      const abortController = new AbortController();
      setError(null);
      setLoading(true);

      async function initialize() {
        if (!webgl2Available()) throw new Error("WebGL2 is unavailable on this device. Use the legacy grading view.");
        const pixiApp = new Application();
        app = pixiApp;
        await pixiApp.init({
          resizeTo: mount,
          preference: "webgl",
          antialias: true,
          autoDensity: true,
          resolution: Math.min(window.devicePixelRatio || 1, 2),
          background: "#07090d"
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

        texture = await Assets.load<Texture>({ src: imageUrl, parser: "loadTextures" });
        if (disposed) {
          await Assets.unload(imageUrl).catch(() => undefined);
          texture = null;
          return;
        }

        const content = new Container();
        const sprite = new Sprite(texture);
        const annotationLayer = new Container();
        const preview = new Graphics();
        content.addChild(sprite, annotationLayer, preview);
        pixiApp.stage.addChild(content);

        const loupeLayer = new Container();
        const loupeSprite = new Sprite(texture);
        const loupeMask = new Graphics();
        const loupeBorder = new Graphics();
        loupeSprite.mask = loupeMask;
        loupeLayer.addChild(loupeSprite, loupeMask, loupeBorder);
        loupeLayer.visible = propsRef.current.loupeEnabled;
        pixiApp.stage.addChild(loupeLayer);

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
          cameraRef.current?.updateSelectionAnchor();
        };
        const fit = () => {
          const availableWidth = Math.max(1, pixiApp.renderer.width);
          const availableHeight = Math.max(1, pixiApp.renderer.height);
          const scale = clampScale(Math.min(availableWidth / sprite.width, availableHeight / sprite.height) * 0.96);
          content.scale.set(scale);
          content.position.set((availableWidth - sprite.width * scale) / 2, (availableHeight - sprite.height * scale) / 2);
          reportZoom();
          cameraRef.current?.updateSelectionAnchor();
        };
        const camera: CameraState = {
          app: pixiApp,
          content,
          sprite,
          annotationLayer,
          preview,
          loupeLayer,
          loupeSprite,
          loupeMask,
          loupeBorder,
          fit,
          setScale: setScaleAround,
          updateSelectionAnchor: () => undefined
        };
        camera.updateSelectionAnchor = () => {
          const annotationId = hoveredAnnotationRef.current ?? propsRef.current.selectedAnnotationId;
          const selected = propsRef.current.annotations.find((annotation) => annotation.id === annotationId && annotation.visible);
          if (!selected) { setActionAnchor(null); return; }
          const geometry = annotationBounds(selected.geometry);
          const canvasBounds = pixiApp.canvas.getBoundingClientRect();
          const rendererX = content.x + (geometry.x + geometry.width / 2) * content.scale.x;
          const rendererY = content.y + (geometry.y + geometry.height) * content.scale.y;
          const left = rendererX * canvasBounds.width / pixiApp.renderer.width;
          const top = rendererY * canvasBounds.height / pixiApp.renderer.height + 9;
          if (left < -20 || left > canvasBounds.width + 20 || top < -20 || top > canvasBounds.height + 20) { setActionAnchor(null); return; }
          setActionAnchor({ annotationId: selected.id, left: Math.min(canvasBounds.width - 112, Math.max(112, left)), top: Math.min(canvasBounds.height - 42, Math.max(6, top)) });
        };
        cameraRef.current = camera;
        sprite.filters = makeClinicalImageFilters(propsRef.current.viewerFilters, propsRef.current.imageAnalysis);
        loupeSprite.filters = makeClinicalImageFilters(propsRef.current.viewerFilters, propsRef.current.imageAnalysis);

        const updateLoupe = (event: PointerEvent) => {
          if (!propsRef.current.loupeEnabled) return;
          const bounds = pixiApp.canvas.getBoundingClientRect();
          const sx = (event.clientX - bounds.left) * (pixiApp.renderer.width / bounds.width);
          const sy = (event.clientY - bounds.top) * (pixiApp.renderer.height / bounds.height);
          const imageX = (sx - content.x) / content.scale.x;
          const imageY = (sy - content.y) / content.scale.y;
          const scale = content.scale.x * LOUPE_MAGNIFICATION;
          loupeSprite.scale.set(scale);
          loupeSprite.position.set(sx - imageX * scale, sy - imageY * scale);
          loupeMask.clear().circle(sx, sy, LOUPE_RADIUS).fill({ color: 0xffffff });
          loupeBorder.clear().circle(sx, sy, LOUPE_RADIUS).stroke({ color: 0xffffff, width: 2, alpha: 0.9 });
        };

        const renderPreview = () => {
          preview.clear();
          const drawing = drawingRef.current;
          if (!drawing) return;
          const color = propsRef.current.activeClass ? annotationColor(propsRef.current.activeClass) : 0x2dd4bf;
          if (drawing.tool === "polygon") {
            const points = [...drawing.points, drawing.current];
            if (points.length > 1) {
              preview.moveTo(points[0][0], points[0][1]);
              for (const point of points.slice(1)) preview.lineTo(point[0], point[1]);
              preview.stroke({ color, width: 2, alpha: 0.9 });
            }
            for (const point of drawing.points) preview.circle(point[0], point[1], 3).fill({ color });
          } else if (drawing.tool === "brush_mask") {
            drawGeometry(preview, { type: "brush_mask", strokes: [drawing.points], size: propsRef.current.brushSize }, color, true, 0.8, false);
          } else if (drawing.tool === "pyramid") {
            drawGeometry(preview, { type: "pyramid", points: pyramidPoints(drawing.start, drawing.current) }, color, true, 0.8, false);
          } else {
            const rect = normalizedRect(drawing.start, drawing.current);
            drawGeometry(preview, { type: drawing.tool, ...rect }, color, true, 0.8, false);
          }
        };

        const completeDrawing = () => {
          const drawing = drawingRef.current;
          if (!drawing) return;
          let geometry: AnnotationGeometry | null = null;
          if (drawing.tool === "polygon") {
            if (drawing.points.length >= 3) geometry = { type: "polygon", points: drawing.points };
          } else if (drawing.tool === "brush_mask") {
            if (drawing.points.length >= 2) geometry = { type: "brush_mask", strokes: [drawing.points], size: propsRef.current.brushSize };
          } else if (drawing.tool === "pyramid") {
            const rect = normalizedRect(drawing.start, drawing.current);
            if (rect.width >= 3 && rect.height >= 3) geometry = { type: "pyramid", points: pyramidPoints(drawing.start, drawing.current) };
          } else {
            const rect = normalizedRect(drawing.start, drawing.current);
            if (rect.width >= 3 && rect.height >= 3) geometry = { type: drawing.tool, ...rect };
          }
          drawingRef.current = null;
          preview.clear();
          if (geometry) propsRef.current.onCreateAnnotation(geometry);
        };

        const transformGeometry = (transform: TransformState): AnnotationGeometry | null => {
          if (transform.kind === "move") {
            return moveGeometry(transform.original, transform.current[0] - transform.start[0], transform.current[1] - transform.start[1]);
          }
          if (transform.kind === "rotate") {
            const startAngle = Math.atan2(transform.start[1] - transform.center[1], transform.start[0] - transform.center[0]);
            const currentAngle = Math.atan2(transform.current[1] - transform.center[1], transform.current[0] - transform.center[0]);
            return rotateGeometry(transform.original, transform.center, currentAngle - startAngle);
          }
          if (transform.kind === "erase" && transform.original.type === "brush_mask") {
            return eraseBrushMask(transform.original, transform.eraserPath ?? [transform.current], propsRef.current.eraserSize / 2);
          }
          const controls = geometryControlPoints(transform.original);
          const handleIndex = transform.handleIndex ?? 2;
          if (transform.original.type === "box") {
            const fixed = controls[(handleIndex + 2) % 4];
            const moving = controls[handleIndex];
            const scaleX = Math.max(0.05, Math.abs((transform.current[0] - fixed[0]) / (moving[0] - fixed[0] || 1)));
            const scaleY = Math.max(0.05, Math.abs((transform.current[1] - fixed[1]) / (moving[1] - fixed[1] || 1)));
            return scaleGeometry(transform.original, fixed, scaleX, scaleY);
          }
          const startDistance = Math.max(1, Math.hypot(transform.start[0] - transform.center[0], transform.start[1] - transform.center[1]));
          const currentDistance = Math.max(3, Math.hypot(transform.current[0] - transform.center[0], transform.current[1] - transform.center[1]));
          const ratio = Math.max(0.05, currentDistance / startDistance);
          return scaleGeometry(transform.original, transform.center, ratio, ratio);
        };

        const renderTransformPreview = () => {
          const transform = transformRef.current;
          if (!transform) return;
          preview.clear();
          const annotation = propsRef.current.annotations.find((item) => item.id === transform.annotationId);
          if (!annotation) return;
          const geometry = transformGeometry(transform);
          if (geometry) drawGeometry(preview, geometry, annotationColor(annotation.classRef), true, 0.9, true);
          if (transform.kind === "erase") {
            preview.circle(transform.current[0], transform.current[1], propsRef.current.eraserSize / 2).stroke({ color: 0xffffff, width: 2, alpha: 0.9 });
          }
        };

        const completeTransform = () => {
          const transform = transformRef.current;
          if (!transform) return;
          const geometry = transformGeometry(transform);
          transformRef.current = null;
          preview.clear();
          if (geometry) propsRef.current.onUpdateAnnotationGeometry(transform.annotationId, geometry);
          else propsRef.current.onDeleteAnnotation(transform.annotationId);
        };

        const wheel = (event: WheelEvent) => {
          event.preventDefault();
          const bounds = pixiApp.canvas.getBoundingClientRect();
          const x = (event.clientX - bounds.left) * (pixiApp.renderer.width / bounds.width);
          const y = (event.clientY - bounds.top) * (pixiApp.renderer.height / bounds.height);
          setScaleAround(content.scale.x * (event.deltaY < 0 ? 1.12 : 1 / 1.12), x, y);
        };
        let panning = false;
        let lastX = 0;
        let lastY = 0;
        const pointerDown = (event: PointerEvent) => {
          if (event.button !== 0) return;
          const point = screenToImage(event, camera);
          const tolerance = 9 / content.scale.x;
          const selected = propsRef.current.annotations.find((annotation) => annotation.id === propsRef.current.selectedAnnotationId);
          if (propsRef.current.eraserEnabled && selected?.geometry.type === "brush_mask" && !selected.locked) {
            const bounds = annotationBounds(selected.geometry);
            transformRef.current = { annotationId: selected.id, kind: "erase", original: selected.geometry, start: point, current: point, center: [bounds.x + bounds.width / 2, bounds.y + bounds.height / 2], eraserPath: [point] };
            pixiApp.canvas.setPointerCapture(event.pointerId);
            pixiApp.canvas.classList.add("is-erasing");
            renderTransformPreview();
            return;
          }
          if (propsRef.current.transformEnabled) {
            const hit = [...propsRef.current.annotations].reverse().find((annotation) => annotationContainsPoint(annotation, point, tolerance));
            if (selected) {
              const bounds = annotationBounds(selected.geometry);
              const center: Point = [bounds.x + bounds.width / 2, bounds.y + bounds.height / 2];
              const controls = geometryControlPoints(selected.geometry);
              const handleIndex = controls.findIndex((control) => Math.hypot(point[0] - control[0], point[1] - control[1]) <= tolerance);
              const rotationPoint: Point = [center[0], bounds.y - 24];
              const rotateHit = selected.geometry.type !== "box" && Math.hypot(point[0] - rotationPoint[0], point[1] - rotationPoint[1]) <= tolerance;
              const preferred = preferredTransformRef.current;
              if (selected.id === hit?.id || handleIndex >= 0 || rotateHit) {
                if (selected.locked) return;
                const kind: TransformState["kind"] = preferred === "rotate" && selected.geometry.type !== "box"
                  ? "rotate"
                  : preferred === "move"
                    ? "move"
                    : rotateHit
                      ? "rotate"
                      : handleIndex >= 0
                        ? "resize"
                        : "move";
                preferredTransformRef.current = null;
                transformRef.current = { annotationId: selected.id, kind, original: selected.geometry, start: point, current: point, center, handleIndex: handleIndex >= 0 ? handleIndex : undefined };
                pixiApp.canvas.setPointerCapture(event.pointerId);
                pixiApp.canvas.classList.add("is-transforming");
                return;
              }
            }
            propsRef.current.onSelectAnnotation(hit?.id ?? null);
            preferredTransformRef.current = null;
            return;
          }
          const tool = propsRef.current.activeTool;
          const annotationClass = propsRef.current.activeClass;
          if (tool && annotationClass) {
            if (tool === "polygon") {
              if (drawingRef.current?.tool === "polygon") {
                drawingRef.current.points.push(point);
                drawingRef.current.current = point;
              } else {
                drawingRef.current = { tool, start: point, current: point, points: [point], pointerId: null };
              }
              renderPreview();
              return;
            }
            drawingRef.current = { tool, start: point, current: point, points: [point], pointerId: event.pointerId };
            pixiApp.canvas.setPointerCapture(event.pointerId);
            pixiApp.canvas.classList.add("is-drawing");
            return;
          }
          panning = true;
          lastX = event.clientX;
          lastY = event.clientY;
          pixiApp.canvas.setPointerCapture(event.pointerId);
          pixiApp.canvas.classList.add("is-panning");
        };
        const pointerMove = (event: PointerEvent) => {
          updateLoupe(event);
          const drawing = drawingRef.current;
          const transform = transformRef.current;
          if (transform) {
            const point = screenToImage(event, camera);
            transform.current = point;
            if (transform.kind === "erase") transform.eraserPath?.push(point);
            renderTransformPreview();
            return;
          }
          if (drawing) {
            const point = screenToImage(event, camera);
            drawing.current = point;
            if (drawing.tool === "brush_mask" && drawing.pointerId !== null) drawing.points.push(point);
            renderPreview();
            return;
          }
          if (!panning) {
            const point = screenToImage(event, camera);
            const hovered = [...propsRef.current.annotations].reverse().find((annotation) => annotationContainsPoint(annotation, point, 7 / content.scale.x));
            const nextHovered = hovered?.id ?? null;
            if (hoveredAnnotationRef.current !== nextHovered) {
              hoveredAnnotationRef.current = nextHovered;
              camera.updateSelectionAnchor();
            }
            return;
          }
          const bounds = pixiApp.canvas.getBoundingClientRect();
          content.x += (event.clientX - lastX) * (pixiApp.renderer.width / bounds.width);
          content.y += (event.clientY - lastY) * (pixiApp.renderer.height / bounds.height);
          lastX = event.clientX;
          lastY = event.clientY;
          camera.updateSelectionAnchor();
        };
        const pointerUp = (event: PointerEvent) => {
          if (drawingRef.current && drawingRef.current.tool !== "polygon") completeDrawing();
          if (transformRef.current) completeTransform();
          panning = false;
          if (pixiApp.canvas.hasPointerCapture(event.pointerId)) pixiApp.canvas.releasePointerCapture(event.pointerId);
          pixiApp.canvas.classList.remove("is-panning", "is-drawing", "is-transforming", "is-erasing");
        };
        const doubleClick = () => {
          if (drawingRef.current?.tool === "polygon") completeDrawing();
        };
        const keyDown = (event: KeyboardEvent) => {
          if (event.key === "Escape") {
            drawingRef.current = null;
            transformRef.current = null;
            hoveredAnnotationRef.current = null;
            preview.clear();
            propsRef.current.onExitToPan();
          } else if (event.key === "Enter" && drawingRef.current?.tool === "polygon") {
            completeDrawing();
          }
        };
        pixiApp.canvas.addEventListener("wheel", wheel, { passive: false, signal: abortController.signal });
        pixiApp.canvas.addEventListener("pointerdown", pointerDown, { signal: abortController.signal });
        pixiApp.canvas.addEventListener("pointermove", pointerMove, { signal: abortController.signal });
        pixiApp.canvas.addEventListener("pointerup", pointerUp, { signal: abortController.signal });
        pixiApp.canvas.addEventListener("pointercancel", pointerUp, { signal: abortController.signal });
        pixiApp.canvas.addEventListener("dblclick", doubleClick, { signal: abortController.signal });
        window.addEventListener("keydown", keyDown, { signal: abortController.signal });
        fit();
        camera.updateSelectionAnchor();
        setLoading(false);
      }

      initialize().catch((reason: unknown) => {
        if (disposed) return;
        setError(reason instanceof Error ? reason.message : "Unable to initialize the image viewer.");
        setLoading(false);
      });

      return () => {
        disposed = true;
        abortController.abort();
        drawingRef.current = null;
        transformRef.current = null;
        hoveredAnnotationRef.current = null;
        cameraRef.current = null;
        if (texture) Assets.unload(imageUrl).catch(() => undefined);
        if (app && initialized) app.destroy({ removeView: true }, { children: true });
      };
    }, [imageLabel, imageUrl, onZoomChange]);

    const cursorClass = props.eraserEnabled ? "is-eraser-active" : props.transformEnabled ? "is-transform-active" : props.activeTool && props.activeClass ? "is-tool-active" : "";
    const actionAnnotation = actionAnchor ? annotations.find((annotation) => annotation.id === actionAnchor.annotationId) ?? null : null;
    return (
      <div className={`grading-workbench-viewport ${cursorClass}`} ref={hostRef}>
        {loading && <div className="grading-workbench-overlay" role="status"><span className="workbench-loader" />Loading diagnostic image…</div>}
        {error && <div className="grading-workbench-overlay is-error" role="alert">{error}</div>}
        {actionAnchor && actionAnnotation && (
          <div className="workbench-canvas-actions" style={{ left: actionAnchor.left, top: actionAnchor.top }} aria-label="Annotation edit controls" onMouseLeave={() => { hoveredAnnotationRef.current = null; cameraRef.current?.updateSelectionAnchor(); }}>
            <button type="button" title="Duplicate annotation" aria-label="Duplicate annotation" disabled={!actionAnnotation.classRef.multipleInstances} onClick={() => props.onDuplicateAnnotation(actionAnnotation.id)}><i className="fa-solid fa-copy" /></button>
            <button type="button" title={actionAnnotation.locked ? "Unlock annotation" : "Lock annotation"} aria-label={actionAnnotation.locked ? "Unlock annotation" : "Lock annotation"} onClick={() => props.onToggleAnnotationLock(actionAnnotation.id)}><i className={`fa-solid ${actionAnnotation.locked ? "fa-lock-open" : "fa-lock"}`} /></button>
            <button type="button" title="Rotate annotation" aria-label="Rotate annotation" disabled={actionAnnotation.locked || actionAnnotation.geometry.type === "box"} onClick={() => { preferredTransformRef.current = "rotate"; props.onSelectAnnotation(actionAnnotation.id); }}><i className="fa-solid fa-rotate" /></button>
            <button type="button" title="Move annotation" aria-label="Move annotation" disabled={actionAnnotation.locked} onClick={() => { preferredTransformRef.current = "move"; props.onSelectAnnotation(actionAnnotation.id); }}><i className="fa-solid fa-up-down-left-right" /></button>
            <button type="button" title="Edit annotation" aria-label="Edit annotation" onClick={() => props.onSelectAnnotation(actionAnnotation.id)}><i className="fa-solid fa-pen" /></button>
            <button type="button" title="Delete annotation" aria-label="Delete annotation" onClick={() => props.onDeleteAnnotation(actionAnnotation.id)}><i className="fa-solid fa-trash-can" /></button>
          </div>
        )}
      </div>
    );
  }
);
