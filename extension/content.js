const executedSignatures = new Set();
let isReady = false;
const IS_DEEPSEEK = location.hostname.includes("deepseek.com");

const BRIDGE_SYSTEM_PROMPT = `СИСТЕМНАЯ ИНСТРУКЦИЯ (AI Bridge FULL CONTROL v6.2):
Ты подключён к моему ПК (Windows) через локальный мост. Чтобы выполнить действие на компьютере, выводи в ответе JSON-блок формата:
\`\`\`json
{"action": "название", "target": "цель", "content": "содержимое", "extra": "доп_параметр"}
\`\`\`

Доступные команды (action):
1. Программы и ссылки:
- "open_app" | target: имя программы ("calc", "notepad", "chrome", "telegram", "steam", "discord" и т.д.)
- "kill_app" | target: имя процесса ("notepad.exe")
- "open_url" | target: URL ("https://...")

2. Файлы, папки и код (по умолчанию пути от Рабочего стола, либо полный путь):
- "read_file" | target: путь к файлу, extra: опционально диапазон строк ("1:120")
- "list_dir" | target: путь к папке (если пусто — Рабочий стол)
- "write_file" | target: "Desktop/script.py", content: текст файла, extra: "open" (открыть) или "run" (запустить .py в cmd)
- "append_file" | target: путь, content: текст для дозаписи
- "delete_path" | target: путь к файлу/папке
- "open_path" | target: путь к файлу/папке

3. Клавиатура и ввод:
- "paste_text" | content: любой текст/код (вставляет через буфер Ctrl+V), extra: "enter" (нажать Enter после вставки)
- "type_text" | target: латинский текст для посимвольного ввода
- "hotkey" | target: комбинация ("ctrl+c", "alt+tab", "win+d", "ctrl+shift+esc")
- "press_key" | target: клавиша ("enter", "esc", "space", "tab"), extra: количество нажатий

4. Мышь и экран:
- "mouse_click" | target: "x,y", extra: "left" / "right" / "middle"
- "mouse_double_click" | target: "x,y"
- "mouse_move" | target: "x,y"
- "scroll" | target: число (например "-500" вниз, "500" вверх)
- "screenshot" | target: путь (или пусто), extra: "open"

5. Окна, звук, терминал и цепочки:
- "window" | target: часть заголовка окна, extra: "focus" / "minimize" / "maximize" / "close"
- "media" | target: "play_pause" / "next" / "prev" / "mute" / "vol_up" / "vol_down", extra: кол-во шагов
- "shell" | target: команда CMD (таймаут 15с)
- "powershell" | target: команда PowerShell (таймаут 15с)
- "batch" | content: JSON-массив шагов [{"action": "...", "target": "..."}, {"action": "sleep", "target": "0.5"}]

Правила:
- Для обычных разговоров отвечай текстом как обычно.
- Для проверки файлов и папок всегда предпочитай "read_file" и "list_dir". Когда нужно действие на ПК — выводи валидный JSON-блок. Если нужно сделать несколько действий подряд (например, открыть Блокнот -> подождать -> вставить текст), используй "batch".

Подтверди подключение одной короткой фразой: "⚡ Мост подключён. Готов управлять ПК."`;

function getAllElementsDeep(root = document) {
  const result = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  let node;
  while ((node = walker.nextNode())) {
    result.push(node);
    if (node.shadowRoot) result.push(...getAllElementsDeep(node.shadowRoot));
  }
  return result;
}

function extractJsonCommand(rawText) {
  if (!rawText) return null;
  const cleaned = rawText.replace(/\u200B|\u00A0/g, " ").trim();
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) return null;
  const candidate = cleaned.slice(start, end + 1);
  if (!candidate.includes('"action"')) return null;
  try {
    const obj = JSON.parse(candidate);
    if (obj && typeof obj.action === "string") return { obj, rawJson: candidate };
  } catch (e) {}
  return null;
}

function getBlockText(el) {
  return (el.textContent || el.innerText || "").trim();
}

