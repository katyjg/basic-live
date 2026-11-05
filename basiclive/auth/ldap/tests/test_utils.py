from django.test import SimpleTestCase

from basiclive.auth.ldap.utils import clean_user_data


class LdapCleanUserDataTests(SimpleTestCase):
    def test_clean_user_data_splits_full_name_when_first_name_empty(self):
        data = {
            "username": "jdoe",
            "first_name": "",
            "last_name": "Jane Doe",
            "email": "jdoe@example.com",
        }
        cleaned = clean_user_data(data)
        self.assertEqual(cleaned["first_name"], "Jane")
        self.assertEqual(cleaned["last_name"], "Doe")

    def test_clean_user_data_handles_multi_part_last_name(self):
        data = {
            "username": "jdoe",
            "first_name": "",
            "last_name": "Mary Jane Watson",
            "email": "mj@example.com",
        }
        cleaned = clean_user_data(data)
        self.assertEqual(cleaned["first_name"], "Mary")
        self.assertEqual(cleaned["last_name"], "Jane Watson")

    def test_clean_user_data_preserves_existing_first_name(self):
        data = {
            "username": "jdoe",
            "first_name": "John",
            "last_name": "Von Neumann",
            "email": "jvn@example.com",
        }
        cleaned = clean_user_data(data)
        self.assertEqual(cleaned["first_name"], "John")
        self.assertEqual(cleaned["last_name"], "Von Neumann")

    def test_clean_user_data_handles_single_word_last_name_without_first_name(self):
        data = {
            "username": "admin",
            "first_name": "",
            "last_name": "Administrator",
            "email": "admin@example.com",
        }
        cleaned = clean_user_data(data)
        self.assertEqual(cleaned["first_name"], "")
        self.assertEqual(cleaned["last_name"], "Administrator")
