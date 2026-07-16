(() => {
  const root = document.documentElement;
  const saved = localStorage.getItem("piticko-theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

  function setTheme(theme) {
    root.dataset.theme = theme;
    localStorage.setItem("piticko-theme", theme);
    const icon = document.querySelector("[data-theme-icon]");
    const label = document.querySelector("[data-theme-label]");
    if (icon) icon.textContent = theme === "dark" ? "🌙" : "☀️";
    if (label) label.textContent = theme === "dark" ? "Tmavý režim" : "Světlý režim";
  }

  setTheme(saved || (prefersDark ? "dark" : "light"));

  document.querySelector("[data-theme-toggle]")?.addEventListener("click", () => {
    setTheme(root.dataset.theme === "dark" ? "light" : "dark");
  });

  document.querySelector("[data-sidebar-open]")?.addEventListener("click", () => document.body.classList.add("sidebar-open"));
  document.querySelectorAll("[data-sidebar-close]").forEach(el => el.addEventListener("click", () => document.body.classList.remove("sidebar-open")));

  const toast = document.querySelector("[data-toast]");
  const hideToast = () => {
    if (!toast) return;
    toast.classList.add("hide");
    setTimeout(() => toast.remove(), 250);
  };
  document.querySelector("[data-toast-close]")?.addEventListener("click", hideToast);
  if (toast) setTimeout(hideToast, 5000);

  document.querySelectorAll("form").forEach(form => {
    form.addEventListener("submit", () => {
      const button = form.querySelector('button[type="submit"]');
      if (!button || button.disabled) return;
      button.disabled = true;
      button.dataset.oldText = button.textContent;
      button.textContent = "⏳ Ukládám…";
    });
  });
})();