function getAssistantContainers() {
  const allEls = getAllElementsDeep();
  if (!IS_DEEPSEEK) {
    return allEls.filter(el => el.tagName === "MODEL-RESPONSE");
  }
  // DeepSeek: ответы ассистента обычно содержат .ds-markdown (у сообщений юзера её нет)
  const mdBlocks = allEls.filter(el => el.matches && el.matches("pre, code")); if (mdBlocks.length) return mdBlocks; const _x = allEls.filter(el => el.matches && el.matches("pre, code"));
  if (mdBlocks.length > 0) return mdBlocks;
  // Фоллбэк: все блоки сообщений, кроме содержащих textarea
  return allEls.filter(el => el.matches && el.matches("[class*='markdown']"));
}

function isGenerating() { if (IS_DEEPSEEK) return false;
  const allEls = getAllElementsDeep();
  if (!IS_DEEPSEEK) {
    return allEls.some(el => el.tagName === "BUTTON" && /Stop|Остановить/i.test(el.getAttribute("aria-label") || ""));
  }
  // DeepSeek: проверяем кнопку остановки генерации (обычно квадрат стопа или aria-label Stop)
  const stopBtn = allEls.find(el =>
    (el.tagName === "BUTTON" || el.getAttribute("role") === "button") &&
    (/Stop|Остановить/i.test(el.getAttribute("aria-label") || "") ||
     /Stop|Остановить/i.test(el.textContent || ""))
  );
  if (stopBtn) return true;
  // Также в DeepSeek во время стриминга есть иконка остановки в кнопке отправки (rect внутри svg в области ввода)
  const ta = document.querySelector("textarea");
  if (ta && ta.parentElement && ta.parentElement.parentElement) {
    const box = ta.parentElement.parentElement;
  }
  return false;
}

setTimeout(() => {
  const responses = getAssistantContainers();
  responses.forEach((resp, idx) => {
    const innerEls = getAllElementsDeep(resp.shadowRoot || resp);
    for (const el of innerEls) {
      if (!el.matches || !el.matches("code-block, pre, code")) continue;
      const parsed = extractJsonCommand(getBlockText(el));
      if (parsed) executedSignatures.add(`msg_${idx}_${parsed.rawJson.replace(/\s+/g, "")}`);
    }
  });
  isReady = true;
}, 1500);

function collapseBlock(container, cmdObj, rawJson) {
  if (!container || container.dataset.bridgeCollapsed === "1") return;
  container.dataset.bridgeCollapsed = "1";

  const wrapper = document.createElement("details");
  wrapper.style.cssText = "background:#1e293b;border:1px solid #334155;border-radius:10px;padding:8px 14px;margin:8px 0;color:#e2e8f0;font-family:'Segoe UI',sans-serif;font-size:13px;cursor:pointer;";
  const summary = document.createElement("summary");
  summary.style.cssText = "font-weight:600;color:#38bdf8;list-style:none;outline:none;";
  summary.textContent = `⏳ Выполняю: ${cmdObj.action}...`;

  const codePreview = document.createElement("pre");
  codePreview.style.cssText = "margin-top:8px;padding:8px;background:#0f172a;border-radius:6px;font-size:12px;color:#94a3b8;overflow-x:auto;white-space:pre-wrap;";
  codePreview.textContent = rawJson;

  wrapper.appendChild(summary);
  wrapper.appendChild(codePreview);
  const msgRoot = container.closest("message-content, .model-response-text, .markdown, .ds-markdown") || container.parentElement;
  if (msgRoot) {
    Array.from(msgRoot.children).forEach(ch => {
      if (ch !== container && !ch.contains(container)) ch.style.display = "none";
    });
  }
  container.style.display = "none";
  container.parentNode.insertBefore(wrapper, container);

  chrome.runtime.sendMessage({ type: "EXEC_CMD", cmd: cmdObj }, (response) => {
    if (chrome.runtime.lastError || !response || !response.ok) {
      const errMsg = response?.message || chrome.runtime.lastError?.message || "Ошибка моста (проверь start.bat и F5)";
      summary.style.color = "#f87171";
      summary.textContent = `⚠️ ${errMsg}`;
      if (!cmdObj.no_reply) autoReplyToChat("⚡ Ошибка моста: " + errMsg.slice(0, 4000));
    } else {
      summary.style.color = "#4ade80";
      if (!cmdObj.no_reply) autoReplyToChat("⚡ " + (response.message || "Выполнено").slice(0, 4000));
      summary.textContent = `⚡ ${response.message || "Выполнено"}`;
    }
  });
}

