(function () {
  "use strict";

  const search = document.getElementById("search-filter");
  const family = document.getElementById("family-filter");
  const state = document.getElementById("state-filter");
  const rows = Array.from(document.querySelectorAll(".report-row"));
  const count = document.getElementById("visible-count");
  const noMatch = document.getElementById("no-match");

  function applyFilters() {
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    for (const row of rows) {
      const matches =
        (!query || row.dataset.search.includes(query)) &&
        (!family.value || row.dataset.family === family.value) &&
        (!state.value || row.dataset.state === state.value);
      row.hidden = !matches;
      if (matches) visible += 1;
    }
    count.textContent = `${visible} visible`;
    noMatch.hidden = visible !== 0 || rows.length === 0;
  }

  for (const control of [search, family, state]) {
    control.addEventListener("input", applyFilters);
    control.addEventListener("change", applyFilters);
  }
  applyFilters();
})();
