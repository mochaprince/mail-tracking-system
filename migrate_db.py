#!/usr/bin/env python3
"""
Database migration script to add missing columns to the mails table.
Run this before starting the application in production.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import urlparse, parse_qs, urlunparse

# Load environment variables
if not os.getenv('DATABASE_URL'):
    load_dotenv()

# Get database URL
database_url = os.getenv('DATABASE_URL')
if database_url:
    # Parse and reconstruct URL for mysql-connector-python
    parsed = urlparse(database_url)
    query_params = parse_qs(parsed.query)
    if 'ssl-mode' in query_params:
        del query_params['ssl-mode']
    new_query = '&'.join([f"{k}={v[0]}" for k, v in query_params.items()])
    scheme = "mysql+mysqlconnector"
    SQLALCHEMY_DATABASE_URL = urlunparse((scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
else:
    SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

def migrate_database():
    """Add missing columns to the mails table."""
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

    with engine.connect() as conn:
        # Check if reminder_sent_at column exists
        result = conn.execute(text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'mails'
            AND COLUMN_NAME = 'reminder_sent_at'
        """))

        if not result.fetchone():
            print("Adding reminder_sent_at column to mails table...")
            conn.execute(text("""
                ALTER TABLE mails
                ADD COLUMN reminder_sent_at DATETIME NULL
            """))
            conn.commit()
            print("✅ Column added successfully!")
        else:
            print("✅ Column already exists.")

        # Check if eksu_ref column exists
        result = conn.execute(text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'mails'
            AND COLUMN_NAME = 'eksu_ref'
        """))

        if not result.fetchone():
            print("Adding eksu_ref column to mails table...")
            conn.execute(text("""
                ALTER TABLE mails
                ADD COLUMN eksu_ref VARCHAR(20) UNIQUE NULL
            """))
            conn.commit()
            print("✅ eksu_ref column added successfully!")
        else:
            print("✅ eksu_ref column already exists.")

        print("Migration completed!")

if __name__ == "__main__":
    migrate_database()
