const parseCsv = text => {
  const [header, ...lines] = text.trim().split(/\r?\n/);
  const keys = header.split(',');
  return lines.map(line => Object.fromEntries(keys.map((key, index) => [key, line.split(',')[index] ?? ''])));
};
let games = [], movement = [];
const gameBody = document.querySelector('#games');
function showGames() {
  const term = document.querySelector('#game-filter').value.toLowerCase();
  gameBody.innerHTML = games.filter(row => Object.values(row).join(' ').toLowerCase().includes(term)).slice(0, 200)
    .map(row => `<tr><td>${row.game_date}</td><td>${row.away_team}</td><td>${row.home_team}</td><td>${row.away_score} : ${row.home_score}</td><td>${row.stadium}</td><td>${row.validation_status}</td></tr>`).join('');
}
async function loadMovement() {
  if (!movement.length) movement = parseCsv(await (await fetch('data/movement.csv')).text());
  const select = document.querySelector('#pitch-type');
  if (select.options.length === 1) [...new Set(movement.map(row => row.pitch_type).filter(Boolean))].sort().forEach(type => select.add(new Option(type, type)));
  plot();
}
function plot() {
  const type = document.querySelector('#pitch-type').value;
  const rows = movement.filter(row => !type || row.pitch_type === type);
  const canvas = document.querySelector('#movement'), ctx = canvas.getContext('2d'), w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h); ctx.strokeStyle = '#9aaaba'; ctx.beginPath(); ctx.moveTo(w / 2, 20); ctx.lineTo(w / 2, h - 36); ctx.moveTo(45, h / 2); ctx.lineTo(w - 20, h / 2); ctx.stroke();
  const sample = Math.max(1, Math.ceil(rows.length / 5000)); let shown = 0;
  rows.forEach((row, index) => { if (index % sample) return; const x = Number(row.horizontal_movement_cm), y = Number(row.vertical_movement_cm); if (!Number.isFinite(x) || !Number.isFinite(y)) return; ctx.fillStyle = '#125ab388'; ctx.beginPath(); ctx.arc(w / 2 + x * 4, h / 2 - y * 4, 2, 0, Math.PI * 2); ctx.fill(); shown++; });
  document.querySelector('#plot-status').textContent = `${type || '전체'}: ${shown.toLocaleString()}개 표본 / ${rows.length.toLocaleString()}개 피치`;
}
document.querySelector('#game-filter').addEventListener('input', showGames);
document.querySelector('#pitch-type').addEventListener('change', plot);
document.querySelector('#plot').addEventListener('click', loadMovement);
Promise.all([fetch('data/summary.json').then(r => r.json()), fetch('data/games.csv').then(r => r.text())]).then(([summary, csv]) => { games = parseCsv(csv); document.querySelector('#summary').textContent = `${summary.date_range.join(' ~ ')} · ${summary.games.toLocaleString()}경기 · ${summary.pitches.toLocaleString()}피치`; showGames(); });
