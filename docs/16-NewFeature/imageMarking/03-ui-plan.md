# 03 - UI Plan (ROI-Only Grid + Polygon)

## Interaction Design
1. Draw ROI Box (defines grid area).
2. Draw Polygon within ROI (lesion boundary).
3. Add/Subtract grid cells inside ROI.

## Touchpad-Friendly Controls
- Mode buttons: `ROI`, `Polygon`, `Add`, `Subtract`, `Pan`.
- Keyboard shortcuts (no conflicts with existing viewer keys):
  - `U` = ROI mode
  - `I` = Polygon mode
  - `O` = Add mode
  - `P` = Subtract mode
  - `Esc` = Cancel current draw

## Grid
- Fixed 32x32 grid **within ROI**.
- Cell size depends on ROI size (fine for small lesions).

## Overlay
- Toggle overlay visibility on/off.
- Clear/delete per feature.

## Serialization
Per feature:
```json
{
  "feature_id": 123,
  "roi": {"type":"box","pixel":[[x1,y1],[x2,y2]],"norm":[[x1n,y1n],[x2n,y2n]]},
  "polygon": {"pixel":[[x,y],...],"norm":[[xn,yn],...]},
  "mask": {"rows":32,"cols":32,"cells":[[r,c],...]}
}
```

## Linked Grading
- Use `window.linkedGradingData[taskUuid].existingFeatureGeometry` for preload.
- Save to the per-panel hidden field.
