"""
Bulk Generate Training Dataset

Generate many synthetic creators and append them to training_data.jsonl.
Orchestrates existing generators without modifying them.
"""

import subprocess
import sys
from pathlib import Path


def bulk_generate(n: int = 30):
    """Generate N synthetic creator examples and append to training dataset."""
    
    # Get the directory containing the scripts
    script_dir = Path(__file__).parent
    
    # Script paths
    generator_script = script_dir / "generate_fake_creator_snapshot.py"
    builder_script = script_dir / "build_training_dataset.py"
    
    print(f"Starting bulk generation of {n} examples...")
    print("=" * 50)
    
    for i in range(1, n + 1):
        # Step 1: Generate new synthetic creator snapshot
        subprocess.run(
            [sys.executable, str(generator_script)],
            check=True,
            cwd=str(script_dir)
        )
        
        # Step 2: Build training dataset entry from snapshot
        subprocess.run(
            [sys.executable, str(builder_script)],
            check=True,
            cwd=str(script_dir)
        )
        
        # Print progress
        print(f"Generated example {i} / {n}")
    
    print("=" * 50)
    print("Bulk dataset generation complete.")


if __name__ == "__main__":
    # Check for optional CLI argument
    if len(sys.argv) > 1:
        try:
            n = int(sys.argv[1])
        except ValueError:
            print(f"Invalid argument: {sys.argv[1]}. Using default N=30.")
            n = 30
    else:
        n = 30
    
    bulk_generate(n)
