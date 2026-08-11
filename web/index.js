const playerList = document.querySelector("#player-list");

fetch("data/profiles/index.json")
  .then(response => {
    if (!response.ok) throw new Error("index data could not be loaded");
    return response.json();
  })
  .then(data => {
    document.querySelector("#season").textContent = `${data.season} regular season`;
    playerList.innerHTML = data.players.map(player => `
      <a class="player-card" href="profiles/${player.slug}.html">
        <span class="player-card__team">${player.team}</span>
        <strong>${player.name}</strong>
        <span class="player-card__romanized">${player.romanized_name}</span>
        <span class="player-card__detail">Bats: ${player.bats} · ${player.pitches.toLocaleString()} pitches${player.meets_minimum ? "" : " · 표본 미달"}</span>
        <span class="player-card__link">View profile →</span>
      </a>`).join("");
  })
  .catch(() => {
    playerList.innerHTML = "<p>선수 목록을 불러오지 못했습니다.</p>";
  });
