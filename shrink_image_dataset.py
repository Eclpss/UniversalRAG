import pandas as pd
import os

def shrink_dataset():
    original_path = "dataset/image.parquet"
    backup_path = "dataset/image_FULL_BACKUP.parquet"
    
    if not os.path.exists(original_path):
        print("❌ Could not find dataset/image.parquet")
        return

    print("📂 Loading the massive image dataset...")
    df = pd.read_parquet(original_path, engine="fastparquet")
    
    # Backup the original so you don't lose the dosen's full dataset!
    if not os.path.exists(backup_path):
        df.to_parquet(backup_path, engine="fastparquet")
        print("✅ Backed up original dataset to image_FULL_BACKUP.parquet")
    
    print("✂️ Slicing exactly ONE image row...")
    micro_df = df.head(1) 
    
    # Overwrite the target file with just the single row
    micro_df.to_parquet(original_path, engine="fastparquet")
    print("🎉 SUCCESS! dataset/image.parquet now contains exactly 1 image.")

if __name__ == "__main__":
    shrink_dataset()