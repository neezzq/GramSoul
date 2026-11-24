#!/usr/bin/env python3
"""Two-phone end-to-end test on two Android emulators (black box, via adb + uiautomator).

    python3 tools/emulator_e2e.py --apk app.apk --a emulator-5554 --b emulator-5556 --out screens/

Both emulators get a clean install of the same APK. Phone A and phone B register
their own nicknames, find each other by nickname, accept the request, start the
demo story together and play with the live model. Screenshots go to --out.
The Compose test tags are exposed as resource-ids (testTagsAsResourceId)."""
from __future__ import annotations

import argparse
import os
import random
import re
import string
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

PKG = None
OUT = "screens"
RESULTS: list[tuple[str, bool, str]] = []
DEMO = "Маяк на Стеклянном берегу"


def sh(*args, check=True, timeout=120) -> str:
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} -> {r.returncode}: {r.stderr[:500]}")
    return r.stdout


def adb(dev, *args, **kw) -> str:
    return sh("adb", "-s", dev, *args, **kw)


def ok(name, cond, info=""):
    RESULTS.append((name, bool(cond), info))
    print(("OK   " if cond else "FAIL ") + name + (f" — {info}" if info else ""), flush=True)
    return cond


class Node:
    def __init__(self, el):
        self.rid = el.get("resource-id", "")
        self.text = el.get("text", "")
        self.desc = el.get("content-desc", "")
        self.enabled = el.get("enabled") == "true"
        m = re.findall(r"\d+", el.get("bounds", "[0,0][0,0]"))
        x1, y1, x2, y2 = map(int, m)
        self.cx, self.cy = (x1 + x2) // 2, (y1 + y2) // 2
        self.y1, self.y2 = y1, y2
        self.pkg = el.get("package", "")


def dump_root(dev):
    for _ in range(5):
        out = adb(dev, "exec-out", "uiautomator", "dump", "/dev/tty", check=False, timeout=60)
        xml = out[out.find("<?xml"): out.rfind(">") + 1] if "<?xml" in out else ""
        if xml:
            try:
                return ET.fromstring(xml)
            except ET.ParseError:
                pass
        time.sleep(1)
    return None


def dump(dev) -> list[Node]:
    root = dump_root(dev)
    return [Node(e) for e in root.iter("node")] if root is not None else []


def chat_texts(dev) -> list[str]:
    """Texts of the visible chat messages only (not buttons / input)."""
    root = dump_root(dev)
    if root is None:
        return []
    for e in root.iter("node"):
        if e.get("resource-id") == "chat_list":
            return [n.get("text") for n in e.iter("node") if n.get("text")]
    return []


def all_text(nodes) -> str:
    return "\n".join(n.text for n in nodes if n.text)


def find(nodes, rid=None, text=None):
    for n in nodes:
        if rid is not None and n.rid != rid:
            continue
        if text is not None and text not in n.text and text not in n.desc:
            continue
        return n
    return None


def dismiss_system_dialogs(dev, nodes) -> bool:
    """Close "System UI isn't responding" / ANR dialogs that slow CI emulators show."""
    for n in nodes:
        if n.rid in ("android:id/aerr_wait", "android:id/aerr_close") or n.text in ("Wait", "Подождать"):
            tap(dev, n)
            return True
    return False


def ensure_app(dev, nodes) -> None:
    if nodes and not any(n.pkg == PKG for n in nodes):
        if not dismiss_system_dialogs(dev, nodes):
            launch(dev)


def wait(dev, rid=None, text=None, timeout=60, name=None):
    end = time.time() + timeout
    last_fix = time.time()
    while time.time() < end:
        nodes = dump(dev)
        n = find(nodes, rid, text)
        if n:
            return n
        if time.time() - last_fix > 12:
            ensure_app(dev, nodes)
            last_fix = time.time()
        time.sleep(1)
    shot(dev, f"timeout_{name or rid or 'text'}")
    raise TimeoutError(f"{dev}: waited for rid={rid} text={text}")


def wait_cond(dev, cond, timeout=600, label="cond"):
    end = time.time() + timeout
    while time.time() < end:
        nodes = dump(dev)
        if cond(nodes):
            return nodes
        time.sleep(2)
    shot(dev, f"timeout_{label}")
    raise TimeoutError(f"{dev}: {label}")


def tap(dev, node):
    adb(dev, "shell", "input", "tap", str(node.cx), str(node.cy))
    time.sleep(0.6)


def tap_id(dev, rid, timeout=60):
    tap(dev, wait(dev, rid=rid, timeout=timeout))


def type_text(dev, text):
    # adb "input text" is ASCII only; spaces become %s
    safe = text.replace("%", "").replace(" ", "%s")
    adb(dev, "shell", "input", "text", "'" + safe.replace("'", "") + "'")
    time.sleep(0.5)


def clear_field(dev):
    # select all + delete (works for multi-line fields too)
    adb(dev, "shell", "input", "keycombination", "KEYCODE_CTRL_LEFT", "KEYCODE_A", check=False)
    adb(dev, "shell", "input", "keyevent", "KEYCODE_DEL")
    adb(dev, "shell", "input", "keyevent", "KEYCODE_MOVE_END")
    adb(dev, "shell", "input", "keyevent", *(["67"] * 30))


