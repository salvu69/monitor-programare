"""
Monitor programare.primariasector1.ro
Verifică dacă există sloturi disponibile pentru serviciul 54
(Transcrieri Certificate Procurate din Străinătate - Procură Specială)
"""

import json
import os
import smtplib
import requests
from datetime import datetime
from email.message import EmailMessage

CONFIG_FILE = "config.json"
STATE_FILE  = "state_programare.json"

SERVICE_ID  = 54
SERVICE_URL = f"https://programare.primariasector1.ro/api/online/{SERVICE_ID}"
BASE_URL    = "https://programare.primariasector1.ro"
CSRF_URL    = f"{BASE_URL}/api/csrf-cookie"
INIT_URL    = f"{BASE_URL}/api/online/init"

CNP_FAKE    = "1234567890123"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
    "Referer": BASE_URL + "/",
    "Origin": BASE_URL,
}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_sloturi():
    session = requests.Session()
    session.headers.update(HEADERS)

    # Pas 1: csrf-cookie
    try:
        r = session.get(CSRF_URL, timeout=20)
        r.raise_for_status()
        xsrf = session.cookies.get("XSRF-TOKEN", "")
        if xsrf:
            session.headers["X-XSRF-TOKEN"] = requests.utils.unquote(xsrf)
    except Exception as e:
        print(f"[WARN] csrf-cookie: {e}")

    # Pas 2: init
    try:
        r = session.get(INIT_URL, timeout=20, params={"cnp": CNP_FAKE})
        r.raise_for_status()
    except Exception as e:
        print(f"[WARN] init: {e}")

    # Pas 3: zilele disponibile
    r = session.get(SERVICE_URL, timeout=20)
    r.raise_for_status()

    data = r.json()
    print(f"[DEBUG] Răspuns API: {json.dumps(data, ensure_ascii=False)[:500]}")
    return data


def parse_sloturi(data):
    """
    Extrage doar datele cu is_available=True din răspunsul API.
    Returnează lista de stringuri de forma "7 iunie (luni)".
    """
    if not data:
        return []

    sloturi = []

    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            if not item.get("is_available", False):
                continue
            data_localizata = item.get("date_localized", item.get("date", ""))
            zi_localizata   = item.get("day_localized", "")
            if zi_localizata:
                sloturi.append(f"{data_localizata} ({zi_localizata})")
            else:
                sloturi.append(data_localizata)
        return sloturi

    if isinstance(data, dict):
        for key in ("zile", "date", "days", "sloturi", "disponibile", "items", "results"):
            val = data.get(key)
            if val and isinstance(val, list):
                return parse_sloturi(val)

    return []


def send_email(config, subject, plain_body, html_body):
    msg = EmailMessage()
    msg["From"]    = config["sender_email"]
    msg["To"]      = config["recipient_email"]
    msg["Subject"] = subject
    msg.set_content(plain_body)
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP_SSL(config["smtp_host"], int(config["smtp_port"])) as server:
        server.login(config["sender_email"], config["sender_app_password"])
        server.send_message(msg)


def build_email(sloturi_noi, toate_sloturile, now_str):
    lista_noi  = "\n".join(f"  • {s}" for s in sloturi_noi) or "  (sloturi noi detectate)"
    lista_toate = "\n".join(f"  • {s}" for s in toate_sloturile) or "  (vezi site-ul)"

    plain = f"""Sloturi noi disponibile pentru programare la Primăria Sector 1!

Serviciu: Transcrieri Certificate Procurate din Străinătate
          (persoane împuternicite cu Procură Specială)
Locație: Strada Piața Amzei, 13

Sloturi NOI:
{lista_noi}

Toate sloturile disponibile:
{lista_toate}

Intră acum: https://programare.primariasector1.ro/
Detectat la: {now_str}
"""

    li_noi   = "".join(f"<li>{s}</li>" for s in sloturi_noi) or "<li>Sloturi noi detectate</li>"
    li_toate = "".join(f"<li>{s}</li>" for s in toate_sloturile) or "<li>Vezi site-ul</li>"

    html = f"""<!doctype html>
<html>
<head><meta charset="utf-8"/></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <div style="background:#2563eb;color:white;padding:16px;border-radius:10px 10px 0 0;text-align:center;">
    <h2 style="margin:0;">🔔 Sloturi noi disponibile!</h2>
  </div>
  <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 10px 10px;">
    <p><strong>Serviciu:</strong> Transcrieri Certificate Procurate din Străinătate<br>
       <strong>Locație:</strong> Strada Piața Amzei, 13</p>

    <h3 style="color:#16a34a;">✅ Sloturi NOI:</h3>
    <ul>{li_noi}</ul>

    <h3>Toate sloturile disponibile:</h3>
    <ul>{li_toate}</ul>

    <div style="text-align:center;margin-top:24px;">
      <a href="https://programare.primariasector1.ro/"
         style="background:#2563eb;color:white;padding:14px 28px;
                text-decoration:none;border-radius:8px;font-size:16px;font-weight:bold;">
        Fă programarea acum →
      </a>
    </div>
    <p style="color:#9ca3af;font-size:12px;margin-top:20px;">Detectat la: {now_str}</p>
  </div>
</body>
</html>"""

    return plain, html


def main():
    now     = datetime.now()
    now_str = now.strftime("%d.%m.%Y %H:%M")

    config = load_json(CONFIG_FILE, None)
    if not config:
        print("Lipsește config.json")
        return

    state = load_json(STATE_FILE, {"sloturi": []})
    sloturi_anterioare = set(state.get("sloturi", []))

    try:
        data = get_sloturi()
    except Exception as e:
        print(f"[EROARE] Nu pot accesa site-ul: {e}")
        return

    sloturi_curente = parse_sloturi(data)
    print(f"[INFO] Sloturi disponibile găsite: {len(sloturi_curente)}")
    for s in sloturi_curente:
        print(f"  • {s}")

    if not sloturi_curente:
        print("[INFO] Niciun slot disponibil momentan.")
        save_json(STATE_FILE, {"sloturi": [], "ultima_verificare": now_str})
        return

    sloturi_set = set(sloturi_curente)
    sloturi_noi = list(sloturi_set - sloturi_anterioare)

    if sloturi_noi or (sloturi_curente and not sloturi_anterioare):
        notif_sloturi = sloturi_noi if sloturi_noi else sloturi_curente
        print(f"[INFO] Sloturi noi detectate: {notif_sloturi}")
        plain, html = build_email(notif_sloturi, sloturi_curente, now_str)
        subject = f"🔔 Sloturi noi programare Sector 1 – {now_str}"
        try:
            send_email(config, subject, plain, html)
            print("[INFO] Email trimis cu succes!")
        except Exception as e:
            print(f"[EROARE] Email: {e}")
    else:
        print("[INFO] Nicio schimbare față de ultima verificare.")

    save_json(STATE_FILE, {
        "sloturi": sloturi_curente,
        "ultima_verificare": now_str
    })


if __name__ == "__main__":
    main()
