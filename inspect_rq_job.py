"""Inspect RQ job status directly and write output to file."""
import os
import sys
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import json
import redis
from rq import Queue
from rq.job import Job

# Redirect all output to file
out = open("inspect_output.txt", "w", encoding="utf-8")
try:
    r = redis.from_url("redis://localhost:6379/0", decode_responses=True)

    all_keys = sorted(r.keys("*"))
    out.write(f"=== All Redis keys ({len(all_keys)}) ===\n")
    for k in all_keys:
        key_type = r.type(k)
        out.write(f"  [{key_type}] {k}\n")

    out.write("\n=== RQ Queue State ===\n")
    conn = redis.from_url("redis://localhost:6379/0")
    q = Queue("account-analysis", connection=conn)
    out.write(f"Queue length: {len(q)}\n")
    out.write(f"Job IDs in queue: {q.job_ids}\n")
    out.write(f"Failed job registry count: {q.failed_job_registry.count}\n")
    out.write(f"Finished job registry count: {q.finished_job_registry.count}\n")
    out.write(f"Started job registry count: {q.started_job_registry.count}\n")

    # Get failed job IDs
    failed_ids = q.failed_job_registry.get_job_ids()
    out.write(f"Failed job IDs: {failed_ids}\n")

    # Get finished job IDs
    finished_ids = q.finished_job_registry.get_job_ids()
    out.write(f"Finished job IDs: {finished_ids}\n")

    # Check the app-level job keys
    for k in all_keys:
        if k.startswith("account_analysis:job:"):
            job_id = k.split(":")[-1]
            out.write(f"\n=== App Job: {job_id} ===\n")
            val = r.get(k)
            if val:
                try:
                    data = json.loads(val)
                    out.write(json.dumps(data, indent=2, default=str) + "\n")
                except json.JSONDecodeError as exc:
                    out.write(f"Invalid JSON: {exc}\nRaw value: {val[:500]}\n")

            # Try to fetch RQ job
            out.write(f"\n=== RQ Job: {job_id} ===\n")
            try:
                job = Job.fetch(job_id, connection=conn)
                out.write(f"RQ status: {job.get_status()}\n")
                out.write(f"func_name: {job.func_name}\n")
                out.write(f"enqueued_at: {job.enqueued_at}\n")
                out.write(f"started_at: {job.started_at}\n")
                out.write(f"ended_at: {job.ended_at}\n")
                exc = job.exc_info
                if exc:
                    out.write(f"exc_info: {exc}\n")
                result = job.result
                if result is not None:
                    out.write(f"result type: {type(result)}\n")
                    if isinstance(result, dict):
                        out.write(f"result keys: {list(result.keys())}\n")
                        result_json = json.dumps(result, indent=2, default=str)
                        if len(result_json) > 5000:
                            out.write(result_json[:5000] + "\n... [TRUNCATED]\n")
                        else:
                            out.write(result_json + "\n")
            except Exception as e:
                out.write(f"Error fetching RQ job: {e}\n")
finally:
    out.close()
print("Written to inspect_output.txt")
