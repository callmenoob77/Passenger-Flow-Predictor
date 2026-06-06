import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import psycopg2
from config import CONN

def main():
    print("Connecting to Supabase...")
    conn = psycopg2.connect(CONN)
    cur = conn.cursor()
    
    print("Creating refund_requests table...")
    sql = """
    CREATE TABLE IF NOT EXISTS refund_requests (
        id SERIAL PRIMARY KEY,
        flight_number TEXT NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT NOT NULL,
        pnr TEXT NOT NULL,
        refund_type TEXT NOT NULL,
        notes TEXT NULL,
        submitted_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    cur.execute(sql)
    conn.commit()
    
    print("Verifying table in database...")
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'refund_requests'
        );
    """)
    exists = cur.fetchone()[0]
    print(f"Table refund_requests exists: {exists}")
    
    cur.close()
    conn.close()
    print("Database migration completed successfully.")

if __name__ == "__main__":
    main()
