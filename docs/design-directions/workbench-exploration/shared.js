(function () {
  const params = new URLSearchParams(window.location.search);
  const initial = ["0", "1", "2"].includes(params.get("state")) ? params.get("state") : "1";

  function setState(state) {
    document.body.dataset.state = state;
    document.querySelectorAll("[data-set-state]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.setState === state));
    });
    const url = new URL(window.location.href);
    url.searchParams.set("state", state);
    window.history.replaceState({}, "", url);
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-set-state]");
    if (button) setState(button.dataset.setState);
  });

  setState(initial);
})();
