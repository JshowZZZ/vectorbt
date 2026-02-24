const TAB_DEFS = [
  { key: "control", label: "控制台" },
  { key: "results", label: "結果" },
  { key: "coverage", label: "覆蓋" },
  { key: "dashboard", label: "儀表板" },
  { key: "history", label: "歷史" },
];

function _buildButton(tabKey, label, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "cp-tab-btn";
  btn.textContent = label;
  btn.dataset.tab = tabKey;
  btn.onclick = onClick;
  return btn;
}

function _buildSection(tabKey) {
  const section = document.createElement("section");
  section.className = "cp-tab-panel";
  section.dataset.tab = tabKey;
  return section;
}

function _appendPlaceholder(section, title, message) {
  const box = document.createElement("div");
  box.className = "cp-placeholder-card";

  const h3 = document.createElement("h3");
  h3.textContent = title;
  box.appendChild(h3);

  const p = document.createElement("p");
  p.textContent = message;
  box.appendChild(p);

  section.appendChild(box);
}

export function initTabs() {
  const title = document.querySelector("h1");
  const panels = Array.from(document.querySelectorAll("body > .panel"));
  if (!title || panels.length === 0) {
    return { activate: () => {} };
  }

  const tabBar = document.createElement("nav");
  tabBar.className = "cp-tab-bar";
  tabBar.setAttribute("aria-label", "Control panel tabs");

  const host = document.createElement("div");
  host.className = "cp-tab-host";

  const sections = new Map();
  const buttons = new Map();

  const activate = (tabKey) => {
    sections.forEach((section, key) => {
      section.classList.toggle("is-active", key === tabKey);
    });
    buttons.forEach((button, key) => {
      button.classList.toggle("is-active", key === tabKey);
    });
  };

  TAB_DEFS.forEach((def) => {
    const section = _buildSection(def.key);
    sections.set(def.key, section);
    host.appendChild(section);

    const button = _buildButton(def.key, def.label, () => activate(def.key));
    buttons.set(def.key, button);
    tabBar.appendChild(button);
  });

  title.insertAdjacentElement("afterend", tabBar);
  tabBar.insertAdjacentElement("afterend", host);

  const mapByIndex = {
    control: [0, 1, 3],
    results: [2, 4, 5, 6, 7],
    history: [8],
  };

  Object.entries(mapByIndex).forEach(([tabKey, indexes]) => {
    const section = sections.get(tabKey);
    if (!section) return;
    indexes.forEach((idx) => {
      if (idx >= 0 && idx < panels.length) {
        section.appendChild(panels[idx]);
      }
    });
  });

  if (sections.get("coverage")?.children.length === 0) {
    _appendPlaceholder(
      sections.get("coverage"),
      "Coverage Map (Scaffold)",
      "AWF-017c 將在此加入 timeframe×symbol 覆蓋矩陣與一鍵排程。"
    );
  }
  if (sections.get("dashboard")?.children.length === 0) {
    _appendPlaceholder(
      sections.get("dashboard"),
      "Cross-Run Dashboard (Scaffold)",
      "AWF-017d 將在此加入跨 run 指標、穩定度趨勢與全域排行榜。"
    );
  }
  if (sections.get("history")?.children.length === 0) {
    _appendPlaceholder(
      sections.get("history"),
      "Run History (Scaffold)",
      "AWF-017d 將在此加入歷史 run 時間線與查詢。"
    );
  }

  activate("control");
  return { activate };
}

