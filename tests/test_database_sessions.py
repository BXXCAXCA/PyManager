import unittest
from types import SimpleNamespace

from src.database import DatabaseManager


class FakeSession:
    def __init__(self):
        self.closed = False
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class DatabaseSessionTests(unittest.TestCase):
    def test_session_scope_rolls_back_and_closes_on_error(self):
        db = DatabaseManager("sqlite:///:memory:")
        fake_session = FakeSession()
        db.get_session = lambda: fake_session

        with self.assertRaises(AttributeError):
            db.save_environment(SimpleNamespace(location="/tmp/demo"))

        self.assertTrue(fake_session.rolled_back)
        self.assertTrue(fake_session.closed)
        db.close()


if __name__ == "__main__":
    unittest.main()
