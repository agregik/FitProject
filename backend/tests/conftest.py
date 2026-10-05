import os
import tempfile

# Must be set before app modules are imported: config reads env at import time,
# and real values from backend/.env never override what's already set here.
_tmp = tempfile.mkdtemp(prefix="fitproject-test-")
os.environ["DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["DEMO_MODE"] = "0"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest  # noqa: E402

from app import db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    if os.path.exists(os.environ["DB_PATH"]):
        os.remove(os.environ["DB_PATH"])
    db.init()
    yield


@pytest.fixture
def user_id():
    return db.execute("INSERT INTO users (first_name, api_token, created_at) VALUES ('T', 'tok-test', ?)",
                      (db.now_iso(),))
