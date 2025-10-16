import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Load environment variables from .env file (for local development)
load_dotenv()
# --- Database Configuration ---

# --- Database Configuration ---
# Use DATABASE_URL if set (e.g., in production on Render), otherwise construct from individual env vars
# Note: Ensure all required env vars are set in .env for local dev or in deployment env
SQLALCHEMY_DATABASE_URL = os.getenv('DATABASE_URL') or f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

# --- Create the engine ---
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
