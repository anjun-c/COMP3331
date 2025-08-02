#!/usr/bin/env python3
import time
import threading
import statistics
import requests

# Configuration
PROXY = "http://127.0.0.1:8080"
TARGET_URL = "http://httpbin.org/delay/2"
TOTAL_REQUESTS = 50
CONCURRENCY = 10

proxies = {
    "http": PROXY,
    "https": PROXY,
}

timings = []
lock = threading.Lock()

def worker(i):
    start = time.time()
    try:
        r = requests.get(TARGET_URL, proxies=proxies, timeout=10)
        elapsed = time.time() - start
        status = r.status_code
    except Exception as e:
        elapsed = None
        status = f"ERROR({e.__class__.__name__})"
    with lock:
        timings.append((i, elapsed, status))
        print(f"Req #{i:2d}: {status} in {elapsed:.3f}s" if elapsed else f"Req #{i:2d}: {status}")

threads = []
for i in range(1, TOTAL_REQUESTS+1):
    t = threading.Thread(target=worker, args=(i,))
    threads.append(t)
    t.start()
    # throttle to at most CONCURRENCY in flight
    while threading.active_count() > CONCURRENCY:
        time.sleep(0.01)

# wait for all to finish
for t in threads:
    t.join()

# summarize
valid_times = [t for (_, t, s) in timings if t is not None]
print("\n--- Summary ---")
print(f"Total requests:      {TOTAL_REQUESTS}")
print(f"Succeeded:           {len(valid_times)}")
print(f"Mean latency:        {statistics.mean(valid_times):.3f}s")
print(f"Median latency:      {statistics.median(valid_times):.3f}s")
print(f"Min latency:         {min(valid_times):.3f}s")
print(f"Max latency:         {max(valid_times):.3f}s")
