"""Goku PC agent. Runs on every club PC (Windows). Python 3, standard library only.
Every 4 seconds: heartbeat + fetch commands (shutdown / restart / lock) from the cloud."""
import json, os, subprocess, sys, time, urllib.request, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "agent_config.json"), encoding="utf-8"))
URL = CFG["url"].rstrip("/") + "/rest/v1/rpc/"
KEY = CFG["key"]


def rpc(name, body):
    req = urllib.request.Request(
        URL + name, data=json.dumps(body).encode(), method="POST",
        headers={"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else None


def mac():
    n = uuid.getnode()
    return ":".join("%02X" % ((n >> s) & 0xFF) for s in range(40, -1, -8))


def run(action):
    if action == "shutdown":
        subprocess.Popen(["shutdown", "/s", "/t", "10", "/c", "Goku: session ended"])
    elif action == "restart":
        subprocess.Popen(["shutdown", "/r", "/t", "10"])
    elif action == "lock":
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
    else:
        return False
    return True


def main():
    pc, secret = CFG["pc_id"], CFG["secret"]
    last_hello = 0
    while True:
        try:
            if time.time() - last_hello > 600:  # tell the cloud this PC's MAC (needed for Wake-on-LAN)
                rpc("agent_hello", {"p_pc": pc, "p_secret": secret, "p_mac": mac()})
                last_hello = time.time()
            for c in rpc("agent_poll", {"p_pc": pc, "p_secret": secret}) or []:
                ok = run(c["action"])
                rpc("agent_ack", {"p_pc": pc, "p_secret": secret, "p_cmd": c["cmd_id"], "p_ok": ok})
        except Exception as e:
            print("error:", e, file=sys.stderr)
        time.sleep(4)


if __name__ == "__main__":
    main()
