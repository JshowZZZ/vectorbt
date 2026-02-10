function _appendCard(section, title, desc, status) {
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

export function initBatchTab() {
  const controlSection = document.querySelector('.cp-tab-panel[data-tab="control"]');
  if (!controlSection) return;
  _appendCard(
    controlSection,
    "Batch Queue Scaffold",
    "AWF-017b 將在本區加入 queue table、enqueue/start/cancel 操作與即時進度。",
    "Ready for AWF-017b"
  );
}

