(() => {
  const STORAGE_KEY = "analyticsFinalGradeBasis";
  const DEFAULT_BASIS = "preference";

  function normalizeBasis(value) {
    return value === "double_match" ? "double_match" : DEFAULT_BASIS;
  }

  function basisUsesUnresolved(value) {
    return normalizeBasis(value) === "double_match";
  }

  function getStoredBasis() {
    try {
      return normalizeBasis(window.localStorage.getItem(STORAGE_KEY));
    } catch (error) {
      return DEFAULT_BASIS;
    }
  }

  function setStoredBasis(value) {
    try {
      window.localStorage.setItem(STORAGE_KEY, normalizeBasis(value));
    } catch (error) {
      // Ignore storage failures and keep the active form value.
    }
  }

  function initSelect(select, onChange) {
    if (!select) return DEFAULT_BASIS;

    const urlParams = new URLSearchParams(window.location.search);
    const urlBasis = normalizeBasis(urlParams.get("final_grade_basis"));
    const currentValue = select.value ? normalizeBasis(select.value) : null;
    const initialBasis = urlParams.has("final_grade_basis")
      ? urlBasis
      : currentValue || getStoredBasis();

    select.value = initialBasis;
    setStoredBasis(initialBasis);
    if (typeof onChange === "function") {
      onChange(initialBasis);
    }

    select.addEventListener("change", () => {
      const basis = normalizeBasis(select.value);
      select.value = basis;
      setStoredBasis(basis);
      if (typeof onChange === "function") {
        onChange(basis);
      }
    });
    return initialBasis;
  }

  window.FinalGradeBasis = {
    STORAGE_KEY,
    DEFAULT_BASIS,
    basisUsesUnresolved,
    getStoredBasis,
    initSelect,
    normalizeBasis,
    setStoredBasis,
  };
})();
