import os
import time
import glob
import shutil
import ctypes
import threading
import subprocess
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
import pyautogui
from PIL import ImageGrab
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Any
import json
from pydantic import BaseModel, field_validator
import uvicorn

pyautogui.FAILSAFE = False

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

last_cmd_signature = ""
last_cmd_time = 0.0



def set_clipboard_image(img_path: str):
    safe_p = img_path.replace("'", "''")
    ps = f"Add-Type -AssemblyName System.Windows.Forms,System.Drawing; $img = [System.Drawing.Image]::FromFile('{safe_p}'); [System.Windows.Forms.Clipboard]::SetImage($img); $img.Dispose()"
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, creationflags=CREATE_NO_WINDOW)

def send_clipboard_to_active_window():
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.15)
    pyautogui.press("enter")

class CommandPayload(BaseModel):
    action: str
    target: str = ""
    content: Any = ""
    extra: str = ""
    report: str = ""

    @field_validator('content', mode='before')
    @classmethod
    def coerce_content(cls, v):
        if v is None:
            return ""
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)


def set_clipboard_utf16(text: str):
    """РљР»Р°РґС‘С‚ Р»СЋР±РѕР№ С‚РµРєСЃС‚ (РІРєР»СЋС‡Р°СЏ РєРёСЂРёР»Р»РёС†Сѓ Рё РјРЅРѕРіРѕСЃС‚СЂРѕС‡РЅС‹Р№ РєРѕРґ) РІ Р±СѓС„РµСЂ РѕР±РјРµРЅР° Windows Р±РµР· СЃС‚РѕСЂРѕРЅРЅРёС… Р±РёР±Р»РёРѕС‚РµРє."""
    ps_cmd = "Set-Clipboard -Value $input"
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        input=text.encode("utf-8"),
        check=True,
        creationflags=CREATE_NO_WINDOW
    )


def expand_user_path(raw_path: str) -> str:
    """РџСЂРµРІСЂР°С‰Р°РµС‚ РєРѕСЂРѕС‚РєРёРµ РїСѓС‚Рё РІСЂРѕРґРµ Desktop/test.py РІ РїРѕР»РЅС‹Р№ РїСѓС‚СЊ Windows."""
    p = os.path.expandvars(os.path.expanduser(raw_path.strip()))
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if p.lower().startswith(("desktop\\", "desktop/", "СЂР°Р±РѕС‡РёР№ СЃС‚РѕР»\\", "СЂР°Р±РѕС‡РёР№ СЃС‚РѕР»/")):
        rel = p.split("\\", 1)[-1].split("/", 1)[-1]
        return os.path.join(desktop, rel)
    if not os.path.isabs(p):
        return os.path.join(desktop, p)
    return p


