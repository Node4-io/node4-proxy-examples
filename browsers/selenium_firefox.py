"""Selenium + Firefox through Node4, using the local forwarder for the credentials.

Firefox reads its proxy from preferences, which have no username or password field.
Pointing those preferences straight at an authenticated proxy makes Firefox show a
login prompt, and under Selenium that prompt blocks the session from starting. The
local forwarder (local-forwarder/) needs no login and adds the credentials upstream.

    pip install selenium      # Selenium Manager fetches geckodriver
    python selenium_firefox.py
"""
import json
import sys
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By

from _env import GATEWAY, IP_URL, PASS, USER, check_credentials, new_session_id

sys.path.insert(0, str(Path(__file__).parent / "local-forwarder"))
from node4_forwarder import Forwarder  # noqa: E402

check_credentials()
session = new_session_id()
forwarder = Forwarder(USER, PASS, upstream=GATEWAY, session=session)
port = forwarder.start()

options = webdriver.FirefoxOptions()
options.add_argument("-headless")
options.set_preference("network.proxy.type", 1)  # manual proxy configuration
for scheme in ("http", "ssl"):                   # ssl = HTTPS, sent as CONNECT
    options.set_preference(f"network.proxy.{scheme}", "127.0.0.1")
    options.set_preference(f"network.proxy.{scheme}_port", port)
options.set_preference("devtools.jsonview.enabled", False)  # show JSON as plain text

driver = webdriver.Firefox(options=options)
try:
    driver.get(IP_URL)
    ip = json.loads(driver.find_element(By.TAG_NAME, "body").text)["ip"]
    print(f"firefox (session {session}): {ip}")
finally:
    driver.quit()
    forwarder.stop()
