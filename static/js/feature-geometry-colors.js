(function () {
  const PALETTE = [
    "#00B8D9", // deep cyan
    "#2E7DFF", // deep azure
    "#00C853", // deep green
    "#B388FF", // deep violet
    "#FFD600", // deep yellow
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
