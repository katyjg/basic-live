from typing import Any


def clean_user_data(user_fields: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize and normalize user fields retrieved from LDAP prior to updating
    or creating the User model instance.

    In POSIX and certain LDAP setups, `givenName` (first_name) may be unset while
    `sn` (last_name) contains the user's full name. If first_name is empty and
    last_name contains whitespace, split into first_name and last_name.
    """
    first_name = (user_fields.get("first_name") or "").strip()
    last_name = (user_fields.get("last_name") or "").strip()

    if not first_name and " " in last_name:
        parts = last_name.split(None, 1)
        user_fields["first_name"] = parts[0]
        user_fields["last_name"] = parts[1]

    return user_fields
