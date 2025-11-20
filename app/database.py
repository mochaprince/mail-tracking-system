import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Load environment variables from .env file only if DATABASE_URL is not set (for local development)
if not os.getenv('DATABASE_URL'):
    load_dotenv()
# --- Database Configuration ---

# --- Database Configuration ---
# Use DATABASE_URL if set (e.g., in production on Render), otherwise construct from individual env vars
# Note: Ensure all required env vars are set in .env for local dev or in deployment env
database_url = os.getenv('DATABASE_URL')
if database_url:
    # For production (Render), parse and reconstruct URL to handle SSL parameters properly
    from urllib.parse import urlparse, parse_qs, urlunparse
    parsed = urlparse(database_url)
    query_params = parse_qs(parsed.query)
    # Remove ssl-mode and add ssl parameters if needed
    if 'ssl-mode' in query_params:
        del query_params['ssl-mode']
        # For PyMySQL, we might need to handle SSL differently, but for now, remove the param
    new_query = '&'.join([f"{k}={v[0]}" for k, v in query_params.items()])
    # Ensure the scheme includes the mysql-connector-python driver
    scheme = "mysql+mysqlconnector"
    SQLALCHEMY_DATABASE_URL = urlunparse((scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
else:
    # For local development, construct from individual env vars
    SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

# --- Create the engine ---
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
