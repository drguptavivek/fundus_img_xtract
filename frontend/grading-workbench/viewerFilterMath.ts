import type { ViewerFilters } from "./workbenchState";

export type ColorMatrixValues = [
  number, number, number, number, number,
  number, number, number, number, number,
  number, number, number, number, number,
  number, number, number, number, number
];

export const IDENTITY_COLOR_MATRIX: ColorMatrixValues = [
  1, 0, 0, 0, 0,
  0, 1, 0, 0, 0,
  0, 0, 1, 0, 0,
  0, 0, 0, 1, 0
];

const LUMINANCE = [0.2126, 0.7152, 0.0722];

function channelRow(channel: 0 | 1 | 2, luminanceOffset: number, saturationOffset: number): number[] {
  const luminanceGain = 1 + luminanceOffset;
  const saturation = 1 + saturationOffset;
  const grayscaleMix = 1 - saturation;
  return LUMINANCE.map((weight, index) => (
    (weight * grayscaleMix + (index === channel ? saturation : 0)) * luminanceGain
  ));
}

export function channelTuningMatrix(filters: ViewerFilters): ColorMatrixValues {
  const red = channelRow(0, filters.redLuminance, filters.redSaturation);
  const green = channelRow(1, filters.greenLuminance, filters.greenSaturation);
  const blue = channelRow(2, filters.blueLuminance, filters.blueSaturation);
  return [
    ...red, 0, 0,
    ...green, 0, 0,
    ...blue, 0, 0,
    0, 0, 0, 1, 0
  ] as unknown as ColorMatrixValues;
}

/** Compose two 4x5 color matrices so `before` runs first and `after` second. */
export function multiplyColorMatrices(after: number[], before: number[]): ColorMatrixValues {
  if (after.length !== 20 || before.length !== 20) throw new Error("Color matrices must contain 20 values");
  const result = new Array<number>(20).fill(0);
  for (let row = 0; row < 4; row += 1) {
    for (let column = 0; column < 4; column += 1) {
      for (let index = 0; index < 4; index += 1) {
        result[row * 5 + column] += after[row * 5 + index] * before[index * 5 + column];
      }
    }
    result[row * 5 + 4] = after[row * 5 + 4];
    for (let index = 0; index < 4; index += 1) {
      result[row * 5 + 4] += after[row * 5 + index] * before[index * 5 + 4];
    }
  }
  return result as unknown as ColorMatrixValues;
}
