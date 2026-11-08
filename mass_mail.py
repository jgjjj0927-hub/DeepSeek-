# language: Python, file: mass_mail.py
# *Alt+Insert — окно рассылки; SMTP из mail_config.json*
import os, sys, re, json, time, smtplib, threading, pathlib
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import keyboard

CONFIG_PATH = pathlib.Path(__file__).parent / "mail_config.json"
DEFAULT_CFG = {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_pass": "",
    "from_name": "Updater",
    "subject": "Important update",
    "body": "Please check the attached file.",
    "delay_sec": 3,
    "attach_file": "",
}

class MailWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Рассылка")
        self.geometry("640x580")
        self.attributes("-topmost", True)
        self.cfg = self._load_cfg()
        self._ui()

    def _load_cfg(self):
        if CONFIG_PATH.exists():
            try:
                return {**DEFAULT_CFG, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
            except Exception:
                pass
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CFG, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        return dict(DEFAULT_CFG)

    def _ui(self):
        p = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self); frm.pack(fill="both", expand=True, padx=10, pady=10)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="SMTP").grid(row=0, column=0, sticky="w", **p)
        ttk.Label(frm, text=f"{self.cfg['smtp_host']}:{self.cfg['smtp_port']} "
                            f"({self.cfg['smtp_user'] or 'не настроено'})"
                 ).grid(row=0, column=1, sticky="w", **p)

        ttk.Label(frm, text="Получатели (по одному на строку)"
                 ).grid(row=1, column=0, columnspan=3,