def keyboard_shown(dev) -> bool:
    out = adb(dev, "shell", "dumpsys", "input_method", check=False)
    return "mInputShown=true" in out or "isInputViewShown=true" in out


def hide_keyboard(dev):
    if keyboard_shown(dev):
        adb(dev, "shell", "input", "keyevent", "4")  # BACK closes the IME only
        time.sleep(0.6)


def shot(dev, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{name}_{dev.replace('emulator-', 'e')}.png")
    with open(path, "wb") as f:
        f.write(subprocess.run(["adb", "-s", dev, "exec-out", "screencap", "-p"], capture_output=True).stdout)
    return path


def launch(dev):
    adb(dev, "shell", "am", "start", "-W", "-n", f"{PKG}/app.fonar.MainActivity", check=False, timeout=120)
    time.sleep(2)


def narrator_texts(nodes):
    # narrator blocks contain the label + text; read all texts after a РАССКАЗЧИК label
    texts = [n.text for n in nodes if n.text]
    out = []
    for i, t in enumerate(texts):
        if t == "РАССКАЗЧИК" and i + 1 < len(texts):
            out.append(texts[i + 1])
    return out


def last_ai_signature(dev):
    nodes = dump(dev)
    return tuple(n.text for n in nodes if n.text)[-12:]


def scroll_up(dev):
    adb(dev, "shell", "input", "swipe", "540", "700", "540", "1500", "300")
    time.sleep(0.8)


def generation_idle(nodes):
    return not find(nodes, rid="generation_status") and not find(nodes, rid="generation_running")


def main():
    global PKG, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", required=True)
    ap.add_argument("--pkg", default="app.fonar.e2e")
    ap.add_argument("--a", default="emulator-5554")
    ap.add_argument("--b", default="emulator-5556")
    ap.add_argument("--out", default="screens")
    ap.add_argument("--gen-timeout", type=int, default=600)
    args = ap.parse_args()
    PKG, OUT = args.pkg, args.out
    A, B = args.a, args.b
    GT = args.gen_timeout
    sfx = "".join(random.choice(string.digits) for _ in range(4))
    nick_a, nick_b = f"Mira{sfx}", f"Lev{sfx}"

    for d in (A, B):
        adb(d, "uninstall", PKG, check=False)
        adb(d, "install", "-r", args.apk, timeout=300)
        for k in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
            adb(d, "shell", "settings", "put", "global", k, "0")
        adb(d, "shell", "input", "keyevent", "82", check=False)  # unlock
        dismiss_system_dialogs(d, dump(d))
        launch(d)

    # 1. registration on two clean installs
    tap_id(A, "nick_input")
    type_text(A, nick_a)
    hide_keyboard(A)
    shot(A, "01_register")
    tap_id(A, "start_button")
    wait(A, rid="my_nick", timeout=60)
    ok("A registered by nick only", True, nick_a)

    tap_id(B, "nick_input")
    type_text(B, nick_a.lower())  # someone else's nick, other case
    hide_keyboard(B)
    tap_id(B, "start_button")
    n = wait(B, text="уже занят", timeout=30)
    shot(B, "02_register_taken")
    ok("B: taken nick refused (no access to A's account)", n is not None)
    tap_id(B, "nick_input")
    clear_field(B)
    type_text(B, nick_b)
    hide_keyboard(B)
    tap_id(B, "start_button")
    wait(B, rid="my_nick", timeout=60)
    ok("B registered by nick only", True, nick_b)
    shot(B, "03_home")

    # 2. A finds B by nickname and sends a request
    tap_id(A, "tab_friends")
    tap_id(A, "friend_search_input")
    type_text(A, nick_b.upper())
    tap_id(A, "friend_search_button")
    hide_keyboard(A)
    tap_id(A, "add_friend")
    wait(A, rid="request_sent", timeout=30)
    shot(A, "04_request_sent")
    ok("A found B by full nick and sent a request", True)

    # 3. B accepts
    tap_id(B, "tab_friends")
    wait(B, rid=f"incoming_{nick_a}", timeout=60)
    shot(B, "05_incoming")
    tap_id(B, f"accept_{nick_a}")
    wait(B, rid=f"friend_{nick_a}", timeout=30)
    wait(A, text="принята", timeout=60)
    ok("request accepted, A sees status 'принята'", True)

    # 4. A: «Играть с другом» on the demo story
    tap_id(A, "tab_stories")
    tap_id(A, f"play_friend_{DEMO}")
    tap_id(A, f"pick_{nick_b}")
    tap_id(A, "invite_confirm")
    wait(A, rid="chat_input", timeout=60)
    shot(A, "06_chat_waiting")

    tap_id(B, "tab_scenes")
    wait(B, rid="invite_card", timeout=60)
    shot(B, "07_invite")
    tap_id(B, "invite_accept")
    wait(B, rid="chat_input", timeout=60)
    wait(A, text=f"— {nick_b}", timeout=60)
    ok("B accepted the game invite; both in one scene", True)

    # 5. A acts; both get the same live reaction
    before_a = len(narrator_texts(dump(A)))
    tap_id(A, "chat_input")
    type_text(A, "*sits down next to Iva and takes her hand* Why so quiet?")
    shot(A, "08_keyboard_open")
    tap_id(A, "send_button")
    hide_keyboard(A)
    t0 = time.time()
    na = wait_cond(A, lambda ns: generation_idle(ns) and len(narrator_texts(ns)) + len([x for x in ns if x.rid == "msg_character"]) > 0
                   and find(ns, text="takes her hand") is not None and find(ns, rid="regenerate_button") is not None
                   and find(ns, rid="regenerate_button").enabled, GT, "reaction_A")
    dt = time.time() - t0
    shot(A, "09_reaction")
    nb = wait_cond(B, lambda ns: find(ns, text="takes her hand") is not None and generation_idle(ns), GT, "reaction_B")
    shot(B, "09_reaction")
    tail_a = chat_texts(A)[-2:]
    tail_b = chat_texts(B)[-2:]
    ok("live model reaction arrived", True, f"{dt:.0f} s")
    ok("both phones show the same reaction", tail_a == tail_b and len(tail_a) == 2, f"{tail_a} | {tail_b}")

    # 6. A edits Iva's card from the chat and returns to the scene
    for _ in range(12):
        if find(dump(A), rid="name_Ива"):
            break
        scroll_up(A)
    tap_id(A, "name_Ива")
    tap_id(A, "char_personality")
    clear_field(A)
    marker = f"Bold and mocking {sfx}"
    type_text(A, marker)
    hide_keyboard(A)
    shot(A, "10_card_edit")
    tap_id(A, "card_save")
    wait(A, rid="chat_input", timeout=30)
    ok("card edited from the chat, back in the scene", True)
    tap_id(A, "chat_input")
    type_text(A, "Iva, are you alright?")
    tap_id(A, "send_button")
    hide_keyboard(A)
    wait_cond(A, lambda ns: find(ns, text="are you alright") is not None and generation_idle(ns)
              and find(ns, rid="regenerate_button") is not None and find(ns, rid="regenerate_button").enabled, GT, "reaction2")
    tap_id(A, "chat_menu")
    tap_id(A, "menu_prompt")
    pn = wait(A, rid="prompt_text", timeout=30)
    full = all_text(dump(A))
    shot(A, "11_prompt")
    ok("next model request contains the saved edit", marker in full)
    adb(A, "shell", "input", "keyevent", "4")
    time.sleep(1)

    # 7. regenerate on B: the last reaction is replaced on both phones
    sig_before = chat_texts(B)[-3:]
    tap_id(B, "regenerate_button")
    time.sleep(3)
    end = time.time() + GT
    while time.time() < end:
        ns = dump(B)
        if generation_idle(ns) and chat_texts(B)[-3:] != sig_before:
            break
        time.sleep(2)
    time.sleep(4)
    ra = chat_texts(A)[-2:]
    rb = chat_texts(B)[-2:]
    shot(B, "12_regenerated")
    ok("regenerated reaction is the same on both phones", ra == rb, f"{ra} | {rb}")

    # 8. B restarts the app: automatic login, scene still there
    adb(B, "shell", "am", "force-stop", PKG)
    launch(B)
    wait(B, rid="my_nick", timeout=30)
    tap_id(B, "tab_scenes")
    tap_id(B, f"room_{DEMO}")
    wait(B, rid="chat_input", timeout=30)
    ok("B relaunched: signed in automatically", True)

    # 9. B loses the network; A plays on; B reconnects and catches up
    adb(B, "shell", "svc", "wifi", "disable", check=False)
    adb(B, "shell", "svc", "data", "disable", check=False)
    tap_id(A, "chat_input")
    type_text(A, "*lifts the lantern* Lets go to the lens.")
    tap_id(A, "send_button")
    hide_keyboard(A)
    try:
        wait(B, rid="offline_banner", timeout=90)
        shot(B, "13_offline")
        ok("B shows the offline banner", True)
    except TimeoutError:
        ok("B shows the offline banner", False)
    wait_cond(A, lambda ns: find(ns, text="lifts the lantern") is not None and generation_idle(ns), GT, "reaction3")
    adb(B, "shell", "svc", "wifi", "enable", check=False)
    adb(B, "shell", "svc", "data", "enable", check=False)
    wait_cond(B, lambda ns: find(ns, text="lifts the lantern") is not None and find(ns, rid="offline_banner") is None, 180, "catchup")
    time.sleep(4)
    ra = chat_texts(A)[-2:]
    rb = chat_texts(B)[-2:]
    shot(B, "14_caught_up")
    ok("after reconnect B received the missed messages", ra == rb, f"{ra} | {rb}")

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} emulator checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR:", e)
        for d in ("emulator-5554", "emulator-5556"):
            try:
                shot(d, "error")
            except Exception:
                pass
        sys.exit(2)
