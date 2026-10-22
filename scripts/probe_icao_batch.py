#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量核验 ICAO PDF：真实文档号、卷次、版次、修订号、页数、是否加密。

纪律：不信文件名，只信 PDF 内页（封面 supersedes 句 + 版权页版次沿革 + 修订记录页）。
输出：data/inbox/icao_batch/probe.json
"""
import json, os, re, sys
from pathlib import Path

# 待核验的 PDF 放在本机的下载目录里；换机器时用环境变量指向自己的路径。
DIR = os.environ.get("ICAO_PDF_DIR", str(Path.home() / "Downloads"))
OUT = "data/inbox/icao_batch"

FILES = [
 "icao_annex_10_aeronauticaltelecommunicationsvolumeiv-surveillanc.pdf",
 "AN10_V5_cons.pdf",
 "ammendment_2_annex_19.pdf",
 "an10v1.pdf",
 "ICAO doc 8126 Aeronautical Information Services Manual  .pdf",
 "icao_doc_8168_aircraftoperations.pdf",
 "4444_cons_en.pdf",
 "icao_doc8168_volume_2.pdf",
 "icao_doc_8168_aircraft_operations_volume_iii.pdf",
 "10066_cons_en.pdf",
 "icao_annex_16_environmentalprotectionvolumeiv-corsia.pdf",
 "icao_annex_16_environmentalprotectionvolumei-aircraftnoise.pdf",
 "AN14_V2_cons_en.pdf",
 "icao_annex_18_thesafetransportofdangerousgoodsbyair.pdf",
 "icao_annex_17_security.pdf",
 "icao_annex_16_environmentalprotectionvolumeiii_co2.pdf",
 "icao_annex_16_environmentalprotectionvolumeii-aircraftengineemis.pdf",
 "an15_cons.pdf",
 "[722611283] an14_v1_cons corr3.pdf",
 "icao_annex_1_personnellicensing.pdf",
 "icao_annex_12_searchandrescue.pdf",
 "icao_annex_13_aircraftaccidentandincidentinvestigation.pdf",
 "differences_icaoannex14volumei-aerodromeandvolumeii-heliports.pdf",
 "ICAO_AN_16Vol03-01_EN_protected.pdf",
 "an11_cons.pdf",
 "icao_annex_2_rulesoftheair.pdf",
 "ICAO_AN_16Vol01-08_EN_protected.pdf",
 "an03_cons.pdf",
 "ICAO_AN_19-2_EN_protected.pdf",
 "ICAO_AN_18-04_EN_protected.pdf",
 "ICAO_AN_17-12_EN_protected.pdf",
 "ICAO_AN_16Vol04-02_EN_protected.pdf",
 "ICAO_AN_14Vol02-5_EN_protected.pdf",
 "ICAO_AN_16Vol03-01_EN_protected.Amdt-2.pdf",
 "ICAO_AN_16Vol02-05_EN_protected.pdf",
 "ICAO_AN_16Vol01-08_EN_protected.Amdt-14.pdf",
 "ICAO_AN_14Vol01-9_EN_protected.pdf",
 "ICAO_AN_15-16_EN_protected.Amdt-43.pdf",
 "ICAO_AN_15-16_EN_protected.pdf",
 "ICAO_AN_13-13_EN_protected.pdf",
 "ICAO_AN_12-09_EN_protected.pdf",
 "ICAO_AN_11-15_EN_protected.Amdt-53.pdf",
 "ICAO_AN_11-15_EN_protected.pdf",
 "ICAO_AN_10Vol06-01_EN_protected.pdf",
 "ICAO_AN_10Vol05-03_EN_protected.Amdt-90.pdf",
 "ICAO_AN_10Vol02-07_EN_protected.pdf",
 "ICAO_AN_10Vol01-08_EN_protected.pdf",
 "ICAO_AN_10Vol04-05_EN_protected.pdf",
 "ICAO_AN_10Vol03-02_EN_protected.pdf",
 "ICAO_AN_10Vol03-02_EN_protected.Amdt-92.pdf",
]


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def probe(path):
    import pypdf
    rec = {"file": os.path.basename(path)}
    try:
        rec["sizeMB"] = round(os.path.getsize(path) / 1048576, 1)
    except OSError as e:
        rec["error"] = f"no file: {e}"
        return rec
    try:
        r = pypdf.PdfReader(path)
    except Exception as e:
        rec["error"] = f"open fail: {type(e).__name__}: {e}"
        return rec
    rec["encrypted"] = bool(r.is_encrypted)
    txt, n = "", 0
    try:
        rec["pages"] = len(r.pages)
        n = len(r.pages)
    except Exception as e:
        rec["error"] = f"page fail: {e}"
        return rec
    # 加密文件尝试空密码解锁
    if r.is_encrypted:
        try:
            r.decrypt("")
            rec["decrypted_empty_pw"] = True
        except Exception:
            rec["decrypted_empty_pw"] = False
    got = 0
    for i in range(min(10, n)):
        try:
            t = r.pages[i].extract_text() or ""
        except Exception:
            t = ""
        if t.strip():
            got += 1
        txt += t + "\n"
    rec["textPages"] = got
    rec["head"] = norm(txt)[:700]
    # 版次与文档号
    ed = re.search(r"([A-Za-z]+)\s*Edition[,]?\s*((?:19|20)\d{2})", txt)
    doc = re.search(r"Doc(?:ument)?\s*\.?\s*(\d{3,5})", txt)
    order = re.search(r"Order Number[:\s]*([A-Z0-9\-\s/]{3,20})", txt)
    isbn = re.search(r"ISBN\s*([0-9\-]{10,20})", txt)
    sup = re.search(r"supersedes?,?\s*(?:on\s*)?([0-9]{1,2}\s+\w+\s+(?:19|20)\d{2})", txt)
    rec["edition"] = ed.group(0) if ed else ""
    rec["docNo"] = doc.group(1) if doc else ""
    rec["orderNo"] = norm(order.group(1)) if order else ""
    rec["isbn"] = isbn.group(1) if isbn else ""
    rec["supersedes"] = sup.group(1) if sup else ""
    return rec


def main():
    os.makedirs(OUT, exist_ok=True)
    res = []
    for i, f in enumerate(FILES, 1):
        p = os.path.join(DIR, f)
        rec = probe(p)
        res.append(rec)
        flag = "ENC" if rec.get("encrypted") else "   "
        print(f"{i:2}. {flag} {rec.get('pages','?'):>5}p {rec.get('sizeMB','?'):>6}MB | "
              f"{rec.get('edition','')[:26]:26} | {f[:58]}")
        if rec.get("error"):
            print("      !!", rec["error"])
    json.dump(res, open(f"{OUT}/probe.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n完成 {len(res)} 份 → {OUT}/probe.json")


if __name__ == "__main__":
    main()
