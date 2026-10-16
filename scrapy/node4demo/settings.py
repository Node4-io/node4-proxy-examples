BOT_NAME = "node4demo"
SPIDER_MODULES = ["node4demo.spiders"]
NEWSPIDER_MODULE = "node4demo.spiders"

# Runs before Scrapy's own HttpProxyMiddleware (priority 750), which applies the credentials.
DOWNLOADER_MIDDLEWARES = {
    "node4demo.middlewares.Node4ProxyMiddleware": 350,
}

# On Rotating Unmetered, keep total concurrency at or below your plan's connection count.
CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 16

# Retry refusals from a fresh request (and usually a fresh exit).
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [403, 429, 500, 502, 503, 504]

ROBOTSTXT_OBEY = True
DOWNLOAD_TIMEOUT = 30
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
LOG_LEVEL = "INFO"
