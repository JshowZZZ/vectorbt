function _appendCoverageIntro(section) {
  if (!section) return;
  const card = document.createElement("div");
  card.className = "cp-placeholder-card";
  const h3 = document.createElement("h3");
  h3.textContent = "Coverage Planner Scaffold";
  card.appendChild(h3);
  const p = document.createElement("p");
  p.textContent =
    "AWF-015/AWF-017c 將在此串接 run_registry 覆蓋缺口、plan 產生與點擊排程。";
  card.appendChild(p);
  const pill = document.createElement("span");
  pill.className = "cp-pill";
  pill.textContent = "Ready for AWF-015 + AWF-017c";
  card.appendChild(pill);
  section.appendChild(card);
}

export function initCoverageTab() {
  const section = document.querySelector('.cp-tab-panel[data-tab="coverage"]');
  _appendCoverageIntro(section);
}

