import os
import sys

def run_cmd(cmd):
    print(f"Executing: {cmd}")
    res = os.system(cmd)
    if res != 0:
        print(f"Error executing: {cmd}")
        sys.exit(1)

def main():
    print("=== mini-GCR Pipeline ===")
    
    # 1. Generate Mock Data (Since we don't have real Tmall data)
    run_cmd("python scripts/generate_mock_data.py")
    
    # 2. Preprocess Data
    run_cmd("python scripts/preprocess.py")
    
    # 3. Build Complementary Pairs and Tokens
    run_cmd("python scripts/build_complementary.py")
    run_cmd("python scripts/tokenize.py")
    
    # 4. Train Models
    # Uncomment below to actually train. Takes time.
    print("Skip actual training in the auto-script to save time. You can run manually:")
    print("  python scripts/train_sasrec.py")
    print("  python scripts/train_mingpt.py")
    
    # 5. Evaluate
    print("Skip evaluation in the auto-script since models are not trained yet.")
    print("  python scripts/eval.py")
    
    print("Pipeline data generation and preprocessing completed.")

if __name__ == "__main__":
    main()
