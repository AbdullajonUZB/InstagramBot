(() => {
  const app = window.Telegram?.WebApp;
  const input = document.querySelector("#media-url");
  const button = document.querySelector("#download-button");
  const pasteButton = document.querySelector("#paste-button");
  const serviceLabel = document.querySelector("#service-label");
  const notice = document.querySelector("#notice");
  const services = [
    ["Instagram", ["instagram.com"]],
    ["YouTube", ["youtube.com", "youtu.be"]],
    ["Pinterest", ["pinterest.com", "pin.it"]],
    ["Facebook", ["facebook.com", "fb.watch"]],
  ];

  if (app) {
    app.ready();
    app.expand();
    app.setHeaderColor("#101725");
    app.setBackgroundColor("#101725");
  } else {
    notice.textContent = "Откройте приложение через кнопку в Telegram-боте.";
  }

  const detect = () => {
    const value = input.value.trim();
    let parsedUrl;
    try {
      parsedUrl = new URL(value);
    } catch { /* URL ещё не введён полностью */ }
    const validUrl = parsedUrl && (parsedUrl.protocol === "https:" || parsedUrl.protocol === "http:");
    const hostname = parsedUrl?.hostname.toLowerCase().replace(/^www\./, "");
    const service = services.find(([, domains]) => domains.some(
      (domain) => hostname === domain || hostname?.endsWith(`.${domain}`),
    ));
    serviceLabel.textContent = service ? `Определён сервис: ${service[0]}` : "Сервис определится автоматически";
    button.disabled = !(app && validUrl && service);
    notice.textContent = app ? "" : "Откройте приложение через кнопку в Telegram-боте.";
  };

  input.addEventListener("input", detect);
  pasteButton.addEventListener("click", async () => {
    try {
      input.value = await navigator.clipboard.readText();
      detect();
      input.focus();
    } catch {
      notice.textContent = "Не удалось вставить автоматически — коснитесь поля и вставьте ссылку.";
    }
  });
  button.addEventListener("click", () => {
    const url = input.value.trim();
    if (!app || button.disabled) return;
    app.HapticFeedback?.impactOccurred("light");
    app.sendData(JSON.stringify({ action: "download", url }));
    button.disabled = true;
    button.querySelector("span:first-child").textContent = "Передано боту";
    notice.textContent = "Готово! Следите за этим чатом — бот пришлёт файл туда.";
    window.setTimeout(() => app.close(), 700);
  });
  detect();
})();
