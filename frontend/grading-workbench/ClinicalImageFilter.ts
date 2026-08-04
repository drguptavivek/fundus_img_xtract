import { ColorMatrixFilter, Filter, GlProgram } from "pixi.js";

import type { ImageAnalysis } from "./imageAnalysis";
import { clinicalDisplayRecipe } from "./imageAnalysis";
import type { ViewerFilters } from "./workbenchState";
import { channelTuningMatrix } from "./viewerFilterMath";

const FILTER_VERTEX = `
precision highp float;
in vec2 aPosition;
out vec2 vTextureCoord;
uniform vec4 uInputSize;
uniform vec4 uOutputFrame;
uniform vec4 uOutputTexture;
vec4 filterVertexPosition(void) {
  vec2 position = aPosition * uOutputFrame.zw + uOutputFrame.xy;
  position.x = position.x * (2.0 / uOutputTexture.x) - 1.0;
  position.y = position.y * (2.0 * uOutputTexture.z / uOutputTexture.y) - uOutputTexture.z;
  return vec4(position, 0.0, 1.0);
}
vec2 filterTextureCoord(void) {
  return aPosition * (uOutputFrame.zw * uInputSize.zw);
}
void main(void) {
  gl_Position = filterVertexPosition();
  vTextureCoord = filterTextureCoord();
}`;

const FILTER_FRAGMENT = `
precision highp float;
in vec2 vTextureCoord;
out vec4 finalColor;
uniform sampler2D uTexture;
uniform vec4 uInputSize;
uniform vec4 uInputClamp;
uniform float uMode;
uniform float uBlackPoint;
uniform float uWhitePoint;
uniform float uGamma;
uniform float uExposure;
uniform float uContrast;
uniform float uSaturation;
uniform float uHighlightProtection;
uniform float uShadowLift;
uniform float uFlattening;
uniform float uLocalContrast;
uniform float uInvert;

vec3 modeColor(vec3 source) {
  if (uMode < 0.5) return source;
  return vec3(source.g);
}

vec3 sampleMode(vec2 uv) {
  return modeColor(texture(uTexture, clamp(uv, uInputClamp.xy, uInputClamp.zw)).rgb);
}

float luma(vec3 color) { return dot(color, vec3(0.2126, 0.7152, 0.0722)); }

// Exact piecewise-linear form of the legacy SVG E-filter table. Dark pixels
// receive the full lift; the mask tapers to zero before the highlight range.
float protectedShadowMask(float luminance) {
  float position = clamp(luminance, 0.0, 1.0) * 29.0;
  if (position <= 5.0) return 1.0;
  if (position < 6.0) return mix(1.0, 0.85, position - 5.0);
  if (position < 7.0) return mix(0.85, 0.70, position - 6.0);
  if (position < 8.0) return mix(0.70, 0.55, position - 7.0);
  if (position < 9.0) return mix(0.55, 0.40, position - 8.0);
  if (position < 10.0) return mix(0.40, 0.25, position - 9.0);
  if (position < 11.0) return mix(0.25, 0.15, position - 10.0);
  if (position < 12.0) return mix(0.15, 0.08, position - 11.0);
  if (position < 13.0) return mix(0.08, 0.03, position - 12.0);
  if (position < 14.0) return mix(0.03, 0.0, position - 13.0);
  return 0.0;
}

void main(void) {
  vec4 source = texture(uTexture, vTextureCoord);
  if (source.a <= 0.0) { finalColor = source; return; }
  vec2 pixel = uInputSize.zw;
  vec3 color = modeColor(source.rgb / source.a);

  vec3 nearBlur = (
    sampleMode(vTextureCoord + vec2(pixel.x, 0.0)) +
    sampleMode(vTextureCoord - vec2(pixel.x, 0.0)) +
    sampleMode(vTextureCoord + vec2(0.0, pixel.y)) +
    sampleMode(vTextureCoord - vec2(0.0, pixel.y))
  ) * 0.25;
  color += (color - nearBlur) * uLocalContrast * 0.75;

  if (uFlattening > 0.001) {
    vec2 wide = pixel * 72.0;
    float field = 0.0;
    field += luma(sampleMode(vTextureCoord + vec2(wide.x, 0.0)));
    field += luma(sampleMode(vTextureCoord - vec2(wide.x, 0.0)));
    field += luma(sampleMode(vTextureCoord + vec2(0.0, wide.y)));
    field += luma(sampleMode(vTextureCoord - vec2(0.0, wide.y)));
    field += luma(sampleMode(vTextureCoord + wide));
    field += luma(sampleMode(vTextureCoord - wide));
    field += luma(sampleMode(vTextureCoord + vec2(wide.x, -wide.y)));
    field += luma(sampleMode(vTextureCoord + vec2(-wide.x, wide.y)));
    field = max(0.04, field / 8.0);
    float flattenGain = clamp(0.38 / field, 0.62, 1.75);
    color *= mix(1.0, flattenGain, uFlattening);
  }

  if (uShadowLift > 0.001) {
    float shadowGain = 1.0 + protectedShadowMask(luma(color)) * uShadowLift * 2.0;
    color *= shadowGain;
  }

  color = clamp((color - uBlackPoint) / max(0.02, uWhitePoint - uBlackPoint), 0.0, 1.0);
  color = pow(color, vec3(max(0.2, uGamma)));
  color *= exp2(uExposure * 2.0);
  color = (color - 0.5) * (1.0 + uContrast) + 0.5;
  float gray = luma(color);
  color = mix(vec3(gray), color, 1.0 + uSaturation);
  vec3 excess = max(color - 0.55, 0.0);
  color /= vec3(1.0) + excess * uHighlightProtection * 1.8;
  color = clamp(color, 0.0, 1.0);
  if (uInvert > 0.5) color = 1.0 - color;
  finalColor = vec4(color * source.a, source.a);
}`;

