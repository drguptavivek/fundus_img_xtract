# Grading Workbench Image Filters

Status: Implemented frontend pipeline; clinical recipes require grader-led
calibration on representative camera and pathology sets.

## Purpose and boundary

The workbench always displays the secured source JPEG or PNG. The backend does
not extract channels or create derived images. The browser decodes a bounded
analysis copy and applies presentation-only transforms to the PixiJS image
sprite. Vector annotations and mask overlays remain in a separate, unfiltered
layer.

`N` is the protected baseline. When every presentation parameter is neutral,
the image sprite has no GPU filter attached. This makes `N` the decoded capture
view rather than another preset.

## Browser histogram analysis

`imageAnalysis.ts` fetches the same authorized image URL used by the viewer,
decodes it with `createImageBitmap`, and downsamples only the analysis copy to a
maximum dimension of 640 pixels. It computes 256-bin red, green, blue, and
perceptual-luminance histograms. Transparent pixels and pixels whose maximum
RGB component is 12 or less are excluded so the black surround of a fundus
export does not dominate the statistics.

For every channel the analysis records mean, P1, P5, median, P95, and P99.
Fine Tune displays the RGB curves on a logarithmic count scale, the active
channel statistics, and the effective black and white window markers. The
histogram is diagnostic UI state only and is not uploaded or stored.

## Display modes

| Code | Implementation | Intended presentation use |
| --- | --- | --- |
| `N` | Original decoded RGB, no filter | Capture-level reference |
| `E` | Original RGB with luminance-masked protected shadow lift | Reveal a dim retina/periphery without washing out the disc |
| `RF` | Green channel plus conservative RNFL-oriented gamma, local contrast, and highlight protection | Software red-free simulation |
| `RF+` | Green channel with stronger auto-windowing/local enhancement | Enhanced software red-free view |

The routine interface intentionally omits isolated red, green, and blue channels
and the green-blue composite. RGB curves and channel tuning remain available in
Fine Tune, while the main toolbar contains only clinically useful views.

`E` reproduces the legacy SVG filter's 30-point luminance table as an exact
piecewise-linear shader curve. The mask is effectively full in deep shadows,
tapers through the retinal mid-shadows, and reaches zero before highlights. Its
gain is `1 + mask × shadow_lift × 2`, so the `0-1` slider spans neutral through a
threefold maximum shadow gain while leaving bright pixels unchanged.

These modes are simulations derived from an ordinary colour image. They must
not be described as optical red-free acquisition, multispectral reflectance,
or a new diagnostic capture.

## Automatic window recipe

For the selected source channel:

```text
black = clamp(P1 / 255 - 0.01, 0, 0.18)
white = clamp(P99 / 255 + 0.08, 0.70, 1.00)
normalized_median = (median / 255 - black) / (white - black)
gamma = log(target_midtone) / log(normalized_median)
```

The target midtone is 0.36 for conservative channel views and 0.43 for the
enhanced recipe. Gamma is clamped to a safe range. The added P99 headroom and
shader highlight shoulder reduce optic-disc clipping.

The effective window shown on the histogram combines this image-specific
recipe with the preset's black-point and white-point shifts. Selecting a new
encounter image recalculates the automatic component from that image.

## Shader order

`ClinicalImageFilter.ts` runs the WebGL presentation operations in this order:

1. Optional saved RGB output-channel tuning.
2. Selected channel isolation or channel composite.
3. A small fixed local-detail adjustment for RF/RF+.
4. Optional wide-neighbour illumination flattening.
5. Protected shadow lift.
6. Black/white window normalization.
7. Gamma/midtone transform.
8. Exposure gain using `2^(2 × exposure)`.
9. Global contrast and saturation.
10. Mode-defined highlight shoulder compression.
11. Optional luminance inversion.

Flattening samples a broad neighbourhood and applies a bounded gain toward a
common field luminance. It is a real-time approximation, not a full offline
background-surface fit. The RF/RF+ detail and highlight behavior is fixed by
the mode and is not exposed as grader-adjustable tuning.

## Fine Tune and presets

Right-click a populated preset slot and choose **Fine tune**. The right grading
panel is replaced with live controls for:

- display mode (`N`, `E`, `RF`, or `RF+`);
- exposure, global contrast, and saturation;
- RGB output-channel luminance and saturation;
- gamma, black-point shift, and white-point shift;
- protected shadow lift and illumination flattening; and
- inversion.

Local contrast, denoise, sharpen, and highlight-protection sliders are
deliberately omitted. Their clinical effect is difficult to interpret
consistently, and aggressive settings can create halos, suppress small lesions,
or amplify JPEG artefacts. Any highlight shoulder or small detail adjustment in
RF/RF+ is fixed as part of that mode rather than stored in a user preset.

The histogram updates its window markers as black point, white point, mode, or
automatic recipe changes. **Cancel** restores the exact viewer state from
before Fine Tune was opened. **Save changes** persists the mode and parameters.
Zoom, pan, loupe state, source pixels, and histogram data are not preset fields.

## Persistence and source locations

Preset parameters are stored by `/api/viewer/presets` and validated by the
`ViewerPresets` model. The main implementation files are:

- `frontend/grading-workbench/imageAnalysis.ts` — decoding, histograms, and
  automatic recipes;
- `frontend/grading-workbench/ClinicalImageFilter.ts` — WebGL shader;
- `frontend/grading-workbench/App.tsx` — toolbar, histogram, and Fine Tune UI;
- `frontend/grading-workbench/viewerPresets.ts` — client preset contract;
- `api/viewer_settings.py` — preset API validation and serialization; and
- `models.py` — persistent preset fields and constraints.

## Calibration requirements

The implemented recipes are safe starting points, not a claim of diagnostic
equivalence. Before clinical rollout, calibration should include multiple
camera models, dark and bright captures, media opacity, small pupils, optic-disc
pathology, RNFL defects, macular disease, and common artefacts. Review should
compare `N`, channel views, and enhanced views while checking black clipping,
disc/highlight clipping, noise amplification, haloing, and whether enhancement
creates misleading boundaries.
