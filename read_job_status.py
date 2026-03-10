"""Read job status directly from Redis and dump to a file."""
import json
import redis

r = redis.from_url("redis://localhost:6379/0", decode_responses=True)
keys = r.keys("account_analysis:job:*")

if not keys:
    print("No job keys found in Redis!")
else:
    for key in keys:
        job_id = key.split(":")[-1]
        print(f"job_id: {job_id}")
        val = r.get(key)
        if val:
            data = json.loads(val)
            with open("smoke_job_status.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            print(f"Status: {data.get('status')}")
            print(f"Top-level keys: {list(data.keys())}")
            # Print result top-level keys if result is present
            if "result" in data and data["result"]:
                result = data["result"]
                if isinstance(result, dict):
                    print(f"Result top-level keys: {list(result.keys())}")
            print(f"Full status data written to smoke_job_status.json")
        else:
            print(f"No value for key: {key}")
