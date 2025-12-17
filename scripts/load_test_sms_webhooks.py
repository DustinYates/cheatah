"""Load testing script for SMS webhook endpoints."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx


async def send_webhook_request(client: httpx.AsyncClient, url: str, payload: dict) -> dict:
    """Send a single webhook request."""
    start_time = time.time()
    try:
        response = await client.post(url, data=payload, timeout=5.0)
        latency = (time.time() - start_time) * 1000
        return {
            "status_code": response.status_code,
            "latency_ms": latency,
            "success": response.status_code == 200,
        }
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return {
            "status_code": 0,
            "latency_ms": latency,
            "success": False,
            "error": str(e),
        }


async def load_test_webhooks(
    base_url: str = "http://localhost:8000",
    num_requests: int = 100,
    concurrency: int = 10,
):
    """Load test SMS webhook endpoint.
    
    Args:
        base_url: Base URL of the API
        num_requests: Number of requests to send
        concurrency: Number of concurrent requests
    """
    print(f"Load Testing SMS Webhooks")
    print("=" * 50)
    print(f"Base URL: {base_url}")
    print(f"Total Requests: {num_requests}")
    print(f"Concurrency: {concurrency}")
    print()
    
    url = f"{base_url}/api/v1/sms/inbound"
    
    # Create payload
    payload = {
        "From": "+1234567890",
        "To": "+0987654321",
        "Body": "Test message",
        "MessageSid": "SM123",
        "AccountSid": "AC123",
    }
    
    results = []
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(concurrency)
        
        async def bounded_request():
            async with semaphore:
                return await send_webhook_request(client, url, payload)
        
        # Send requests
        tasks = [bounded_request() for _ in range(num_requests)]
        results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    
    # Analyze results
    successful = sum(1 for r in results if r["success"])
    failed = num_requests - successful
    latencies = [r["latency_ms"] for r in results if r["success"]]
    
    print("Results:")
    print(f"  Total Requests: {num_requests}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Success Rate: {(successful/num_requests)*100:.2f}%")
    print(f"  Total Time: {total_time:.2f}s")
    print(f"  Requests/sec: {num_requests/total_time:.2f}")
    
    if latencies:
        print(f"\nLatency Statistics (ms):")
        print(f"  Min: {min(latencies):.2f}")
        print(f"  Max: {max(latencies):.2f}")
        print(f"  Avg: {sum(latencies)/len(latencies):.2f}")
        print(f"  Median: {sorted(latencies)[len(latencies)//2]:.2f}")
    
    print("\n" + "=" * 50)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Load test SMS webhook endpoints")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--requests", type=int, default=100, help="Number of requests")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrency level")
    
    args = parser.parse_args()
    
    asyncio.run(load_test_webhooks(
        base_url=args.url,
        num_requests=args.requests,
        concurrency=args.concurrency,
    ))