def find_and_launch_app(app_name: str):
    query = app_name.lower().strip().replace(".exe", "")

    system_tools = {
        "calc": "calc.exe",
        "РєР°Р»СЊРєСѓР»СЏС‚РѕСЂ": "calc.exe",
        "notepad": "notepad.exe",
        "Р±Р»РѕРєРЅРѕС‚": "notepad.exe",
        "taskmgr": "taskmgr.exe",
        "РґРёСЃРїРµС‚С‡РµСЂ Р·Р°РґР°С‡": "taskmgr.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "explorer": "explorer.exe",
        "РїСЂРѕРІРѕРґРЅРёРє": "explorer.exe",
        "paint": "mspaint.exe",
        "settings": "ms-settings:",
        "РЅР°СЃС‚СЂРѕР№РєРё": "ms-settings:",
    }
    if query in system_tools:
        os.startfile(system_tools[query]) if ":" in system_tools[query] else subprocess.Popen(system_tools[query], shell=True, creationflags=CREATE_NO_WINDOW)
        return f"Р—Р°РїСѓС‰РµРЅРѕ: {system_tools[query]}"

    search_dirs = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        os.path.expandvars(r"%PUBLIC%\Desktop"),
    ]

    for base_dir in search_dirs:
        if not os.path.exists(base_dir):
            continue
        for root, _, files in os.walk(base_dir):
            for file in files:
                if file.lower().endswith((".lnk", ".exe", ".url")):
                    name_no_ext = os.path.splitext(file)[0].lower()
                    if "uninstall" in name_no_ext or "СѓРґР°Р»РёС‚СЊ" in name_no_ext:
                        continue
                    if query in name_no_ext:
                        os.startfile(os.path.join(root, file))
                        return f"Р—Р°РїСѓС‰РµРЅРѕ: {file}"

    exe_dirs = [
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        os.path.expandvars(r"%LOCALAPPDATA%"),
        os.path.expandvars(r"%APPDATA%"),
    ]
    for base_dir in exe_dirs:
        if not os.path.exists(base_dir):
            continue
        base_depth = base_dir.rstrip(os.sep).count(os.sep)
        for root, dirs, files in os.walk(base_dir):
            if root.count(os.sep) - base_depth > 3:
                del dirs[:]
                continue
            for file in files:
                if file.lower().endswith(".exe"):
                    name_no_ext = os.path.splitext(file)[0].lower()
                    if query == name_no_ext or (len(query) >= 4 and query in name_no_ext and "uninstall" not in name_no_ext):
                        subprocess.Popen([os.path.join(root, file)])
                        return f"Р—Р°РїСѓС‰РµРЅРѕ: {file}"

    return f"РќРµ РЅР°Р№РґРµРЅРѕ: {app_name}"


def manage_window(mode: str, title_query: str) -> str:
    """РЈРїСЂР°РІР»РµРЅРёРµ РѕРєРЅР°РјРё РїРѕ С‡Р°СЃС‚Рё Р·Р°РіРѕР»РѕРІРєР°: focus, minimize, maximize, close."""
    user32 = ctypes.windll.user32
    q = title_query.lower().strip()
    matched = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                if q in buff.value.lower():
                    matched.append((hwnd, buff.value))
        return True

    user32.EnumWindows(enum_cb, 0)
    if not matched:
        return f"РћРєРЅРѕ В«{title_query}В» РЅРµ РЅР°Р№РґРµРЅРѕ"

    hwnd, title = matched[0]
    if mode == "focus":
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        return f"РђРєС‚РёРІРёСЂРѕРІР°РЅРѕ РѕРєРЅРѕ: {title}"
    elif mode == "minimize":
        user32.ShowWindow(hwnd, 6)
        return f"РЎРІС‘СЂРЅСѓС‚Рѕ РѕРєРЅРѕ: {title}"
    elif mode == "maximize":
        user32.ShowWindow(hwnd, 3)
        return f"Р Р°Р·РІС‘СЂРЅСѓС‚Рѕ РѕРєРЅРѕ: {title}"
    elif mode == "close":
        user32.PostMessageW(hwnd, 0x0010, 0, 0)
        return f"Р—Р°РєСЂС‹С‚Рѕ РѕРєРЅРѕ: {title}"
    return f"РќРµРёР·РІРµСЃС‚РЅС‹Р№ СЂРµР¶РёРј РѕРєРЅР°: {mode}"


