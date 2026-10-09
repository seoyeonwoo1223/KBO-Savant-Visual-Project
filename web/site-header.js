// 전 페이지 공통 헤더. 빌드 단계가 없으므로 각 페이지가 <body> 맨 앞에서 이 스크립트를
// 동기 로드하고, 스크립트는 자기 자리에 헤더 마크업을 삽입합니다.
// 사이트 루트는 자신의 src로부터 계산하므로 페이지 깊이와 무관합니다.
// 스타일은 theme.css의 .site-header / .site-brand / .site-nav-bar / .site-nav 규칙에 있습니다.
(function () {
  const script = document.currentScript;
  const root = new URL(".", script.src);

  // [경로, 표시 이름]. 홈 카드 순서와 같게 유지합니다.
  const TOOLS = [
    ["leaderboards/", "Leaderboards"],
    ["zones/", "Zone Profile"],
    ["swing-take/", "Swing/Take"],
    ["zone-awareness/", "Approach"],
    ["pitch-arsenal/", "Pitch Plot"],
    ["movement-zones/", "Movement Zones"],
    ["conditional-finder/", "Conditional Finder"],
    ["trendline/", "Trendline"],
    ["blocking/", "Blocking"],
    ["abs-zone/", "ABS Zone"],
  ];
  // 자체 인덱스가 없는 하위 페이지를 상위 도구에 매핑합니다.
  const ALIASES = { "profiles/": "swing-take/" };

  const here = new URL(".", location.href).href;
  const aliased = Object.keys(ALIASES).find(
    (path) => new URL(path, root).href === here
  );
  const current = aliased ? new URL(ALIASES[aliased], root).href : here;

  const links = TOOLS.map(([path, label]) => {
    const href = new URL(path, root).href;
    const active = href === current ? ' aria-current="page"' : "";
    return `<a href="${href}"${active}>${label}</a>`;
  }).join("");

  // 브랜드 줄(<header>)과 메뉴 줄(.site-nav-bar)을 형제로 둡니다. sticky는 부모 범위를
  // 벗어나지 못하므로, 메뉴 줄만 상단에 고정하려면 브랜드 줄 밖에 있어야 합니다.
  script.insertAdjacentHTML(
    "beforebegin",
    `<header class="site-header">
      <div class="site-header__inner">
        <a class="site-brand" href="${root.href}">
          <img src="${new URL("assets/image-Photoroom.png?v=20260913-4", root).href}" alt="">
          <span class="site-brand__text">
            <span class="site-brand__word">KBO <span>Savant</span></span>
            <span class="site-brand__tag">Visualizing data based on Naver Sports</span>
          </span>
        </a>
      </div>
    </header>
    <div class="site-nav-bar"><nav class="site-nav" aria-label="도구">${links}</nav></div>`
  );

  // "What is this?" 설명(.method-card)은 기본으로 접고, 제목 블록의 버튼으로 엽니다.
  // 카드는 제목 바로 아래로 옮기며 id는 그대로라 페이지 JS가 채우는 문단도 유지됩니다.
  document.addEventListener("DOMContentLoaded", () => {
    const title = document.querySelector("main .page-title");
    const card = document.querySelector("main .method-card");
    if (!title || !card) return;
    card.id ||= "about-panel";
    card.classList.add("method-card--collapsible");
    card.hidden = true;
    title.after(card);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "about-toggle";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", card.id);
    button.innerHTML = '<span aria-hidden="true">i</span>What is this?';
    button.addEventListener("click", () => {
      const open = card.hidden;
      card.hidden = !open;
      button.setAttribute("aria-expanded", String(open));
    });
    // 제목 블록 안에 시즌 선택 등이 나란히 있는 페이지도 있으므로 h1 옆(같은 부모)에 둡니다.
    (title.querySelector("h1")?.parentElement || title).append(button);
  });
})();
