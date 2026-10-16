// A concurrent worker pool through a Node4 gateway.
//
//	export NODE4_USER=... NODE4_PASS=...
//	go run . -workers 10 -n 40
//
// -fresh (the default) disables keep-alive so every request opens its own connection,
// and rotation is per connection, so each request can leave from a different exit.
// With -fresh=false the transport reuses tunnels and you will see far fewer exits.
package main

import (
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"
)

// fetch returns the response body and whether the request succeeded with a 200.
// A 407 (bad credentials, or a product your plan does not include) or a 502 is a
// failure, not an exit IP.
func fetch(client *http.Client, target string) (string, bool) {
	resp, err := client.Get(target)
	if err != nil {
		// For an https:// target a 407 arrives as an error from the CONNECT step.
		if strings.Contains(err.Error(), "Proxy Authentication Required") {
			fmt.Fprintln(os.Stderr, "407 from the proxy: check NODE4_USER/NODE4_PASS and that your plan includes this product")
		}
		return "", false
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil || resp.StatusCode != http.StatusOK {
		if resp.StatusCode == http.StatusProxyAuthRequired {
			fmt.Fprintln(os.Stderr, "407 from the proxy: check NODE4_USER/NODE4_PASS and that your plan includes this product")
		}
		return "", false
	}
	return strings.TrimSpace(string(body)), true
}

func main() {
	workers := flag.Int("workers", 10, "concurrent connections (keep at or below your plan's limit)")
	n := flag.Int("n", 40, "requests to send")
	fresh := flag.Bool("fresh", true, "new connection per request (new exit per request)")
	target := flag.String("url", "https://api.ipify.org", "URL to fetch")
	flag.Parse()

	user, pass := os.Getenv("NODE4_USER"), os.Getenv("NODE4_PASS")
	if user == "" || pass == "" {
		fmt.Fprintln(os.Stderr, "Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).")
		os.Exit(1)
	}
	gateway := os.Getenv("NODE4_GATEWAY")
	if gateway == "" {
		gateway = "gw-rotating_datacenter.node4.io:8083"
	}
	proxy := &url.URL{Scheme: "http", User: url.UserPassword(user, pass), Host: gateway}

	client := &http.Client{
		Timeout: 30 * time.Second,
		Transport: &http.Transport{
			Proxy:               http.ProxyURL(proxy),
			DisableKeepAlives:   *fresh,
			MaxConnsPerHost:     *workers,
			MaxIdleConnsPerHost: *workers,
		},
	}

	jobs := make(chan int)
	var mu sync.Mutex
	exits := map[string]int{}
	failed := 0
	var wg sync.WaitGroup
	for w := 0; w < *workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for range jobs {
				ip, ok := fetch(client, *target)
				mu.Lock()
				if ok {
					exits[ip]++
				} else {
					failed++
				}
				mu.Unlock()
			}
		}()
	}
	start := time.Now()
	for i := 0; i < *n; i++ {
		jobs <- i
	}
	close(jobs)
	wg.Wait()

	fmt.Printf("%d requests, %d failed, %d distinct exits, %d workers, %s\n",
		*n, failed, len(exits), *workers, time.Since(start).Round(time.Millisecond))
}
