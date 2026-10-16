"""Selenium + Chrome for Testing: credentials from a tiny extension, no extra process.

Use this when the browser runs somewhere a local forwarder is awkward, such as a
Selenium Grid node. The script writes a two-file MV3 extension to a temporary folder;
it answers the proxy's 407 with your username and password.

Needs Chrome for Testing or Chromium. Branded Google Chrome 137 and later ignores
--load-extension, so the extension never loads and pages fail to open.

    npx @puppeteer/browsers install chrome@stable      # downloads Chrome for Testing
    export CHROME_BINARY=/path/to/chrome-for-testing/chrome
    python selenium_chrome_extension.py
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By

from _env import GATEWAY, IP_URL, PASS, check_credentials, new_session_id, session_user

BINARY = os.environ.get("CHROME_BINARY", "")
if not BINARY:
    sys.exit("Set CHROME_BINARY to a Chrome for Testing or Chromium executable (see the docstring).")

MANIFEST = {
    "manifest_version": 3,
    "name": "Node4 proxy login",
    "version": "1.0",
    "permissions": ["webRequest", "webRequestAuthProvider"],
    "host_permissions": ["<all_urls>"],
    "background": {"service_worker": "background.js"},
}
BACKGROUND = """
chrome.webRequest.onAuthRequired.addListener(
  (details, callback) => callback(details.isProxy ? { authCredentials: CREDENTIALS } : {}),
  { urls: ["<all_urls>"] },
  ["asyncBlocking"]
);
"""


def write_extension(username: str, password: str) -> Path:
    folder = Path(tempfile.mkdtemp(prefix="node4-auth-"))
    (folder / "manifest.json").write_text(json.dumps(MANIFEST))
    creds = json.dumps({"username": username, "password": password})
    (folder / "background.js").write_text(f"const CREDENTIALS = {creds};\n{BACKGROUND}")
    return folder


check_credentials()
session = new_session_id()
extension = write_extension(session_user(session), PASS)  # contains the password: deleted below

options = webdriver.ChromeOptions()
options.binary_location = BINARY
options.add_argument("--headless=new")
options.add_argument(f"--proxy-server=http://{GATEWAY}")
options.add_argument(f"--load-extension={extension}")
driver = webdriver.Chrome(options=options)
try:
    for _ in range(2):
        driver.get(IP_URL)
        ip = json.loads(driver.find_element(By.TAG_NAME, "body").text)["ip"]
        print(f"chrome {driver.capabilities['browserVersion']} (session {session}): {ip}")
finally:
    driver.quit()
    shutil.rmtree(extension, ignore_errors=True)