def run_action(cmd: CommandPayload) -> str:
    action = cmd.action.strip().lower()
    target = cmd.target.strip()
    content = cmd.content
    extra = cmd.extra.strip()

    try:
        # 1. РџР РћР“Р РђРњРњР« Р РџР РћР¦Р•РЎРЎР«
        if action == "open_app":
            return find_and_launch_app(target)

        elif action == "kill_app":
            name = target if target.lower().endswith(".exe") else f"{target}.exe"
            subprocess.run(f'taskkill /F /IM "{name}"', shell=True, creationflags=CREATE_NO_WINDOW, capture_output=True)
            return f"РџСЂРѕС†РµСЃСЃ Р·Р°РІРµСЂС€С‘РЅ: {name}"

        elif action == "open_url":
            os.startfile(target)
            return f"РћС‚РєСЂС‹С‚Р° СЃСЃС‹Р»РєР°: {target}"

        # 2. Р¤РђР™Р›Р« Р РљРћР” РќРђ Р”РРЎРљР•
        elif action == "write_file":
            full_path = expand_user_path(target)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            if extra.lower() == "open":
                os.startfile(full_path)
            elif extra.lower() == "run" and full_path.lower().endswith(".py"):
                subprocess.Popen(f'start cmd /k python "{full_path}"', shell=True)
            return f"Р¤Р°Р№Р» Р·Р°РїРёСЃР°РЅ ({len(content)} СЃРёРјРІ.): {full_path}"

        elif action == "append_file":
            full_path = expand_user_path(target)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "a", encoding="utf-8") as f:
                f.write("\n" + content)
            return f"Р”РѕРїРёСЃР°РЅРѕ РІ С„Р°Р№Р»: {full_path}"

        elif action == "delete_path":
            full_path = expand_user_path(target)
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
                return f"РџР°РїРєР° СѓРґР°Р»РµРЅР°: {full_path}"
            elif os.path.isfile(full_path):
                os.remove(full_path)
                return f"Р¤Р°Р№Р» СѓРґР°Р»С‘РЅ: {full_path}"
            return f"РџСѓС‚СЊ РЅРµ РЅР°Р№РґРµРЅ: {full_path}"

        elif action == "open_path":
            full_path = expand_user_path(target)
            os.startfile(full_path)
            return f"РћС‚РєСЂС‹С‚Рѕ: {full_path}"

        # 3. Р’Р’РћР” РўР•РљРЎРўРђ, РљРћР”Рђ Р’ РћРљРќРђ Р РљР›РђР’РРђРўРЈР Рђ
        elif action == "paste_text":
            text_to_paste = content if content else target
            set_clipboard_utf16(text_to_paste)
            time.sleep(0.15)
            pyautogui.hotkey("ctrl", "v")
            if extra.lower() == "enter":
                time.sleep(0.05)
                pyautogui.press("enter")
            return f"Р’СЃС‚Р°РІР»РµРЅ С‚РµРєСЃС‚ ({len(text_to_paste)} СЃРёРјРІ.)"

        elif action == "type_text":
            pyautogui.write(target, interval=0.02)
            return "РўРµРєСЃС‚ РЅР°РїРµС‡Р°С‚Р°РЅ"

        elif action == "hotkey":
            keys = [k.strip().lower() for k in target.split("+")]
            pyautogui.hotkey(*keys)
            return f"РќР°Р¶Р°С‚Рѕ: {target}"

        elif action == "press_key":
            count = int(extra) if extra.isdigit() else 1
            for _ in range(count):
                pyautogui.press(target.lower())
                time.sleep(0.05)
            return f"РљР»Р°РІРёС€Р° {target} РЅР°Р¶Р°С‚Р° ({count}x)"

        # 4. РњР«РЁР¬ Р Р­РљР РђРќ
        elif action == "mouse_click":
            x, y = map(int, target.replace(" ", "").split(","))
            btn = extra.lower() if extra.lower() in ("left", "right", "middle") else "left"
            pyautogui.click(x, y, button=btn)
            return f"РљР»РёРє ({btn}): {x},{y}"

        elif action == "mouse_double_click":
            x, y = map(int, target.replace(" ", "").split(","))
            pyautogui.doubleClick(x, y)
            return f"Р”РІРѕР№РЅРѕР№ РєР»РёРє: {x},{y}"

        elif action == "mouse_move":
            x, y = map(int, target.replace(" ", "").split(","))
            pyautogui.moveTo(x, y, duration=0.25)
            return f"РљСѓСЂСЃРѕСЂ РїРµСЂРµРјРµС‰С‘РЅ: {x},{y}"

        elif action == "scroll":
            amount = int(target)
            pyautogui.scroll(amount)
            return f"РџСЂРѕРєСЂСѓС‚РєР°: {amount}"

        elif action == "screenshot":
            save_path = expand_user_path(target) if target else expand_user_path(f"screenshot_{int(time.time())}.png")
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            img = ImageGrab.grab()
            img.save(save_path)
            if extra.lower() == "open":
                os.startfile(save_path)
            try:
                set_clipboard_image(save_path)
            except Exception:
                pass
            if extra.lower() == "send" or cmd.report.strip().lower() == "send":
                try:
                    send_clipboard_to_active_window()
                except Exception:
                    pass
            return f"РЎРєСЂРёРЅС€РѕС‚ СЃРѕС…СЂР°РЅС‘РЅ: {save_path}"

        # 5. РћРљРќРђ, Р—Р’РЈРљ Р РўР•Р РњРРќРђР›
        elif action == "window":
            mode = extra.lower() if extra else "focus"
            return manage_window(mode, target)

        elif action == "media":
            cmd_map = {
                "play_pause": "playpause",
                "pause": "playpause",
                "next": "nexttrack",
                "prev": "prevtrack",
                "mute": "volumemute",
                "vol_up": "volumeup",
                "vol_down": "volumedown",
            }
            key = cmd_map.get(target.lower(), target.lower())
            steps = int(extra) if extra.isdigit() else 1
            for _ in range(steps):
                pyautogui.press(key)
            return f"РњРµРґРёР°: {target}"

        elif action == "shell":
            try:
                res = subprocess.run(target, shell=True, creationflags=CREATE_NO_WINDOW, capture_output=True, text=True, encoding="cp866", errors="ignore", timeout=15)
                out = (res.stdout or res.stderr).strip()
                return f"CMD: {out[:4000]}" if out else "РљРѕРјР°РЅРґР° РІС‹РїРѕР»РЅРµРЅР°"
            except subprocess.TimeoutExpired:
                return "вљ пёЏ РўР°Р№РјР°СѓС‚ (15СЃ): CMD-РєРѕРјР°РЅРґР° Р·Р°РІРёСЃР»Р° Рё РїСЂРµСЂРІР°РЅР°"

        elif action == "powershell":
            try:
                res = subprocess.run(["powershell", "-NoProfile", "-Command", target], capture_output=True, text=True, encoding="cp866", errors="ignore", timeout=15)
                out = (res.stdout or res.stderr).strip()
                return f"PS: {out[:4000]}" if out else "PowerShell РІС‹РїРѕР»РЅРµРЅ"
            except subprocess.TimeoutExpired:
                return "вљ пёЏ РўР°Р№РјР°СѓС‚ (15СЃ): PowerShell-РєРѕРјР°РЅРґР° Р·Р°РІРёСЃР»Р° Рё РїСЂРµСЂРІР°РЅР°"

        elif action == "read_file":
            full_path = target if os.path.isabs(str(target)) else os.path.join(os.path.expanduser("~"), "Desktop", str(target))
            if not os.path.exists(full_path):
                return f"Р¤Р°Р№Р» РЅРµ РЅР°Р№РґРµРЅ: {full_path}"
            with open(full_path, "r", encoding="utf-8", errors="replace") as rf:
                lines = rf.readlines()
            if extra and ":" in str(extra):
                parts = str(extra).split(":")
                s = int(parts[0]) - 1 if parts[0] else 0
                e = int(parts[1]) if parts[1] else len(lines)
                lines = lines[max(0, s):e]
            txt = "".join(lines)
            if len(txt) > 3800:
                txt = txt[:3800] + "\n... [РѕР±СЂРµР·Р°РЅРѕ]"
            return f"рџ“„ {os.path.basename(full_path)}:\n{txt}"

        elif action == "list_dir":
            full_path = target if os.path.isabs(str(target)) else os.path.join(os.path.expanduser("~"), "Desktop", str(target)) if target else expand_user_path("")
            if not os.path.exists(full_path):
                return f"РџР°РїРєР° РЅРµ РЅР°Р№РґРµРЅР°: {full_path}"
            items = [f"рџ“Ѓ {n}/" if os.path.isdir(os.path.join(full_path, n)) else f"рџ“„ {n}" for n in sorted(os.listdir(full_path))[:100]]
            return f"рџ“‚ {full_path}:\n" + ("\n".join(items) if items else "(РїСѓСЃС‚Рѕ)")

        elif action == "git_push":
            repo_dir = os.path.dirname(os.path.abspath(__file__))
            commit_msg = content if content else (target if target else "fix: update ai-bridge")
            vp = os.path.join(repo_dir, "version.json")
            new_v = "6.3"
            try:
                cur = {"version": "6.2", "changelog": commit_msg}
                if os.path.exists(vp):
                    with open(vp, "r", encoding="utf-8") as vf:
                        cur = json.load(vf)
                parts = str(cur.get("version", "6.2")).split(".")
                parts[-1] = str(int(parts[-1]) + 1)
                new_v = ".".join(parts)
                with open(vp, "w", encoding="utf-8") as vf:
                    json.dump({"version": new_v, "changelog": commit_msg}, vf, ensure_ascii=False, indent=2)
            except Exception:
                pass
            subprocess.run(["git", "-C", repo_dir, "add", "-A"], capture_output=True, timeout=10)
            subprocess.run(["git", "-C", repo_dir, "commit", "-m", f"v{new_v}: {commit_msg}"], capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=10)
            res = subprocess.run(["git", "-C", repo_dir, "push"], capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=15)
            out = (res.stdout or res.stderr).strip()
            return f"GitHub РѕР±РЅРѕРІР»С‘РЅ (v{new_v}): {out[:500]}"

        elif action == "batch":
            import json as _json
            steps = _json.loads(content if content else target)
            results = []
            for step in steps:
                act = step.get("action", "")
                if act == "sleep":
                    time.sleep(float(step.get("target", 0.3)))
                else:
                    results.append(run_action(CommandPayload(**step)))
            return " -> ".join(results)

        elif action == "ps_b64":
            try:
                import base64 as _b64
                ps_script = _b64.b64decode(target).decode("utf-8")
                res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True, encoding="cp866", errors="ignore", timeout=15)
                out = (res.stdout or res.stderr).strip()
                return f"PS: {out[:4000]}" if out else "PS_B64 РІС‹РїРѕР»РЅРµРЅ"
            except subprocess.TimeoutExpired:
                return "вљ пёЏ РўР°Р№РјР°СѓС‚ (15СЃ): PS_B64-РєРѕРјР°РЅРґР° Р·Р°РІРёСЃР»Р° Рё РїСЂРµСЂРІР°РЅР°"

        elif action == 'chat_send':
            txt = content if content else target
            set_clipboard_utf16(txt)
            send_clipboard_to_active_window()
            return f'CHAT_SENT ({len(txt)})'

        elif action == 'full_check':
            res = subprocess.run(['python', os.path.join(os.path.dirname(__file__), '_self_inspect.py')], capture_output=True, text=True, encoding='utf-8', errors='ignore')
            report_txt = (res.stdout or res.stderr).strip()[-3800:]
            if extra.lower() == 'send' or cmd.report.strip().lower() == 'send':
                set_clipboard_utf16(report_txt)
                send_clipboard_to_active_window()
            return report_txt

        elif action == "py_b64":
            import base64 as _b64
            py_script = _b64.b64decode(target).decode("utf-8")
            tmp_py = os.path.join(os.path.dirname(__file__), "_tmp_task.py")
            with open(tmp_py, "w", encoding="utf-8") as f:
                f.write(py_script)
            res = subprocess.run(["python", tmp_py], capture_output=True, text=True, encoding="utf-8", errors="ignore")
            out = (res.stdout or res.stderr).strip()
            return f"PY: {out[:4000]}" if out else "PY_B64 РІС‹РїРѕР»РЅРµРЅ"

        return f"РќРµРёР·РІРµСЃС‚РЅР°СЏ РєРѕРјР°РЅРґР°: {action}"
    except Exception as e:
        return f"РћС€РёР±РєР° ({action}): {e}"


