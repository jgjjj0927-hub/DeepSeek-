# language: Python, file: mass_mail.py
# *Alt+Insert — окно рассылки; SMTP-креды из mail_config.json рядом с файлом*
import os, sys, re, json, time, smtplib, threading, pathlib, queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

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
        self.geometry("680x600")
        self.attributes("-topmost", True)
        self.cfg = self._load_cfg()
        self._stop_flag = threading.Event()
        self._ui()

    def _load_cfg(self):
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                return {**DEFAULT_CFG, **raw}
            except Exception:
                pass
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CFG, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        return dict(DEFAULT_CFG)

    def _ui(self):
        p = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="SMTP").grid(row=0, column=0, sticky="w", **p)
        self.smtp_label = ttk.Label(
            frm,
            text=f"{self.cfg['smtp_host']}:{self.cfg['smtp_port']}  "
                 f"({self.cfg['smtp_user'] or 'не настроено'})")
        self.smtp_label.grid(row=0, column=1, columnspan=2, sticky="w", **p)

        ttk.Label(frm, text="Получатели (по одному на строку)"
                 ).grid(row=1, column=0, columnspan=3, sticky="w", **p)
        self.txt_to = tk.Text(frm, height=9, width=72)
        self.txt_to.grid(row=2, column=0, columnspan=3, sticky="ew", **p)

        ttk.Label(frm, text="Тема").grid(row=3, column=0, sticky="w", **p)
        self.var_subj = tk.StringVar(value=self.cfg["subject"])
        ttk.Entry(frm, textvariable=self.var_subj).grid(
            row=3, column=1, columnspan=2, sticky="ew", **p)

        ttk.Label(frm, text="Текст").grid(row=4, column=0, sticky="nw", **p)
        self.txt_body = tk.Text(frm, height=6, width=72)
        self.txt_body.insert("1.0", self.cfg["body"])
        self.txt_body.grid(row=4, column=0, columnspan=3, sticky="ew", **p)

        ttk.Label(frm, text="Вложение").grid(row=5, column=0, sticky="w", **p)
        self.var_att = tk.StringVar(value=self.cfg["attach_file"])
        ttk.Entry(frm, textvariable=self.var_att).grid(
            row=5, column=1, sticky="ew", **p)
        ttk.Button(frm, text="...", width=3, command=self._pick_attach).grid(
            row=5, column=2, sticky="w", **p)

        ttk.Label(frm, text="Задержка между письмами, сек"
                 ).grid(row=6, column=0, sticky="w", **p)
        self.var_delay = tk.DoubleVar(value=self.cfg["delay_sec"])
        ttk.Spinbox(frm, from_=1, to=60, textvariable=self.var_delay, width=6
                    ).grid(row=6, column=1, sticky="w", **p)

        btns = ttk.Frame(frm)
        btns.grid(row=7, column=0, columnspan=3, sticky="ew", pady=10)
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)
        self.btn_send = ttk.Button(btns, text="Начать рассылку", command=self._start)
        self.btn_send.grid(row=0, column=0, sticky="ew", padx=4)
        self.btn_stop = ttk.Button(btns, text="Стоп", command=self._stop,
                                   state="disabled")
        self.btn_stop.grid(row=0, column=1, sticky="ew", padx=4)

        self.progress = ttk.Progressbar(frm, mode="determinate")
        self.progress.grid(row=8, column=0, columnspan=3, sticky="ew", **p)

        ttk.Label(frm, text="Лог").grid(row=9, column=0, sticky="w", **p)
        self.log = tk.Text(frm, height=9, width=72, state="disabled")
        self.log.grid(row=10, column=0, columnspan=3, sticky="ew", **p)

    def _pick_attach(self):
        path = filedialog.askopenfilename()
        if path:
            self.var_att.set(path)

    def _log(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    @staticmethod
    def _parse_recipients(raw):
        emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", raw)
        seen, out = set(), []
        for e in emails:
            low = e.lower()
            if low not in seen:
                seen.add(low)
                out.append(e)
        return out

    def _start(self):
        if not self.cfg["smtp_user"] or not self.cfg["smtp_pass"]:
            messagebox.showerror("Ошибка",
                                 "SMTP не настроен. Заполните mail_config.json.")
            return
        recipients = self._parse_recipients(self.txt_to.get("1.0", "end"))
        if not recipients:
            messagebox.showerror("Ошибка", "Не найдено ни одного адреса.")
            return
        att = self.var_att.get().strip()
        if att and not os.path.isfile(att):
            messagebox.showerror("Ошибка", "Файл вложения не найден.")
            return
        if not messagebox.askyesno(
                "Подтверждение",
                f"Отправить письмо на {len(recipients)} адрес(ов)?\n"
                f"От: {self.cfg['smtp_user']}\n"
                f"Через: {self.cfg['smtp_host']}"):
            return
        self._stop_flag.clear()
        self.btn_send.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.progress.configure(maximum=len(recipients), value=0)
        threading.Thread(
            target=self._send_all,
            args=(recipients, self.var_subj.get(),
                  self.txt_body.get("1.0", "end"),
                  att, float(self.var_delay.get())),
            daemon=True).start()

    def _stop(self):
        self._stop_flag.set()
        self._log("[!] остановка запрошена")

    def _send_all(self, recipients, subject, body, attachment, delay):
        ok, fail = 0, 0
        att_name, att_data = None, None
        if attachment:
            att_name = os.path.basename(attachment)
            try:
                with open(attachment, "rb") as f:
                    att_data = f.read()
            except OSError as e:
                self._log(f"[!] не читается вложение: {e}")
                attachment = ""
                att_data = None
        try:
            s = smtplib.SMTP(self.cfg["smtp_host"],
                             int(self.cfg["smtp_port"]), timeout=30)
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(self.cfg["smtp_user"], self.cfg["smtp_pass"])
        except smtplib.SMTPAuthenticationError:
            self._log("[!] ошибка аутентификации: app password, не основной пароль")
            self.after(0, self._done)
            return
        except Exception as e:
            self._log(f"[!] SMTP: {e}")
            self.after(0, self._done)
            return

        try:
            for i, rcpt in enumerate(recipients, 1):
                if self._stop_flag.is_set():
                    self._log("[!] остановлено пользователем")
                    break
                msg = MIMEMultipart()
                msg["From"] = f"{self.cfg['from_name']} <{self.cfg['smtp_user']}>"
                msg["To"] = rcpt
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain", "utf-8"))
                if att_data:
                    part = MIMEApplication(att_data)
                    part.add_header("Content-Disposition", "attachment",
                                    filename=att_name)
                    msg.attach(part)
                try:
                    s.send_message(msg)
                    ok += 1
                    self.after(0, self._log, f"[{i}/{len(recipients)}] -> {rcpt}  ok")
                except smtplib.SMTPException as e:
                    fail += 1
                    self.after(0, self._log,
                               f"[{i}/{len(recipients)}] -> {rcpt}  FAIL: {e}")
                self.after(0, self.progress.configure, {"value": i})
                time.sleep(max(1.0, delay))
        finally:
            try:
                s.quit()
            except Exception:
                pass
            self.after(0, self._log, f"[i] итог: ok={ok}, fail={fail}")
            self.after(0, self._done)

    def _done(self):
        self.btn_send.configure(state="normal")
        self.btn_stop.configure(state="disabled")

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.window = None
        if HAS_KEYBOARD:
            try:
                keyboard.add_hotkey("alt+insert", self._schedule_show)
            except Exception:
                pass
        self._show()

    def _schedule_show(self):
        self.root.after(0, self._show)

    def _show(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.lift()
            self.window.focus_force()
            return
        self.window = MailWindow(self.root)
        self.window.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self):
        if self.window is not None:
            self.window.destroy()
            self.window = None

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    App().run()
