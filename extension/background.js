chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "PING_BRIDGE") {
    fetch("http://127.0.0.1:8000/status")
      .then(r => r.json())
      .then(data => sendResponse({
        online: true,
        localVersion: data.local_version || "6.2",
        remoteVersion: data.remote_version || "6.2",
        hasUpdate: !!data.has_update,
        changelog: data.changelog || ""
      }))
      .catch(() => {
        fetch("http://127.0.0.1:8000/openapi.json")
          .then(r => sendResponse({ online: r.ok, hasUpdate: false }))
          .catch(() => sendResponse({ online: false }));
      });
    return true;
  }

  if (msg.type === "GIT_SYNC") {
    fetch("http://127.0.0.1:8000/git_sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: msg.mode || "pull", message: msg.message || "" })
    })
      .then(r => r.json())
      .then(data => sendResponse({ ok: data.status === "ok", message: data.message }))
      .catch(err => sendResponse({ ok: false, message: err.message }));
    return true;
  }

  if (msg.type === "EXEC_CMD") {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    fetch("http://127.0.0.1:8000/exec", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(msg.cmd),
      signal: controller.signal
    })
      .then(r => r.json())
      .then(data => {
        clearTimeout(timer);
        sendResponse({ ok: data.status === "ok" || data.status === "ignored", message: data.message });
      })
      .catch(err => {
        clearTimeout(timer);
        sendResponse({ ok: false, message: "Мост не отвечает: " + err.message });
      });
    return true;
  }
});
