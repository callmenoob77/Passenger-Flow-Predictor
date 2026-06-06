import psycopg2

CONN = "postgresql://postgres.tuqhlwpmhkirtvgihdxs:AdiDamianGebz@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"

def main():
    print("Connecting to Supabase...")
    conn = psycopg2.connect(CONN)
    cur = conn.cursor()
    
    print("Creating passenger_notifications table...")
    sql = """
    CREATE TABLE IF NOT EXISTS passenger_notifications (
        id SERIAL PRIMARY KEY,
        email TEXT NOT NULL,
        flight_number TEXT NOT NULL,
        subscribed_at TIMESTAMPTZ DEFAULT NOW(),
        notified BOOLEAN DEFAULT FALSE,
        notified_at TIMESTAMPTZ NULL,
        CONSTRAINT unique_email_flight UNIQUE (email, flight_number)
    );
    """
    cur.execute(sql)
    conn.commit()
    
    print("Verifying table in database...")
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'passenger_notifications'
        );
    """)
    exists = cur.fetchone()[0]
    print(f"Table passenger_notifications exists: {exists}")
    
    cur.close()
    conn.close()
    print("Database migration completed successfully.")

if __name__ == "__main__":
    main()
