"""Fetch the exit IP several times: once rotating, once on a held session.

    scrapy crawl exit_ip
"""
import json
import secrets

import scrapy


class ExitIpSpider(scrapy.Spider):
    name = "exit_ip"

    async def start(self):
        # Scrapy 2.13+ entry point; older versions call start_requests() below.
        for request in self.start_requests():
            yield request

    def start_requests(self):
        for i in range(20):
            yield scrapy.Request(f"https://api.ipify.org?format=json&n={i}", cb_kwargs={"kind": "rotating"}, dont_filter=True)
        session = secrets.token_hex(4)
        for i in range(3):
            yield scrapy.Request(
                f"https://api.ipify.org?format=json&s={i}",
                meta={"node4_session": session},
                cb_kwargs={"kind": f"session {session}"},
                dont_filter=True,
            )

    def parse(self, response, kind):
        yield {"kind": kind, "exit_ip": json.loads(response.text)["ip"]}