function setReactTextareaValue(ta, text) {
  ta.focus();
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
  nativeSetter.call(ta, text);
  ta.dispatchEvent(new Event("input", { bubbles: true }));
  ta.dispatchEvent(new Event("change", { bubbles: true }));
}

function triggerDeepSeekSend(ta) {
  ta.dispatchEvent(new KeyboardEvent("keydown", {
    key: "Enter",
    code: "Enter",
    keyCode: 13,
    which: 13,
    bubbles: true,
    cancelable: true
  }));
}

function autoReplyToChat(replyText) {
  if (IS_DEEPSEEK) {
    const ta = document.querySelector("textarea");
    if (!ta) return;
    setReactTextareaValue(ta, replyText);
    setTimeout(() => triggerDeepSeekSend(ta), 300);
    return;
  }

  const allEls = getAllElementsDeep();
  const editable = allEls.find(el =>
    el.getAttribute && el.getAttribute("contenteditable") === "true" &&
    (el.getAttribute("role") === "textbox" || el.closest("rich-textarea"))
  ) || allEls.find(el => el.getAttribute && el.getAttribute("contenteditable") === "true");
  if (!editable) return;
  editable.focus();
  const ok = document.execCommand("insertText", false, replyText);
  if (!ok || !(editable.textContent || "").trim()) {
    editable.textContent = replyText;
  }
  editable.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: replyText }));
  setTimeout(() => {
    const freshEls = getAllElementsDeep();
    const sendBtn = freshEls.find(el =>
      el.tagName === "BUTTON" &&
      /Send|Отправить/i.test(el.getAttribute("aria-label") || "") &&
      !el.disabled && el.getAttribute("aria-disabled") !== "true"
    );
    if (sendBtn) {
      sendBtn.click();
    } else {
      editable.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
    }
  }, 400);
}

function scanLastResponse() {
  if (!isReady) return;
  if (isGenerating()) return;

  const responses = getAssistantContainers();
  if (responses.length === 0) return;

  const lastIndex = responses.length - 1;
  const lastResponse = responses[lastIndex];
  const innerEls = [lastResponse, ...getAllElementsDeep(lastResponse.shadowRoot || lastResponse)];

  for (const el of innerEls) {
    if (!el.matches || !el.matches("code-block, pre, code")) continue;
    const parsed = extractJsonCommand(getBlockText(el));
    if (!parsed) continue;
    if (parsed.obj.action === "название") continue;

    const signature = `msg_${lastIndex}_${parsed.rawJson.replace(/\s+/g, "")}`;
    if (executedSignatures.has(signature)) return;
    executedSignatures.add(signature);

    const outerContainer = el.closest("code-block") || el.closest(".md-code-block") || el.closest("pre") || el;
    collapseBlock(outerContainer, parsed.obj, parsed.rawJson);
    return;
  }
}

function sendActivationPrompt() {
  if (IS_DEEPSEEK) {
    const ta = document.querySelector("textarea");
    if (!ta) {
      alert("Не найдено поле ввода DeepSeek. Кликни в поле чата и попробуй снова.");
      return;
    }
    setReactTextareaValue(ta, BRIDGE_SYSTEM_PROMPT);
    setTimeout(() => triggerDeepSeekSend(ta), 250);
    return;
  }

  const allEls = getAllElementsDeep();
  const inputBox = allEls.find(el =>
    (el.getAttribute && el.getAttribute("contenteditable") === "true" && el.getAttribute("role") === "textbox") ||
    el.tagName === "RICH-TEXTAREA"
  );

  const editable = inputBox?.querySelector?.('[contenteditable="true"]') || inputBox;
  if (!editable) {
    alert("Не найдено поле ввода Gemini. Кликни в поле чата и попробуй снова.");
    return;
  }

  editable.focus();
  document.execCommand("insertText", false, BRIDGE_SYSTEM_PROMPT);

  setTimeout(() => {
    const freshEls = getAllElementsDeep();
    const sendBtn = freshEls.find(el =>
      el.tagName === "BUTTON" &&
      /Send|Отправить/i.test(el.getAttribute("aria-label") || "") &&
      !el.disabled
    );
    if (sendBtn) sendBtn.click();
  }, 250);
}

