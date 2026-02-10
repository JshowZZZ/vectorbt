function _appendDashboardCard(section, title, desc, status) {
  if (!section) return;
  const card = document.createElement("div");
  card.className = "cp-placeholder-card";
  const h3 = document.createElement("h3");
  h3.textContent = title;
  card.appendChild(h3);
  const p = document.createElement("p");
  p.textContent = desc;
  card.appendChild(p);
  const pill = document.createElement("span");
  pill.className = "cp-pill";
  pill.textContent = status;
  card.appendChild(pill);
  section.appendChild(card);
}

export function initDashboardTab() {
  const dashSection = document.querySelector('.cp-tab-panel[data-tab="dashboard"]');
  const historySection = document.querySelector('.cp-tab-panel[data-tab="history"]');

  _appendDashboardCard(
    dashSection,
    "Cross-Run Analytics Scaffold",
    "AWF-016/AWF-017d 將在本區聚合 KPI、組合穩定度與全域 leaderboard。",
    "Ready for AWF-016 + AWF-017d"
  );
  _appendDashboardCard(
    historySection,
    "Run History Scaffold",
    "AWF-017d 將在本區提供 run timeline、篩選與回溯連結。",
    "Ready for AWF-017d"
  );
}

