#!/usr/bin/env python3
"""QAZGAME club generator.

Usage:  python make_club.py club.json
Reads one club description (club.json) and produces, in ./dist/<slug>/ :
  index.html, admin.html      the club's website and operator panel
  seed.sql                    club data for the database (PCs, tariffs, secrets, admin e-mail)
  agents/ + <slug>-agents.zip PC agents, lock screen, Wake-on-LAN agent with per-PC keys
"""
import json, os, re, secrets, shutil, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_TARIFF_DEFS = [["hour", "1 час", "1 сағат", 1], ["p21", "2+1", "2+1", 3], ["p32", "3+2", "3+2", 5],
                       ["morning", "Утренний 08:00–13:00", "Таңғы 08:00–13:00", 5],
                       ["day", "Дневной 13:00–19:00", "Күндізгі 13:00–19:00", 6],
                       ["night", "Ночной 22:00–08:00", "Түнгі 22:00–08:00", 10]]
DEFAULT_COLORS = {"brand": "#5DD62C", "dark": "#337418", "bg": "#0F0F0F", "card": "#202020", "text": "#F8F8F8"}


def die(msg):
    print("ERROR:", msg)
    sys.exit(1)


def rgb(h):
    h = h.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        die("color must look like #5DD62C, got %r" % h)
    return "%d,%d,%d" % tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def cap(s):
    return s[:1].upper() + s[1:]


def sql(s):
    return "'" + str(s).replace("'", "''") + "'"


def need(d, path):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur or cur[k] in ("", None):
            die("club.json: missing '%s'" % path)
        cur = cur[k]
    return cur


def flatten(prefix, v, out):
    if isinstance(v, dict):
        for k, x in v.items():
            flatten(prefix + "." + k if prefix else k, x, out)
    else:
        out[prefix] = str(v)


