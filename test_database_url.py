import os
import sys
sys.path.append('.')

# Test without DATABASE_URL set
print("Testing without DATABASE_URL set:")
if 'DATABASE_URL' in os.environ:
    del os.environ['DATABASE_URL']

try:
    from app.database import SQLALCHEMY_DATABASE_URL
    print(f"SQLALCHEMY_DATABASE_URL: {SQLALCHEMY_DATABASE_URL}")
except Exception as e:
    print(f"Error: {e}")

print("\nTesting with DATABASE_URL set:")
os.environ['DATABASE_URL'] = 'mysql+pymysql://testuser:testpass@testhost:3306/testdb'

# Reload the module to test again
import importlib
import app.database
importlib.reload(app.database)
from app.database import SQLALCHEMY_DATABASE_URL
print(f"SQLALCHEMY_DATABASE_URL: {SQLALCHEMY_DATABASE_URL}")
