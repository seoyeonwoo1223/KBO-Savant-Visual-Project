// 전 페이지 공통 헤더. 빌드 단계가 없으므로 각 페이지가 <body> 맨 앞에서 이 스크립트를
// 동기 로드하고, 스크립트는 자기 자리에 헤더 마크업을 삽입합니다.
// 사이트 루트는 자신의 src로부터 계산하므로 페이지 깊이와 무관합니다.
// 스타일은 theme.css의 .site-header / .site-brand / .site-nav 규칙에 있습니다.
(function () {
  const script = document.currentScript;
  const root = new URL(".", script.src);

  // [경로, 표시 이름]. 홈 카드 순서와 같게 유지합니다.
  const TOOLS = [
    ["leaderboards/", "Leaderboards"],
    ["zones/", "Zone Profile"],
    ["swing-take/", "Swing/Take"],
    ["zone-awareness/", "Zone Awareness"],
    ["pitch-arsenal/", "Pitch Plot"],
    ["movement-zones/", "Movement Zones"],
    ["blocking/", "Blocking"],
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

  script.insertAdjacentHTML(
    "beforebegin",
    `<header class="site-header">
      <div class="site-header__inner">
        <a class="site-brand" href="${root.href}">
          <img src="${new URL("assets/image-Photoroom.png", root).href}" alt="">
          <span class="site-brand__word">KBO <span>Savant</span></span>
        </a>
        <nav class="site-nav" aria-label="도구">${links}</nav>
      </div>
    </header>`
  );
})();
