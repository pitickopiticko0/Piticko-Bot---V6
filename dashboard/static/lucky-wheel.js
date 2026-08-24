"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-wheel-form]");
  const wheel = document.querySelector(".wheel-visual");
  const button = form?.querySelector("button");
  if (!form || !wheel || !button) return;

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    button.disabled = true;
    button.textContent = "🎡 Točíme…";
    wheel.classList.add("is-spinning");
    window.setTimeout(() => form.submit(), 900);
  }, { once: true });
});