function modeNumber(filters: ViewerFilters): number {
  if (filters.mode === "redfree" || filters.mode === "redfreeenhanced") return 1;
  return 0;
}

/** Build presentation-only GPU filters. Normal capture view deliberately returns no filter. */
export function makeClinicalImageFilters(filters: ViewerFilters, analysis: ImageAnalysis | null): Filter[] {
  if (filters.mode === "none" && JSON.stringify(filters) === JSON.stringify({
    mode: "none", brightness: 0, contrast: 0, saturation: 0,
    redLuminance: 0, redSaturation: 0, greenLuminance: 0, greenSaturation: 0,
    blueLuminance: 0, blueSaturation: 0, gamma: 1, blackPoint: 0, whitePoint: 1,
    shadowLift: 0, flattening: 0, invert: false
  })) return [];

  const recipe = clinicalDisplayRecipe(filters.mode, analysis);
  const channelFilter = new ColorMatrixFilter();
  channelFilter.matrix = channelTuningMatrix(filters);
  const displayFilter = new Filter({
    glProgram: GlProgram.from({ vertex: FILTER_VERTEX, fragment: FILTER_FRAGMENT, name: "clinical-fundus-display" }),
    resources: {
      clinicalUniforms: {
        uMode: { value: modeNumber(filters), type: "f32" },
        uBlackPoint: { value: Math.max(0, recipe.blackPoint + filters.blackPoint), type: "f32" },
        uWhitePoint: { value: Math.min(1, recipe.whitePoint + filters.whitePoint - 1), type: "f32" },
        uGamma: { value: recipe.gamma * filters.gamma, type: "f32" },
        uExposure: { value: filters.brightness, type: "f32" },
        uContrast: { value: filters.contrast, type: "f32" },
        uSaturation: { value: filters.saturation, type: "f32" },
        uHighlightProtection: { value: recipe.highlightProtection, type: "f32" },
        uShadowLift: { value: filters.shadowLift, type: "f32" },
        uFlattening: { value: filters.flattening, type: "f32" },
        uLocalContrast: { value: recipe.localContrast, type: "f32" },
        uInvert: { value: filters.invert ? 1 : 0, type: "f32" }
      }
    }
  });
  return [channelFilter, displayFilter];
}
