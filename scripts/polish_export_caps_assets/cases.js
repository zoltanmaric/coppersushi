const level = document.getElementById('level');
const effect = document.getElementById('effect');
const date = document.getElementById('case-date');
const rows = [...document.querySelectorAll('#cases tbody tr')];
function filterCases() {
  let visible = 0;
  for (const row of rows) {
    row.hidden = Boolean((level.value && row.dataset.level !== level.value) ||
      (effect.value && row.dataset.effect !== effect.value) ||
      (date.value && row.dataset.date !== date.value));
    if (!row.hidden) visible++;
  }
  document.getElementById('case-count').textContent = `${visible.toLocaleString()} matching MTUs`;
}
for (const control of [level, effect, date]) control.addEventListener('input', filterCases);
document.getElementById('reset-filters').addEventListener('click', () => {
  level.value = effect.value = date.value = '';
  filterCases();
});