function injectBridgeUI() {
  const allEls = getAllElementsDeep();
  const existingBtn = allEls.find(el => el.id === "gemini-pc-bridge-btn");
  if (existingBtn) return;

  const anchorBtn = !IS_DEEPSEEK ? allEls.find(el =>
    el.tagName === "BUTTON" &&
    /Send|Отправить|Microphone|Микрофон/i.test(el.getAttribute("aria-label") || "")
  ) : null;

  const btn = document.createElement("button");
  btn.id = "gemini-pc-bridge-btn";
  btn.type = "button";
  btn.title = "Активировать управление ПК в этом чате";
  btn.innerHTML = `<span id="bridge-status-dot" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#f87171;margin-right:6px;"></span>⚡ PC Bridge`;

  Object.assign(btn.style, {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    height: "34px",
    padding: "0 12px",
    marginRight: "6px",
    borderRadius: "18px",
    border: "1px solid #334155",
    backgroundColor: "#1e293b",
    color: "#e2e8f0",
    fontFamily: "'Segoe UI', sans-serif",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
    transition: "all 0.2s ease",
    zIndex: "9999"
  });

  btn.onmouseenter = () => {
    btn.style.backgroundColor = "#334155";
    btn.style.borderColor = "#38bdf8";
  };
  btn.onmouseleave = () => {
    btn.style.backgroundColor = "#1e293b";
    btn.style.borderColor = "#334155";
  };

  btn.onclick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    btn.style.borderColor = "#4ade80";
    btn.style.color = "#4ade80";
    sendActivationPrompt();
    setTimeout(() => {
      btn.style.borderColor = "#334155";
      btn.style.color = "#e2e8f0";
    }, 1500);
  };

  if (anchorBtn && anchorBtn.parentElement) {
    anchorBtn.parentElement.insertBefore(btn, anchorBtn);
  } else {
    btn.style.position = "fixed";
    btn.style.bottom = IS_DEEPSEEK ? "18px" : "20px";
    btn.style.right = "20px";
    document.body.appendChild(btn);
  }

  updateBridgeStatus();
}

function showUpdateBadge(anchorParent, info) {
  const allEls = getAllElementsDeep();
  let badge = allEls.find(el => el.id === "bridge-update-badge");
  if (!info || !info.hasUpdate) {
    if (badge) badge.remove();
    return;
  }
  if (!badge) {
    badge = document.createElement("button");
    badge.id = "bridge-update-badge";
    badge.type = "button";
    Object.assign(badge.style, {
      display: "inline-flex",
      alignItems: "center",
      height: "34px",
      padding: "0 12px",
      marginRight: "6px",
      borderRadius: "18px",
      border: "1px solid #f59e0b",
      backgroundColor: "#451a03",
      color: "#fbbf24",
      fontFamily: "'Segoe UI', sans-serif",
      fontSize: "12px",
      fontWeight: "700",
      cursor: "pointer",
      zIndex: "9999"
    });
    badge.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      badge.textContent = "⏳ Обновляю с GitHub...";
      chrome.runtime.sendMessage({ type: "GIT_SYNC", mode: "pull" }, (r) => {
        if (r && r.ok) {
          badge.style.borderColor = "#4ade80";
          badge.style.color = "#4ade80";
          badge.textContent = "✅ Обновлено! Перезапусти start.bat";
          setTimeout(() => badge.remove(), 5000);
        } else {
          badge.textContent = "⚠️ Ошибка git pull";
        }
      });
    };
    if (anchorParent) anchorParent.insertBefore(badge, anchorParent.firstChild);
    else document.body.appendChild(badge);
  }
  badge.title = info.changelog || "Доступна новая версия на GitHub";
  badge.textContent = `⬆️ Обновить v${info.remoteVersion}`;
}

function updateBridgeStatus() {
  const allEls = getAllElementsDeep();
  const dot = allEls.find(el => el.id === "bridge-status-dot");
  const btn = allEls.find(el => el.id === "gemini-pc-bridge-btn");
  if (!dot) return;

  chrome.runtime.sendMessage({ type: "PING_BRIDGE" }, (res) => {
    if (chrome.runtime.lastError || !res || !res.online) {
      dot.style.background = "#f87171";
      showUpdateBadge(null, null);
    } else {
      dot.style.background = "#4ade80";
      showUpdateBadge(btn?.parentElement, res);
    }
  });
}

setInterval(scanLastResponse, 500);
setInterval(injectBridgeUI, 1500);
setInterval(updateBridgeStatus, 4000);
