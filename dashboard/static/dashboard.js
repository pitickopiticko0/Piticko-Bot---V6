document.addEventListener("DOMContentLoaded", () => {
  const search = document.getElementById("guildSearch");
  if (search) {
    search.addEventListener("input", () => {
      const value = search.value.trim().toLowerCase();
      document.querySelectorAll("[data-guild]").forEach(card => {
        card.style.display = card.dataset.guild.includes(value) ? "" : "none";
      });
    });
  }

  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(item => item.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(item => item.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(tab.dataset.tab)?.classList.add("active");
      history.replaceState(null, "", `#${tab.dataset.tab}`);
    });
  });

  const initialTab = location.hash.replace("#", "");
  if (initialTab) {
    document.querySelector(`.tab[data-tab="${initialTab}"]`)?.click();
  }

  document.querySelectorAll("[data-uptime]").forEach(element => {
    let seconds = Number(element.dataset.uptime || 0);
    const render = () => {
      const days = Math.floor(seconds / 86400);
      const hours = Math.floor((seconds % 86400) / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      element.textContent = `${days}d ${hours}h ${minutes}m`;
      seconds += 1;
    };
    render();
    setInterval(render, 1000);
  });

  const toast = document.querySelector(".toast");
  if (toast) {
    setTimeout(() => toast.remove(), 4200);
  }
});
