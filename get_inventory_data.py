from database_connection import get_db_connection
import pandas as pd
import matplotlib.pyplot as plt
def get_inventory_dataframe(limit=None, show_info=True):
    """
    Get inventory table as pandas DataFrame
    
    Args:
        limit (int, optional): Limit the number of rows. If None, gets all data.
        show_info (bool): Whether to show basic information about the data
    
    Returns:
        pandas.DataFrame: The inventory table data
    """
    if show_info:
        print("🔍 Retrieving Inventory Table Data")
        print("=" * 50)
    
    db = get_db_connection()
    
    try:
        if not db.connect():
            print("❌ Failed to connect to database")
            return None
        
        # Build query
        if limit:
            query = f"SELECT * FROM inventory LIMIT {limit}"
            if show_info:
                print(f"📊 Loading {limit} rows from inventory table...")
        else:
            query = "SELECT * FROM inventory"
            if show_info:
                print(f"📊 Loading all data from inventory table...")
        
        # Execute query
        df = db.execute_query(query)
        db.close()
        
        if df is None or df.empty:
            print("❌ No data found in inventory table")
            return None
        
        if show_info:
            print(f"✅ Successfully loaded {len(df)} rows with {len(df.columns)} columns")
            
            # Basic info
            print(f"\n📈 Dataset Overview:")
            print(f"Shape: {df.shape}")
            print(f"Memory usage: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
            
            # Column info
            print(f"\n📝 Columns:")
            for i, col in enumerate(df.columns, 1):
                dtype = str(df[col].dtype)
                non_null = df[col].count()
                null_count = df[col].isnull().sum()
                print(f"  {i:2d}. {col:<20} | {dtype:<15} | Non-null: {non_null:>5} | Null: {null_count:>4}")
            
            # Data preview
            print(f"\n👀 First 3 rows:")
            print(df.head(3).to_string(index=False, max_cols=10))
            
            if len(df.columns) > 10:
                print(f"\n... and {len(df.columns) - 10} more columns")
            
            # Missing data summary
            missing_data = df.isnull().sum()
            total_missing = missing_data.sum()
            if total_missing > 0:
                print(f"\n⚠️  Missing Data Summary:")
                missing_cols = missing_data[missing_data > 0]
                for col, count in missing_cols.items():
                    pct = (count / len(df)) * 100
                    print(f"  {col}: {count} missing ({pct:.1f}%)")
            else:
                print(f"\n✅ No missing data found!")
            
            print(f"\n🎯 DataFrame ready for analysis!")
        
        return df
        
    except Exception as e:
        print(f"❌ Error getting inventory data: {e}")
        if db:
            db.close()
        return None
    
def main():
    df = get_inventory_dataframe(limit=None)
    print(df.head())

if __name__ == "__main__":
    main()
