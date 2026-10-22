#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实浏览器验收：确认站点能渲染结果、检索可用、控制台无错误。

用法：先起静态服务（仓库根 python -m http.server 8861），再跑本脚本。
"""
import os
import sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8861/site/"
# 截图落到仓库外的同级 outputs/ 目录；可用 SCREENSHOT_PATH 覆盖
_DEFAULT_OUT = Path(__file__).resolve().parent.parent.parent / "outputs" / "site-verify.png"
OUT = os.environ.get("SCREENSHOT_PATH", str(_DEFAULT_OUT))


def main():
    errors, logs = [], []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)

        t0 = time.time()
        pg.goto(URL, wait_until="load", timeout=60000)
        print(f"goto 完成 {time.time()-t0:.2f}s")

        # 首次渲染
        try:
            pg.wait_for_selector(".record", timeout=30000)
            n0 = pg.locator(".record").count()
            print(f"[OK] 首屏渲染记录数 = {n0}")
        except Exception as e:
            n0 = 0
            print(f"[FAIL] 首屏无 .record：{type(e).__name__}")
            print("   #results 内容前 300 字:", pg.inner_text("#results")[:300] if pg.locator("#results").count() else "(无)")

        # 结果计数文案
        try:
            print("   计数文案:", pg.inner_text("#result-count")[:80])
        except Exception:
            pass

        # 检索：Annex 19
        if pg.locator("#q").count():
            pg.fill("#q", "Annex 19")
            pg.keyboard.press("Enter")
            time.sleep(1.2)
            n1 = pg.locator(".record").count()
            print(f"[检索] 'Annex 19' -> {n1} 条")

            pg.fill("#q", "适航指令")
            pg.keyboard.press("Enter")
            time.sleep(1.2)
            n2 = pg.locator(".record").count()
            print(f"[检索] '适航指令' -> {n2} 条")

            pg.fill("#q", "")
            pg.keyboard.press("Enter")
            time.sleep(0.8)

        # 点开第一条详情
        if pg.locator(".record .btn-detail").count():
            try:
                pg.locator(".record .btn-detail").first.click()
                time.sleep(1.5)
                vis = pg.locator(".record-detail").first.is_visible()
                print(f"[交互] 详情展开可见 = {vis}")
            except Exception as e:
                print(f"[交互] 详情展开失败：{e}")

        # 筛选器：法域选 CN
        try:
            pg.select_option("#f-jurisdiction", "CN")
            time.sleep(0.8)
            n3 = pg.locator(".record").count()
            print(f"[筛选] 法域=CN -> {n3} 条")
            pg.select_option("#f-jurisdiction", "")
            time.sleep(0.5)
        except Exception as e:
            print(f"[筛选] 失败：{e}")

        pg.screenshot(path=OUT, full_page=False)
        b.close()

    print("\n--- 控制台错误/警告 ---")
    if errors:
        for e in errors[:10]:
            print("  pageerror:", e[:200])
    if logs:
        for l in logs[:10]:
            print("  ", l[:200])
    if not errors and not logs:
        print("  无")
    print(f"\n截图：{OUT}")
    print("结论：", "可用" if n0 > 0 and not errors else "仍有阻断问题")


if __name__ == "__main__":
    main()
