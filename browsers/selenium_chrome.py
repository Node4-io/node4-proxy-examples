"""Selenium + Chrome through Node4, using the local forwarder for the credentials.

Chrome's --proxy-server flag takes host:port only, with no username or password, and
Selenium has no reliable way to answer the proxy's 407 in current Chrome (see the
README). So each browser points at a local forwarder (local-forwarder/) that adds the
credentials on the way to Node4. One forwarder per browser, each with its own sticky
session, gives each browser its own exit IP.

    pip install selenium      # Selenium Manager fetches the matching chromedriver
    python selenium_chrome.py
"""
import json
import sys
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By

from _env import GATEWAY, IP_URL, PASS, USER, check_credentials, new_session_id

sys.path.insert(0, str(Path(__file__).parent / "local-forwarder"))
from node4_forwarder import Forwarder  # noqa: E402

BROWSERS = 2


def exit_ip(driver) -> str:
    driver.get(IP_URL)
    return json.loads(driver.find_element(By.TAG_NAME, "body").text)["ip"]


check_credentials()  # Chrome reports a rejected password as a generic tunnel error
for n in range(1, BROWSERS + 1):
    session = new_session_id()
    forwarder = Forwarder(USER, PASS, upstream=GATEWAY, session=session)
    port = forwarder.start()  # 127.0.0.1:<port>, no auth, background thread

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument(f"--proxy-server=http://127.0.0.1:{port}")
    driver = webdriver.Chrome(options=options)
    try:
        print(f"browser {n} (session {session}): {exit_ip(driver)}, reload {exit_ip(driver)}")
    finally:
        driver.quit()
        forwarder.stop()