@app.get("/status")
def get_status():
    import urllib.request
    local_v = "6.2"
    try:
        vp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json")
        if os.path.exists(vp):
            with open(vp, "r", encoding="utf-8") as vf:
                local_v = str(json.load(vf).get("version", "6.2"))
    except Exception:
        pass
    remote_v = local_v
    changelog = ""
    for branch in ("main", "master"):
        try:
            req = urllib.request.Request(
                f"https://raw.githubusercontent.com/BratTIm1/ai-bridge/{branch}/version.json?t={int(time.time())}",
                headers={"User-Agent": "AI-Bridge"}
            )
            with urllib.request.urlopen(req, timeout=2) as r:
                data = json.loads(r.read().decode("utf-8"))
                remote_v = str(data.get("version", local_v))
                changelog = str(data.get("changelog", ""))
                break
        except Exception:
            pass
    return {"online": True, "local_version": local_v, "remote_version": remote_v, "has_update": remote_v != local_v, "changelog": changelog}


@app.post("/git_sync")
def git_sync(payload: dict = None):
    mode = (payload or {}).get("mode", "pull")
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    if mode == "pull":
        res = subprocess.run(["git", "-C", repo_dir, "pull"], capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=15)
        out = (res.stdout or res.stderr).strip()
        return {"status": "ok" if res.returncode == 0 else "error", "message": out or "РћР±РЅРѕРІР»РµРЅРѕ"}
    elif mode == "push":
        msg = (payload or {}).get("message", "auto: update ai-bridge")
        subprocess.run(["git", "-C", repo_dir, "add", "-A"], capture_output=True, timeout=10)
        subprocess.run(["git", "-C", repo_dir, "commit", "-m", msg], capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=10)
        res = subprocess.run(["git", "-C", repo_dir, "push"], capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=15)
        out = (res.stdout or res.stderr).strip()
        return {"status": "ok" if res.returncode == 0 else "error", "message": out or "РћС‚РїСЂР°РІР»РµРЅРѕ РІ GitHub"}
    return {"status": "error", "message": "Unknown mode"}


