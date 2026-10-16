BOT_NAME = "node4demo"
SPIDER_MODULES = ["node4demo.spiders"]
NEWSPIDER_MODULE = "node4demo.spiders"

# Runs before Scrapy's own HttpProxyMiddleware (priority 750), which applies the credentials.
DOWNLOADER_MIDDLEWARES = {
    "node4demo.middlewares.Node4ProxyMiddleware": 350,
}

# Keep total concurrency at or below your plan's limit: the free tier allows 10
# concurrent connections, Rotating Unmetered your plan's connection count.
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 8

# Retry refusals. Without a session each retry opens a new tunnel, so it can leave
# from a different exit (see middlewares.py).
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [403, 429, 500, 502, 503, 504]

ROBOTSTXT_OBEY = True
DOWNLOAD_TIMEOUT = 30
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
LOG_LEVEL = "INFO"
