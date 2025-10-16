import os
import pymysql
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

# Read values
db_host = os.getenv("DB_HOST")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")

try:
    connection = pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name
    )
    print("✅ Database connection successful!")
    connection.close()
except Exception as e:
    print("❌ Database connection failed:")
    print(e)