def js_json(o):
    return json.dumps(o, ensure_ascii=False).replace("</", "<\\/")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "club.json")
    c = json.load(open(path, encoding="utf-8"))

    for p in ["name", "logo_top", "logo_accent", "city.ru", "city.kk", "address.ru", "address.kk", "tagline.ru", "tagline.kk",
              "phone", "whatsapp", "supabase.url", "supabase.anon_key", "admin_email"]:
        need(c, p)
    if not c.get("zones"):
        die("club.json: 'zones' is empty")
    if not re.fullmatch(r"\+?\d{8,15}", c["phone"]):
        die("phone must be digits with optional +, e.g. +77075150388")
    if not re.fullmatch(r"\d{8,15}", c["whatsapp"]):
        die("whatsapp must be digits only, e.g. 77075150388")

    colors = {**DEFAULT_COLORS, **c.get("colors", {})}
    defs = c.get("tariffDefs") or DEFAULT_TARIFF_DEFS
    keys = [d[0] for d in defs]
    for z in c["zones"]:
        for p in ("id", "count"):
            if p not in z:
                die("zone without '%s'" % p)
        if not re.fullmatch(r"[a-z0-9_]+", z["id"]):
            die("zone id must be lowercase letters/digits: %r" % z["id"])
        if z["id"] not in c.get("tariffs", {}):
            die("tariffs missing for zone '%s'" % z["id"])
        t = c["tariffs"][z["id"]]
        if "hour" not in t:
            die("zone '%s' needs an 'hour' tariff (used for extending sessions)" % z["id"])
        for k in t:
            if k not in keys:
                die("zone '%s': unknown tariff key '%s' (known: %s)" % (z["id"], k, ", ".join(keys)))
        z.setdefault("specs", {})
    pc_count = sum(z["count"] for z in c["zones"])

    if c.get("open24", False):
        hs = {"ru": "Круглосуточно", "kk": "Тәулік бойы"}
        hn = {"ru": "Открыто круглосуточно", "kk": "Тәулік бойы ашық"}
        hb = "24/7"
        hours = c.get("hours") or {"ru": "Круглосуточно, 24/7", "kk": "Тәулік бойы, 24/7"}
    else:
        hours = need(c, "hours")
        hs = c.get("hours_short") or hours
        hn = c.get("hours_note") or {"ru": "Работаем " + hours["ru"], "kk": "Жұмыс уақыты: " + hours["kk"]}
        hb = c.get("hours_big") or hours["ru"]

    rating, tg = c.get("rating"), c.get("twogis")
    if rating:
        stat2 = {"value": rating["value"], "label": {"ru": "Рейтинг в 2GIS", "kk": "2GIS рейтингі"}}
        rl = {"ru": "Рейтинг %s в 2GIS · оценок: %s · отзывов: %s." % (str(rating["value"]).replace(".", ","), rating["count"], rating["reviews"]),
              "kk": "2GIS-те рейтинг %s · бағалар: %s · пікірлер: %s." % (str(rating["value"]).replace(".", ","), rating["count"], rating["reviews"])}
        reviews_n = rating["reviews"]
    else:
        stat2 = {"value": pc_count, "label": {"ru": "Компьютеров", "kk": "Компьютер"}}
        rl = {"ru": "", "kk": ""}
        reviews_n = ""
    twogis_url = "https://2gis.kz/%s/firm/%s" % (tg["city"], tg["id"]) if tg else ""
    ig = c.get("instagram", "")
    slug = re.sub(r"[^a-z0-9]+", "-", c["name"].lower()).strip("-") or "club"
    kaspi = {"link": "kaspi://", "fallback": "https://kaspi.kz/", **c.get("kaspi", {})}

    club = {"kaspi": kaspi, "whatsapp": c["whatsapp"], "supabase": {"url": c["supabase"]["url"], "anon_key": c["supabase"]["anon_key"]},
            "pcCount": pc_count, "tariffs": c["tariffs"], "school": c.get("school"), "bonus": c.get("bonus", []),
            "zones": [{"id": z["id"], "count": z["count"], "name": z["name"], "specs": z["specs"]} for z in c["zones"]],
            "reviews_url": (twogis_url + "/tab/reviews") if tg else "", "rules": c["rules"],
            "rulesNote": c.get("rulesNote", {"ru": "С уважением, администрация", "kk": "Құрметпен, әкімшілік"}), "tariffDefs": defs}

    tok = {}
    flatten("", {
        "name": c["name"], "logo_top": c["logo_top"], "logo_accent": c["logo_accent"], "city": c["city"], "address": c["address"],
        "tagline": c["tagline"], "tagline_cap": {"ru": cap(c["tagline"]["ru"]), "kk": cap(c["tagline"]["kk"])},
        "hours": hours, "hours_short": hs, "hours_note": hn, "hours_big": hb,
        "phone": c["phone"], "phone_display": c.get("phone_display", c["phone"]), "whatsapp": c["whatsapp"],
        "stat2_value": stat2["value"], "stat2_label": stat2["label"], "rating_line": rl, "reviews": reviews_n,
        "powered": " · Powered by QAZGAME" if c.get("powered_by", True) else "",
        "instagram_html": (' · <a class="g" target="_blank" rel="noopener" href="https://instagram.com/%s">@%s</a>' % (ig, ig)) if ig else "",
        "contact_title": "WhatsApp · Instagram" if ig else "WhatsApp",
        "twogis_html": ('<p><a class="g" target="_blank" rel="noopener" href="%s" data-i="k2l"></a></p>' % twogis_url) if tg else "",
        "brand": colors["brand"], "brand_rgb": rgb(colors["brand"]), "dark": colors["dark"], "dark_rgb": rgb(colors["dark"]),
        "bg": colors["bg"], "bg_rgb": rgb(colors["bg"]), "card": colors["card"], "card_rgb": rgb(colors["card"]),
        "text": colors["text"], "text_rgb": rgb(colors["text"]),
        "supabase_url": c["supabase"]["url"], "anon_key": c["supabase"]["anon_key"],
    }, tok)
    tok["CLUB_JSON"] = js_json(club)
    tok["zn_json"] = js_json({z["id"]: z["name"] for z in c["zones"]})

    def render(name):
        s = open(os.path.join(HERE, "template", name), encoding="utf-8").read()
        s = re.sub(r"\{\{([A-Za-z0-9_.]+)\}\}", lambda m: tok[m.group(1)] if m.group(1) in tok else m.group(0), s)
        left = set(re.findall(r"\{\{[^}]+\}\}", s))
        if left:
            die("unresolved tokens in %s: %s" % (name, ", ".join(sorted(left))))
        return s

    out = os.path.join(HERE, "dist", slug)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    index = render("index.template.html")
    if not tg:  # no 2GIS page: hide the reviews section and its menu link
        index = index.replace('<section id="reviews">', '<section id="reviews" hidden>').replace('<a href="#reviews" data-i="n4"></a>', "")
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(index)
    open(os.path.join(out, "admin.html"), "w", encoding="utf-8").write(render("admin.template.html"))

    # ---- seed.sql (secrets are generated here and written to BOTH the database and the agent configs)
    wol = secrets.token_hex(16)
    pcs, n = [], 0
    for z in c["zones"]:
        for _ in range(z["count"]):
            n += 1
            pcs.append((n, z["id"], secrets.token_hex(16), secrets.token_hex(16)))
    lines = ["-- QAZGAME seed for: %s. Run in the Supabase SQL editor AFTER schema.sql." % c["name"],
             "insert into public.settings(key,value) values ('wol_secret',%s),('admin_email',%s) on conflict (key) do update set value = excluded.value;" % (sql(wol), sql(c["admin_email"].lower())),
             "insert into public.pcs(id,zone,secret,lock_secret) values", ",\n".join("  (%d,%s,%s,%s)" % (i, sql(z), sql(a), sql(b)) for i, z, a, b in pcs) + ";",
             "insert into public.tariffs(zone,key,label,hours,price) values"]
    rows = []
    for z in c["zones"]:
        for d in defs:
            if d[0] in c["tariffs"][z["id"]]:
                rows.append("  (%s,%s,%s::jsonb,%d,%d)" % (sql(z["id"]), sql(d[0]), sql(json.dumps({"ru": d[1], "kk": d[2]}, ensure_ascii=False)), d[3], c["tariffs"][z["id"]][d[0]]))
    lines.append(",\n".join(rows) + ";")
    open(os.path.join(out, "seed.sql"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

    # ---- agents
    ag = os.path.join(out, "agents")
    shutil.copytree(os.path.join(HERE, "template", "agents"), ag)
    base = {"url": c["supabase"]["url"], "key": c["supabase"]["anon_key"]}
    for i, z, sec, lk in pcs:
        d = os.path.join(ag, "configs", "PC%02d" % i)
        os.makedirs(d)
        json.dump({**base, "pc_id": i, "secret": sec}, open(os.path.join(d, "agent_config.json"), "w"), indent=2)
        json.dump({**base, "pc_id": i, "lock_secret": lk, "club": c["name"], "brand": colors["brand"], "bg": colors["bg"], "text": colors["text"], "card": colors["card"]},
                  open(os.path.join(d, "lock_config.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    json.dump({**base, "secret": wol, "broadcast": "255.255.255.255"}, open(os.path.join(ag, "wol_config.json"), "w"), indent=2)
    zpath = os.path.join(out, "%s-agents.zip" % slug)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(ag):
            for f in files:
                p = os.path.join(root, f)
                zf.write(p, os.path.join("agents", os.path.relpath(p, ag)))

    warn = [w for w in ["supabase.url" if "YOUR" in c["supabase"]["url"] else "", "supabase.anon_key" if "YOUR" in c["supabase"]["anon_key"] else ""] if w]
    print("OK: %s  (%d PCs in %d zones)" % (c["name"], pc_count, len(c["zones"])))
    print("Output folder:", out)
    for f in ("index.html", "admin.html", "seed.sql", "%s-agents.zip" % slug):
        print("  -", f)
    if warn:
        print("WARNING: still placeholders in club.json ->", ", ".join(warn))
    print("\nNext: 1) run schema.sql, then seed.sql in Supabase SQL Editor  2) create the admin user (%s) in Authentication -> Users (Auto Confirm)\n"
          "      3) upload index.html + admin.html to GitHub Pages  4) install %s on the club PCs (see README.txt inside)" % (c["admin_email"], "%s-agents.zip" % slug))


if __name__ == "__main__":
    main()
