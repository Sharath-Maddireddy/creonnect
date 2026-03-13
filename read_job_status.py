"""Read job status directly from Redis and dump to a file."""
import json
import redis

r = redis.from_url("redis://localhost:6379/0", decode_responses=True)
keys = r.keys("account_analysis:job:*")

all_jobs = {}
if not keys:
    print("No job keys found in Redis!")
else:
    for key in keys:
        job_id = key.split(":")[-1]
        print(f"job_id: {job_id}")
        val = r.get(key)
        if val:
            try:
                data = json.loads(val)
            except json.JSONDecodeError as exc:
                print(f"Invalid JSON for key {key}: {exc}")
                continue
            all_jobs[job_id] = data
            print(f"Status: {data.get('status')}")
            print(f"Top-level keys: {list(data.keys())}")
            # Print result top-level keys if result is present
            if "result" in data and data["result"]:
                result = data["result"]
                if isinstance(result, dict):
                    print(f"Result top-level keys: {list(result.keys())}")
        else:
            print(f"No value for key: {key}")
    if all_jobs:
        with open("smoke_job_status.json", "w", encoding="utf-8") as f:
            json.dump(all_jobs, f, indent=2, ensure_ascii=False, default=str)
        print(f"Full status data for {len(all_jobs)} job(s) written to smoke_job_status.json")
