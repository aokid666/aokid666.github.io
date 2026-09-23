const filters = ["date", "state", "genre", "mode", "scene"].map(name => document.getElementById(name + "-filter"));
const search = document.getElementById("search");
const questions = [...document.querySelectorAll(".question")];
const sections = [...document.querySelectorAll(".day-section")];
const count = document.getElementById("result-count");
const empty = document.getElementById("empty-state");

function applyFilters() {
  const query = search.value.trim().toLocaleLowerCase();
  let visible = 0;
  for (const item of questions) {
    const matches = filters.every(filter => !filter.value || item.dataset[filter.id.replace("-filter", "")] === filter.value)
      && (!query || item.dataset.search.includes(query));
    item.hidden = !matches;
    if (matches) visible++;
  }
  for (const section of sections) {
    section.hidden = ![...section.querySelectorAll(".question")].some(item => !item.hidden);
  }
  count.textContent = `显示 ${visible} / ${questions.length} 道题`;
  empty.hidden = visible !== 0;
}

function resetFilters() {
  filters.forEach(filter => { filter.value = ""; });
  search.value = "";
  applyFilters();
}

filters.forEach(filter => filter.addEventListener("change", applyFilters));
search.addEventListener("input", applyFilters);
document.getElementById("reset-filters").addEventListener("click", resetFilters);
document.getElementById("empty-reset").addEventListener("click", resetFilters);
if (window.matchMedia("(max-width: 700px)").matches) {
  document.querySelector(".filter-drawer").open = false;
}
applyFilters();
