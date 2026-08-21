import asyncio
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Load env variables before importing database
load_dotenv("backend/.env", override=True)

from sqlalchemy import select
from backend.app.infra.database import init_db, get_async_sessionmaker
from backend.app.infra.models import BackgroundJob
from backend.app.utils.logger import logger

async def extract_finetuning_data(output_file: str, limit: int = 1000):
    try:
        logger.info("Initializing database...")
        await init_db(strict=True)
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return

    session_maker = get_async_sessionmaker()
    
    # We want successful account analysis jobs that have both payload and result
    query = (
        select(BackgroundJob)
        .where(BackgroundJob.status == "succeeded")
        .where(BackgroundJob.job_name == "account_analysis")
        .where(BackgroundJob.payload_json.is_not(None))
        .where(BackgroundJob.result_json.is_not(None))
        .order_by(BackgroundJob.created_at.desc())
        .limit(limit)
    )

    extracted_count = 0
    seen_accounts = set()
    
    with open(output_file, "w", encoding="utf-8") as f:
        async with session_maker() as session:
            result = await session.execute(query)
            jobs = result.scalars().all()
            
            for job in jobs:
                account_id = job.account_id
                if account_id:
                    if account_id in seen_accounts:
                        continue
                    seen_accounts.add(account_id)
                
                payload = job.payload_json
                result_data = job.result_json
                
                # Reconstruct prompt logic (simplified representation for fine-tuning)
                # In practice, we'd rebuild the exact system and user prompt.
                # For this proof of concept, we embed the JSON payload as user input
                # and the result JSON as assistant output.
                
                system_prompt = "You are an expert AI social media analyst. Analyze the account and its posts to provide a comprehensive account health score, feature predictions, and creator intelligence."
                
                user_content = json.dumps(payload, ensure_ascii=False)
                assistant_content = json.dumps(result_data, ensure_ascii=False)
                
                record = {
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                        {"role": "assistant", "content": assistant_content}
                    ]
                }
                
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                extracted_count += 1

    logger.info(f"Successfully extracted {extracted_count} records to {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract fine-tuning data from Supabase")
    parser.add_argument("--output", type=str, default="internal_tools/artifacts/finetune_dataset_batch.jsonl", help="Output file path")
    parser.add_argument("--limit", type=int, default=1000, help="Max records to extract")
    args = parser.parse_args()
    
    # Ensure artifacts directory exists
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    
    asyncio.run(extract_finetuning_data(args.output, args.limit))