@app.post("/exec")
def execute_command(cmd: CommandPayload):
    global last_cmd_signature, last_cmd_time
    now = time.time()
    sig = f"{cmd.action}:{cmd.target}:{len(cmd.content)}"

    if sig == last_cmd_signature and (now - last_cmd_time) < 3.0:
        return {"status": "ignored", "message": "Р”СѓР±Р»СЊ Р·Р°Р±Р»РѕРєРёСЂРѕРІР°РЅ"}

    last_cmd_signature = sig
    last_cmd_time = now

    print(f"\n[рџ“Ґ РљРѕРјР°РЅРґР°] {cmd.action} | target={cmd.target} | extra={cmd.extra}")
    msg = run_action(cmd)
    out_log = os.path.join(os.path.dirname(__file__), "last_output.txt")
    with open(out_log, "w", encoding="utf-8") as lf:
        lf.write(f"ACTION: {cmd.action}\nTARGET: {cmd.target}\nRESULT:\n{msg}\n")
    if cmd.report.strip().lower() == "send":
        try:
            set_clipboard_utf16(f"[{cmd.action}] {cmd.target}\n{msg}")
            send_clipboard_to_active_window()
        except Exception as e:
            print(f"[вљ пёЏ РђРІС‚Рѕ-РѕС‚РїСЂР°РІРєР°] {e}")
    print(f"[вњ… Р“РѕС‚РѕРІРѕ] {msg}")
    return {"status": "ok", "message": msg}


if __name__ == "__main__":
    print("=" * 55)
    print("рџљЂ AI Bridge FULL CONTROL v6.2 Р·Р°РїСѓС‰РµРЅ (127.0.0.1:8000)")
    print("рџ§° РРЅСЃС‚СЂСѓРјРµРЅС‚С‹: С„Р°Р№Р»С‹, РєРѕРґ, Р±СѓС„РµСЂ, РјС‹С€СЊ, РѕРєРЅР°, Р·РІСѓРє, PS")
    print("=" * 55)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")
