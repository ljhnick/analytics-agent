#!/usr/bin/env python3
"""
Simple Module Table Data Retrieval
This script gets the module table data as a pandas DataFrame for analysis
"""

from database_connection import get_db_connection
import pandas as pd
import matplotlib.pyplot as plt
def get_module_dataframe(limit=None, show_info=True):
    """
    Get module table as pandas DataFrame
    
    Args:
        limit (int, optional): Limit the number of rows. If None, gets all data.
        show_info (bool): Whether to show basic information about the data
    
    Returns:
        pandas.DataFrame: The module table data
    """
    if show_info:
        print("🔍 Retrieving Module Table Data")
        print("=" * 50)
    
    db = get_db_connection()
    
    try:
        if not db.connect():
            print("❌ Failed to connect to database")
            return None
        
        # Build query
        if limit:
            query = f"SELECT * FROM module LIMIT {limit}"
            if show_info:
                print(f"📊 Loading {limit} rows from module table...")
        else:
            query = "SELECT * FROM module"
            if show_info:
                print(f"📊 Loading all data from module table...")
        
        # Execute query
        df = db.execute_query(query)
        db.close()
        
        if df is None or df.empty:
            print("❌ No data found in module table")
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
        print(f"❌ Error getting module data: {e}")
        if db:
            db.close()
        return None

def analyze_module_basic(df):
    """
    Basic analysis of the module DataFrame
    
    Args:
        df (pandas.DataFrame): The module table DataFrame
    """
    if df is None or df.empty:
        print("No data to analyze")
        return
    
    print("\n" + "=" * 60)
    print("📊 BASIC MODULE TABLE ANALYSIS")
    print("=" * 60)
    
    # 1. Unique users and threads
    if 'userid' in df.columns:
        unique_users = df['userid'].nunique()
        print(f"👥 Unique users: {unique_users:,}")
    
    if 'threadid' in df.columns:
        unique_threads = df['threadid'].nunique()
        print(f"💬 Unique threads: {unique_threads:,}")
    
    # 2. Date range analysis
    date_cols = ['created_at', 'updated_at']
    for col in date_cols:
        if col in df.columns:
            min_date = df[col].min()
            max_date = df[col].max()
            print(f"📅 {col}: {min_date} to {max_date}")
    
    # 3. Action analysis
    if 'action' in df.columns:
        print(f"\n🎯 Top 10 Actions:")
        action_counts = df['action'].value_counts().head(10)
        for action, count in action_counts.items():
            pct = (count / len(df)) * 100
            print(f"  {action[:50]:<50} | {count:>6} ({pct:>5.1f}%)")
    
    # 4. Activity by user (top 10)
    if 'userid' in df.columns:
        print(f"\n👤 Top 10 Most Active Users:")
        user_activity = df['userid'].value_counts().head(10)
        for userid, count in user_activity.items():
            pct = (count / len(df)) * 100
            print(f"  User {userid:<20} | {count:>6} actions ({pct:>5.1f}%)")
    
    # 5. Activity by thread (top 10)
    if 'threadid' in df.columns:
        print(f"\n💬 Top 10 Most Active Threads:")
        thread_activity = df['threadid'].value_counts().head(10)
        for threadid, count in thread_activity.items():
            pct = (count / len(df)) * 100
            print(f"  Thread {threadid:<20} | {count:>6} actions ({pct:>5.1f}%)")

if __name__ == "__main__":
    module_df = get_module_dataframe(limit=None)
    if module_df is not None:
        analyze_module_basic(module_df)
