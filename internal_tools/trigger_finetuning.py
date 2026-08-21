import os
import argparse
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv("backend/.env", override=True)

def trigger_finetuning(dataset_path: str, model: str = "gpt-4o-mini-2024-07-18"):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable is not set.")
        return

    if not os.path.exists(dataset_path):
        print(f"Error: Dataset not found at {dataset_path}")
        return

    client = OpenAI(api_key=api_key)

    print(f"Uploading file {dataset_path}...")
    with open(dataset_path, "rb") as f:
        file_response = client.files.create(
            file=f,
            purpose="fine-tune"
        )
    
    file_id = file_response.id
    print(f"File uploaded successfully! ID: {file_id}")

    print(f"Starting fine-tuning job for model {model}...")
    job_response = client.fine_tuning.jobs.create(
        training_file=file_id,
        model=model,
    )

    print("Fine-tuning job created successfully!")
    print(f"Job ID: {job_response.id}")
    print(f"Status: {job_response.status}")
    print("\nYou can check the status of the job in the OpenAI dashboard or via the API.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trigger OpenAI fine-tuning")
    parser.add_argument("--dataset", type=str, default="internal_tools/artifacts/finetune_dataset_batch.jsonl", help="Path to JSONL dataset")
    parser.add_argument("--model", type=str, default="gpt-4o-mini-2024-07-18", help="Base model to fine-tune")
    args = parser.parse_args()

    trigger_finetuning(args.dataset, args.model)
