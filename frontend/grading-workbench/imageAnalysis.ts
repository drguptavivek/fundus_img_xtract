import type { ViewerFilterMode } from "./workbenchState";

export interface ChannelDistribution {
  mean: number;
  p01: number;
  p05: number;
  median: number;
  p95: number;
  p99: number;
}

export interface ImageAnalysis {
  width: number;
  height: number;
  sampleCount: number;
  red: ChannelDistribution;
  green: ChannelDistribution;
  blue: ChannelDistribution;
  luminance: ChannelDistribution;
  histograms: {
    red: number[];
    green: number[];
    blue: number[];
    luminance: number[];
  };
}

export interface ClinicalDisplayRecipe {
  blackPoint: number;
  whitePoint: number;
  gamma: number;
  highlightProtection: number;
  localContrast: number;
}

const EMPTY_DISTRIBUTION: ChannelDistribution = {
  mean: 0,
  p01: 0,
  p05: 0,
  median: 0,
  p95: 255,
  p99: 255
};

function percentile(histogram: Uint32Array, sampleCount: number, fraction: number): number {
  if (!sampleCount) return fraction < 0.5 ? 0 : 255;
  const target = Math.max(1, Math.ceil(sampleCount * fraction));
  let cumulative = 0;
  for (let value = 0; value < histogram.length; value += 1) {
    cumulative += histogram[value];
    if (cumulative >= target) return value;
  }
  return 255;
}

function distribution(histogram: Uint32Array, sampleCount: number, sum: number): ChannelDistribution {
  if (!sampleCount) return EMPTY_DISTRIBUTION;
  return {
    mean: Number((sum / sampleCount).toFixed(2)),
    p01: percentile(histogram, sampleCount, 0.01),
    p05: percentile(histogram, sampleCount, 0.05),
    median: percentile(histogram, sampleCount, 0.5),
    p95: percentile(histogram, sampleCount, 0.95),
    p99: percentile(histogram, sampleCount, 0.99)
  };
}

/** Analyze decoded display pixels; the source file and server data are never modified. */
export function analyzeImagePixels(pixels: Uint8ClampedArray, width: number, height: number): ImageAnalysis {
  const histograms = [new Uint32Array(256), new Uint32Array(256), new Uint32Array(256), new Uint32Array(256)];
  const sums = [0, 0, 0, 0];
  let sampleCount = 0;
  for (let offset = 0; offset + 3 < pixels.length; offset += 4) {
    const red = pixels[offset];
    const green = pixels[offset + 1];
    const blue = pixels[offset + 2];
    const alpha = pixels[offset + 3];
    // Exclude transparent pixels and the black surround common in fundus exports.
    if (alpha < 128 || Math.max(red, green, blue) <= 12) continue;
    const luminance = Math.round(0.2126 * red + 0.7152 * green + 0.0722 * blue);
    const values = [red, green, blue, luminance];
    values.forEach((value, index) => {
      histograms[index][value] += 1;
      sums[index] += value;
    });
    sampleCount += 1;
  }
  return {
    width,
    height,
    sampleCount,
    red: distribution(histograms[0], sampleCount, sums[0]),
    green: distribution(histograms[1], sampleCount, sums[1]),
    blue: distribution(histograms[2], sampleCount, sums[2]),
    luminance: distribution(histograms[3], sampleCount, sums[3]),
    histograms: {
      red: Array.from(histograms[0]),
      green: Array.from(histograms[1]),
      blue: Array.from(histograms[2]),
      luminance: Array.from(histograms[3])
    }
  };
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function recipeFor(distributionValue: ChannelDistribution, enhanced: boolean): ClinicalDisplayRecipe {
  const blackPoint = clamp(distributionValue.p01 / 255 - 0.01, 0, 0.18);
  // Leave headroom for the optic disc and specular highlights rather than
  // stretching the 99th percentile directly to display white.
  const whitePoint = clamp(distributionValue.p99 / 255 + 0.08, 0.7, 1);
  const normalizedMedian = clamp(
    (distributionValue.median / 255 - blackPoint) / Math.max(0.05, whitePoint - blackPoint),
    0.02,
    0.95
  );
  const targetMidtone = enhanced ? 0.43 : 0.36;
  const gamma = clamp(Math.log(targetMidtone) / Math.log(normalizedMedian), enhanced ? 0.42 : 0.48, 1.15);
  return {
    blackPoint: Number(blackPoint.toFixed(4)),
    whitePoint: Number(whitePoint.toFixed(4)),
    gamma: Number(gamma.toFixed(4)),
    highlightProtection: enhanced ? 0.24 : 0.16,
    localContrast: enhanced ? 0.18 : 0
  };
}

export function clinicalDisplayRecipe(mode: ViewerFilterMode, analysis: ImageAnalysis | null): ClinicalDisplayRecipe {
  if (mode === "none" || mode === "enhance" || !analysis?.sampleCount) {
    return { blackPoint: 0, whitePoint: 1, gamma: 1, highlightProtection: 0, localContrast: 0 };
  }
  if (mode === "redfree" || mode === "redfreeenhanced") {
    const recipe = recipeFor(analysis.green, mode === "redfreeenhanced");
    if (mode === "redfree") {
      return {
        ...recipe,
        gamma: Number(Math.max(0.42, recipe.gamma * 0.94).toFixed(4)),
        highlightProtection: 0.2,
        localContrast: 0.08
      };
    }
    return recipe;
  }
  return { blackPoint: 0, whitePoint: 1, gamma: 1, highlightProtection: 0, localContrast: 0 };
}

/** Decode and sample a same-origin JPEG/PNG in the browser at bounded resolution. */
export async function analyzeImageUrl(imageUrl: string, signal?: AbortSignal): Promise<ImageAnalysis> {
  const response = await fetch(imageUrl, { credentials: "same-origin", signal });
  if (!response.ok) throw new Error(`Unable to analyze image (${response.status})`);
  const bitmap = await createImageBitmap(await response.blob());
  try {
    const scale = Math.min(1, 640 / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("Browser image analysis canvas is unavailable");
    context.drawImage(bitmap, 0, 0, width, height);
    return analyzeImagePixels(context.getImageData(0, 0, width, height).data, width, height);
  } finally {
    bitmap.close();
  }
}
