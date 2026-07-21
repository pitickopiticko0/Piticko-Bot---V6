"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const tabs = Array.from(document.querySelectorAll(".tab[data-tab]"));
  const panels = Array.from(document.querySelectorAll(".tab-panel"));

  const activateTab = (name, updateHash = true) => {
    const selected = tabs.find((tab) => tab.dataset.tab === name);
    const panel = document.getElementById(name);
    if (!selected || !panel) return;

    tabs.forEach((tab) => {
      const active = tab === selected;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    panels.forEach((item) => item.classList.toggle("active", item === panel));

    if (updateHash) history.replaceState(null, "", `#${name}`);
    panel.querySelector("input, textarea, select, button")?.focus({ preventScroll: true });
  };

  tabs.forEach((tab) => tab.addEventListener("click", () => activateTab(tab.dataset.tab)));

  document.querySelectorAll("[data-open-tab]").forEach((element) => {
    const open = () => activateTab(element.dataset.openTab);
    element.addEventListener("click", open);
    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        open();
      }
    });
  });

  const initialTab = location.hash.slice(1);
  if (initialTab) activateTab(initialTab, false);

  const search = document.getElementById("guildSearch");
  if (search) {
    search.addEventListener("input", () => {
      const value = search.value.trim().toLocaleLowerCase("cs");
      document.querySelectorAll("[data-guild]").forEach((card) => {
        card.hidden = !card.dataset.guild.toLocaleLowerCase("cs").includes(value);
      });
    });
  }

  document.querySelectorAll("[data-uptime]").forEach((element) => {
    let seconds = Number(element.dataset.uptime || 0);
    const render = () => {
      const days = Math.floor(seconds / 86400);
      const hours = Math.floor((seconds % 86400) / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      element.textContent = `${days}d ${hours}h ${minutes}m`;
      seconds += 1;
    };
    render();
    window.setInterval(render, 1000);
  });

  document.querySelectorAll(".toast").forEach((toast) => {
    const remove = () => {
      toast.classList.add("is-hiding");
      window.setTimeout(() => toast.remove(), 220);
    };
    toast.querySelector(".toast-close")?.addEventListener("click", remove);
    window.setTimeout(remove, 5200);
  });

  document.querySelectorAll('input[type="color"]').forEach((input) => {
    const code = input.parentElement?.querySelector("code");
    input.addEventListener("input", () => {
      if (code) code.textContent = input.value.toUpperCase();
    });
  });

  const avatarInput = document.getElementById("botAvatarInput");
  const avatarPreview = document.getElementById("botAvatarPreview");
  if (avatarInput && avatarPreview) {
    let previewUrl = null;
    avatarInput.addEventListener("change", () => {
      const file = avatarInput.files?.[0];
      if (!file) return;
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(file);
      avatarPreview.src = previewUrl;
    });
    window.addEventListener("pagehide", () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    });
  }
});
