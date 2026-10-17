"""Goku Wake-on-LAN agent. Runs on ONE always-on device in the club LAN (operator PC or Raspberry Pi).
Every 2 seconds it fetches "wake" commands and sends a magic packet to the PC's MAC address."""
import json, os, socket, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "wol_config.json"), encoding="utf-8"))
URL = CFG["url"].rstrip("/") + "/rest/v1/rpc/"
KEY = CFG["key"]


def rpc(name, body):
    req = urllib.request.Request(
        URL + name, data=json.dumps(body).encode(), method="POST",
        headers={"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else None


def magic(mac):
    h = "".join(ch for ch in (mac or "") if ch in "0123456789abcdefABCDEF")
    if len(h) != 12:
        raise ValueError("no MAC for this PC yet")
    pkt = b"\xff" * 6 + bytes.fromhex(h) * 16
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    for port in (9, 7):
        s.sendto(pkt, (CFG.get("broadcast", "255.255.255.255"), port))
    s.close()


def main():
    secret = CFG["secret"]
    while True:
        try:
            for c in rpc("wol_poll", {"p_secret": secret}) or []:
                try:
                    magic(c.get("mac"))
                    ok = True
                    print("wake PC", c["pc_id"])
                except Exception as e:
                    ok = False
                    print("wake failed PC", c["pc_id"], e, file=sys.stderr)
                rpc("wol_ack", {"p_secret": secret, "p_cmd": c["cmd_id"], "p_ok": ok})
        except Exception as e:
            print("error:", e, file=sys.stderr)
        time.sleep(2)


if __name__ == "__main__":
    main()
