import os
import json
from openai import OpenAI

client = OpenAI()

try:
    jobs = client.fine_tuning.jobs.list(limit=5)
    
    result = []
    for j in jobs.data:
        result.append({
            "job_id": j.id,
            "status": j.status,
            "fine_tuned_model": j.fine_tuned_model
        })
        
    with open("tmp_jobs.json", "w") as f:
        json.dump(result, f, indent=2)
        
    print("Successfully wrote jobs to tmp_jobs.json")
        
except Exception as e:
    print(f"Error checking status: {e}")
