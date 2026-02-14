(function () {
  const PALETTE = [
    "#e63946",
    "#457b9d",
    "#2a9d8f",
    "#f4a261",
    "#264653",
    "#8ab17d",
    "#ff006e",
    "#3a86ff",
    "#8338ec",
    "#ff7f11",
    "#06d6a0",
    "#ef476f",
    "#118ab2",
    "#7f4f24",
    "#4d908e",
    "#6a4c93",
  ];

  function numericFeatureId(featureId) {
    const parsed = Number(featureId);
    if (Number.isNaN(parsed)) return 0;
    return Math.abs(Math.trunc(parsed));
  }

  function colorForFeature(featureId) {
    const id = numericFeatureId(featureId);
    return PALETTE[id % PALETTE.length];
  }

  window.FeatureGeometryColors = {
    palette: PALETTE.slice(),
    colorForFeature,
  };
})();
