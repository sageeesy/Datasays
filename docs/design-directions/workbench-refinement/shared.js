(function () {
  const value = new URLSearchParams(location.search).get("state");
  const initial = value === "3" ? "3" : "2";

  function apply(state) {
    document.body.dataset.state = state;
    document.querySelectorAll("[data-state-button]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.stateButton === state));
    });
    const url = new URL(location.href);
    url.searchParams.set("state", state);
    history.replaceState({}, "", url);
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-state-button]");
    if (button) apply(button.dataset.stateButton);
  });

  apply(initial);
})();
