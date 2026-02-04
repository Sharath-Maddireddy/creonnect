"""
Dataset Statistics

Compute basic statistics from training_data.jsonl.
"""

import json
from pathlib import Path


def load_training_data():
    """Load and parse training_data.jsonl, handling malformed lines gracefully."""
    data_path = Path(__file__).parent / "training_data.jsonl"
    
    records = []
    malformed_count = 0
    
    if not data_path.exists():
        print(f"Error: {data_path} not found.")
        return []
    
    with open(data_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                malformed_count += 1
                print(f"Warning: Malformed JSON on line {line_num}: {e}")
    
    if malformed_count > 0:
        print(f"Skipped {malformed_count} malformed lines.\n")
    
    return records


def compute_stats(records):
    """Compute and print statistics from training records."""
    
    if not records:
        print("No records to analyze.")
        return
    
    followers_list = []
    growth_scores = []
    niche_counts = {}
    
    for record in records:
        try:
            # Extract followers
            followers = record.get("input", {}).get("profile", {}).get("followers")
            if followers is not None:
                followers_list.append(followers)
            
            # Extract growth score
            growth_score = record.get("output", {}).get("growth", {}).get("growth_score")
            if growth_score is not None:
                growth_scores.append(growth_score)
            
            # Extract primary niche
            primary_niche = record.get("output", {}).get("niche", {}).get("primary_niche")
            if primary_niche:
                niche_counts[primary_niche] = niche_counts.get(primary_niche, 0) + 1
        except Exception as e:
            print(f"Warning: Error extracting data from record: {e}")
    
    # Print statistics
    print("=" * 50)
    print("TRAINING DATASET STATISTICS")
    print("=" * 50)
    
    print(f"\nTotal examples:      {len(records)}")
    
    if followers_list:
        avg_followers = sum(followers_list) / len(followers_list)
        print(f"Average followers:   {avg_followers:,.0f}")
    else:
        print("Average followers:   N/A")
    
    if growth_scores:
        avg_growth = sum(growth_scores) / len(growth_scores)
        print(f"Average growth score: {avg_growth:.1f}")
    else:
        print("Average growth score: N/A")
    
    # Niche distribution
    print("\n" + "-" * 50)
    print("NICHE DISTRIBUTION")
    print("-" * 50)
    
    if niche_counts:
        # Sort by count descending
        sorted_niches = sorted(niche_counts.items(), key=lambda x: x[1], reverse=True)
        for niche, count in sorted_niches:
            pct = (count / len(records)) * 100
            print(f"  {niche}: {count} ({pct:.1f}%)")
    else:
        print("  No niche data available.")
    
    print("=" * 50)


def main():
    records = load_training_data()
    compute_stats(records)


if __name__ == "__main__":
    main()
