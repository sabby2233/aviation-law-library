"""下载 ET 给出的官方文书，抽取决定日期与最终金额，与库内值比对。

只下载、只抽元数据（日期、金额、决定编号），不转存全文——
官方文书全文仍以原站为准，本库只留定位符与抽取值。
"""

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\qwesz\WorkBuddy\2026-10-20-22-03-33\aviation-law-library")
VDIR = ROOT / "data" / "verify" / "official"
VDIR.mkdir(parents=True, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

TARGETS = [
    ("AVA-ES-ADP-A-001", "ETid-86", "https://www.aepd.es/resoluciones/PS-00300-2019_ORI.pdf", "es"),
    ("AVA-ES-ADP-A-002", "ETid-196", "https://www.aepd.es/es/documento/ps-00402-2019.pdf", "es"),
    ("AVA-ES-ADP-A-009", "ETid-3192", "https://www.aepd.es/documento/ps-00005-2025.pdf", "es"),
    ("AVA-BE-ADP-A-001", "ETid-1116",
     "https://www.autoriteprotectiondonnees.be/publications/decision-quant-au-fond-n-48-2022.pdf", "fr"),
    ("AVA-CY-ADP-A-001", "ETid-181",
     "http://www.dataprotection.gov.cy/dataprotection/dataprotection.nsf/all/ACDFDC478581BEE1C22584EE0", "el"),
]

DATE_PATS = [
    r"(?:FECHA|Fecha|Date|Fecha de la resolución|DATUM)[:\s]*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
    r"(\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4})",
    r"(\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|"
    r"septembre|octobre|novembre|décembre)\s+\d{4})",
    r"(?:Madrid|Bruselas|Bruxelles)[,\s]+(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
]

AMOUNT_PATS = [
    r"(\d{1,3}(?:\.\d{3})+(?:,\d{2})?)\s*(?:euros|EUR|€)",
    r"(\d{1,3}(?:,\d{3})+)\s*(?:euros|EUR)",
    r"€\s*(\d{1,3}(?:[.,]\d{3})+)",
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), r.headers.get("Content-Type", "")


def pdf_text(b):
    import io
    import pypdf
    r = pypdf.PdfReader(io.BytesIO(b))
    return "\n".join((p.extract_text() or "") for p in r.pages), len(r.pages)


def norm_date(s):
    """抽到的日期统一成 YYYY-MM-DD。"""
    MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
              "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
              "octubre": 10, "noviembre": 11, "diciembre": 12,
              "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5,
              "juin": 6, "juillet": 7, "août": 8, "septembre": 9,
              "octobre": 10, "novembre": 11, "décembre": 12}
    s = s.strip()
    m = re.match(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        y = int(y) if len(y) == 4 else 2000 + int(y)
        return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.match(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", s, re.I)
    if m and m.group(2).lower() in MONTHS:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", s, re.I)
    if m and m.group(2).lower() in MONTHS:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return None


out = []
for rid, etid, url, lang in TARGETS:
    print(f"\n=== {rid} / {etid} ===")
    rec = {"recordId": rid, "etid": etid, "url": url}
    try:
        body, ctype = fetch(url)
        rec["httpSize"] = len(body)
        rec["contentType"] = ctype
        if "pdf" in ctype.lower() or url.lower().endswith(".pdf"):
            text, npages = pdf_text(body)
            rec["pages"] = npages
            rec["textChars"] = len(text)
            (VDIR / f"{rid}.pdf").write_bytes(body)
        else:
            text = body.decode("utf-8", errors="ignore")
            text = re.sub(r"<[^>]+>", " ", text)
            rec["textChars"] = len(text)

        dates = []
        for p in DATE_PATS:
            for m in re.finditer(p, text, re.I):
                nd = norm_date(m.group(1))
                if nd and "2000" <= nd[:4] <= "2026":
                    dates.append(nd)
        amounts = []
        for p in AMOUNT_PATS:
            for m in re.finditer(p, text):
                v = m.group(1).replace(".", "").replace(",", ".") if "," in m.group(1) else m.group(1).replace(".", "")
                try:
                    amounts.append(int(float(v)))
                except ValueError:
                    pass
        rec["datesFound"] = sorted(set(dates))[:8]
        rec["amountsFound"] = sorted(set(amounts), reverse=True)[:8]
        print(f"  HTTP OK  {rec['httpSize']}B  {rec.get('pages','?')} 页  {rec['textChars']} 字符")
        print(f"  文书日期候选：{rec['datesFound']}")
        print(f"  文书金额候选：{rec['amountsFound'][:5]}")
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {str(e)[:110]}"
        print(f"  失败：{rec['error']}")
    out.append(rec)
    time.sleep(1.5)

(ROOT / "data" / "verify" / "official_extract.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n→ data/verify/official_extract.json")
