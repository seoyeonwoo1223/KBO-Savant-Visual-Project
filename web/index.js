const playerList = document.querySelector("#player-list");
const form = document.querySelector("#player-search");
const query = document.querySelector("#player-query");
const message = document.querySelector("#search-message");

const normalize = value => String(value || "").replace(/\s+/g, "").toLowerCase();

const openProfile = player => {
  window.location.assign(`profiles/index.html?player=${encodeURIComponent(player.id || player.slug || player.name)}`);
};

fetch("data/profiles/index.json")
  .then(response => {
    if (!response.ok) throw new Error("index data could not be loaded");
    return response.json();
  })
  .then(data => {
    document.querySelector("#season").textContent = `${data.season} regular season`;
    const render = players => {
      playerList.innerHTML = players.map(player => `
      <button class="player-card" type="button" data-player-id="${player.id || player.slug || player.name}">
        <span class="player-card__team">${player.team}</span>
        <strong>${player.name}</strong>
        <span class="player-card__romanized">${player.romanized_name}</span>
        <span class="player-card__detail">Bats: ${player.bats} · ${player.pitches.toLocaleString()} pitches${player.meets_minimum ? "" : " · 표본 미달"}</span>
        <span class="player-card__link">View profile →</span>
      </button>`).join("");
      playerList.querySelectorAll("[data-player-id]").forEach(card => card.addEventListener("click", () => {
        openProfile(data.players.find(player => String(player.id || player.slug || player.name) === card.dataset.playerId));
      }));
    };
    render(data.players);
    form.addEventListener("submit", event => {
      event.preventDefault();
      const value = normalize(query.value);
      const exact = data.players.find(player => normalize(player.name) === value || normalize(player.romanized_name) === value);
      const matches = data.players.filter(player => normalize(player.name).includes(value) || normalize(player.romanized_name).includes(value));
      if (exact) return openProfile(exact);
      if (matches.length === 1) return openProfile(matches[0]);
      if (!value) { message.textContent = "선수 이름을 입력해 주세요."; return; }
      message.textContent = matches.length ? `검색 결과가 ${matches.length}명입니다. 아래 목록에서 선택해 주세요.` : "해당 선수의 ABS 프로필이 없습니다.";
      render(matches);
    });
  })
  .catch(() => {
    playerList.innerHTML = "<p>선수 목록을 불러오지 못했습니다.</p>";
  });
