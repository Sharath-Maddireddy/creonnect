"""
Split Dataset Script

Splits training_data.jsonl into train and validation sets.
- 80% train.jsonl
- 20% val.jsonl
"""

import json
import random
from pathlib import Path


def split_dataset(train_ratio: float = 0.8, seed: int = 42):
    """Split training_data.jsonl into train and val sets."""
    
    script_dir = Path(__file__).parent
    input_file = script_dir / "training_data.jsonl"
    train_file = script_dir / "train.jsonl"
    val_file = script_dir / "val.jsonl"
    
    # Load all examples
    examples = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    examples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    
    total = len(examples)
    if total == 0:
        print("No examples found in training_data.jsonl")
        return
    
    # Shuffle
    random.seed(seed)
    random.shuffle(examples)
    
    # Split
    split_idx = int(total * train_ratio)
    train_examples = examples[:split_idx]
    val_examples = examples[split_idx:]
    
    # Write train.jsonl
    with open(train_file, "w", encoding="utf-8") as f:
        for ex in train_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    
    # Write val.jsonl
    with open(val_file, "w", encoding="utf-8") as f:
        for ex in val_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    
    # Print summary
    print("=" * 50)
    print("DATASET SPLIT COMPLETE")
    print("=" * 50)
    print(f"  Total examples:      {total}")
    print(f"  Train examples:      {len(train_examples)} ({len(train_examples)/total*100:.1f}%)")
    print(f"  Validation examples: {len(val_examples)} ({len(val_examples)/total*100:.1f}%)")
    print("-" * 50)
    print(f"  Saved train.jsonl:   {train_file}")
    print(f"  Saved val.jsonl:     {val_file}")
    print("=" * 50)


if __name__ == "__main__":
    split_dataset()
