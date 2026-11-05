import os
import random
import secrets
import string


import ldap3
from ldap3 import Server, Connection


from basiclive.auth.ldap.conf import settings


USER_ATTRIBUTES = [
    'cn', 'uid', 'uidNumber', 'gidNumber',
    'homeDirectory', 'loginShell', 'description',
    'gecos', 'objectclass'
]
PAGE_SIZE = 1000


def uniquefy(name, existing):
    """
    Generate a unique name given the requested name and a list of existing names
    :param name: initial guess of name
    :param existing: list of existing names
    :return: a unique name based on the suggested name
    """
    root = f'{name}'.replace('-', '').replace(' ', '').strip().lower()
    choices = [root] + [f'{root}{i}' for i in range(1, 20)]
    candidates = sorted((set(choices) - set(existing)))
    return candidates[0]


def pwd_generator(alpha=6, numeric=3):
    """
    Generate and Returns a human-readble password (say rol816din instead of
    a difficult to remember K8Yn9muL )

    :param alpha: number of alpha characters
    :param numeric: number of numeric characters
    :return: generated password
    """
    vowels = ['a', 'e', 'i', 'o', 'u']
    consonants = [a for a in string.ascii_lowercase if a not in vowels]
    digits = string.digits

    # utility functions
    def a_part(str_len):
        ret = ''
        for i in range(int(str_len)):
            if i % 2 == 0:
                rand_id = random.randint(0, 20)  # number of consonants
                ret += consonants[rand_id]
            else:
                rand_id = random.randint(0, 4)  # number of vowels
                ret += vowels[rand_id]
        ret = ''.join([random.choice([k, k, k, k.upper()]) for k in ret])
        return ret

    def n_part(str_len):
        ret = ''
        for i in range(int(str_len)):
            rand_id = random.randint(0, 9)  # number of digits
            ret += digits[rand_id]
        return ret

    fpl = alpha / 2
    if alpha % 2:
        fpl = int(alpha / 2) + 1
    lpl = alpha - fpl

    start = a_part(fpl)
    mid = n_part(numeric)
    end = a_part(lpl)

    return f"{start}{mid}{end}"


def generate_passphrase(length, separators=None, dictionary: str = None):
    """
    Generates a secure passphrase using random words from a dictionary file.

    :param length: The number of words in the passphrase.
    :param separators: The character(s) to use between words, will randomly choose if multiple.
    :param dictionary: Dictionary file to use.
    :return: A string containing the generated passphrase.
    """
    if separators is None:
        separators = settings.PASSPHRASE_SEPARATORS
    if dictionary is None:
        dictionary = settings.WORDS_DICTIONARY
    try:
        with open(dictionary, 'r') as f:
            words = [word.strip() for word in f if 3 < len(word.strip()) < 15 and word.strip().isalpha()]  # Filter short and very long words
    except FileNotFoundError:
        return "Error: Dictionary file not found at dictionary. Please provide a custom word list."
    except Exception as e:
        return f"An error occurred: {e}"

    # Ensure there are enough words in the list
    if len(words) < length:
        return "Error: Not enough words in the dictionary to generate the requested passphrase length."

    # Use secrets.choice for cryptographically secure random selection
    selected_words = [secrets.choice((str.title, str))(secrets.choice(words)) for _ in range(length)]
    results = [random.choice(separators)]*(2 * length - 1)
    results[::2] = selected_words
    return ''.join(results)


class Directory(object):
    """
    A Directory manager implementing methods for listing and modifying a directory
    """

    def __init__(self, uri=None, user=None, secret=None, use_ssl=True):
        """
        :param uri: Server URI
        :param user: name to bind or None for anonymous bind
        :param secret: password to bind or None for anonymous.
        :param use_ssl: whether to use SSL or not. Default True.
        """
        if ldap3 is None:
            raise RuntimeError("ldap3 is not installed. Install with: poetry install --extras ldap")
        self.admin_user = user if user is not None else settings.MANAGER_DN
        self.admin_secret = secret if secret is not None else settings.MANAGER_SECRET
        server_uri = uri if uri is not None else settings.SERVER_URI
        self.server = Server(server_uri, use_ssl=use_ssl, get_info=ldap3.ALL)

    def _base_dn(self):
        return settings.BASE_DN

    def _group_table(self):
        return settings.GROUP_TABLE

    def _user_table(self):
        return settings.USER_TABLE

    def _user_root(self):
        return settings.USER_ROOT

    def _user_shell(self):
        return settings.USER_SHELL

    def add_user(self, info):
        """
        Add a user entry
        :param info:
        :return: dictionary of new user information
        """
        users = {user['uid'].value: user['uidNumber'].value for user in self.fetch_users()}
        uidNumber = gidNumber = max(list(users.values())) + 1 if users else 1000
        if not info.get('username', '').strip():
            info['username'] = uniquefy(info.get('last_name', 'user'), list(users.keys()))
        if not info.get('password', '').strip():
            info['password'] = pwd_generator()

        base_dn = self._base_dn()
        group_table = self._group_table()
        user_table = self._user_table()
        user_root = self._user_root()
        user_shell = self._user_shell()

        # Create group
        group_dn = f"cn={info['username']},{group_table},{base_dn}"
        group_object_classes = ['top', 'groupOfUniqueNames', 'posixGroup']
        group_record = {
            'cn': info['username'],
            'gidNumber': gidNumber,
            'memberUid': info['username'],
            'objectClass': group_object_classes,
        }

        # Create user
        user_dn = f"uid={info['username']},{user_table},{base_dn}"
        user_object_classes = ['top', 'account', 'posixAccount', 'shadowAccount']
        user_record = {
            'cn': info['username'],
            'uid': info['username'],
            'gecos': f"{info.get('first_name', '')} {info.get('last_name', '')}".strip(),
            'homeDirectory': os.path.join(user_root, info['username']),
            'loginShell': user_shell,
            'uidNumber': uidNumber,
            'gidNumber': gidNumber,
            'objectClass': user_object_classes,
            'userPassword': info['password'],
        }
        with Connection(self.server, user=self.admin_user, password=self.admin_secret, auto_bind=True) as connection:
            group_success = connection.add(group_dn, group_object_classes, group_record)
            user_success = connection.add(user_dn, user_object_classes, user_record)

        del info['password']  # remove password from dictionary before returning
        return info

    def add_group_member(self, group, user):
        """
        Add a user to a group
        :param group: group name
        :param user: user name
        :return: True if successful
        """
        group_dn = f"cn={group},{self._group_table()},{self._base_dn()}"
        with Connection(self.server, user=self.admin_user, password=self.admin_secret, auto_bind=True) as connection:
            return connection.modify(group_dn, {'memberUid': [(ldap3.MODIFY_ADD, [user])]})

    def delete_user(self, username):
        """
        Delete a user entry
        :param username: username of user to delete
        :return: True or false based on success
        """
        group_dn = f"cn={username},{self._group_table()},{self._base_dn()}"
        user_dn = f"uid={username},{self._user_table()},{self._base_dn()}"

        with Connection(self.server, user=self.admin_user, password=self.admin_secret, auto_bind=True) as connection:
            success_user = connection.delete(user_dn)
            success_group = connection.delete(group_dn)
            return success_group and success_user

    def update_user(self, username, info):
        """
        Update user attributes to those specified in a new dictionary
        :param username: user name to update
        :param info: attribute dictionary containing new values
        :return:
        """
        user_dn = f"uid={username},{self._user_table()},{self._base_dn()}"
        user_record = {
            key: [(ldap3.MODIFY_REPLACE, [value])]
            for key, value in info.items()
        }
        with Connection(self.server, user=self.admin_user, password=self.admin_secret, auto_bind=True) as connection:
            return connection.modify(user_dn, user_record)

    def change_password(self, username, old_pwd, new_pwd):
        """
        Change the password for a user
        :param username: user name to change
        :param old_pwd: old password to bind with
        :param new_pwd: new password to change
        :return: True or False
        """
        user_dn = f"uid={username},{self._user_table()},{self._base_dn()}"
        user_record = {
            'userPassword': [(ldap3.MODIFY_REPLACE, [new_pwd])]
        }
        with Connection(self.server, user_dn, old_pwd, auto_bind=True) as connection:
            return connection.modify(user_dn, user_record)

    def set_password(self, username, new_pwd):
        """
        Change the password for a user
        :param username: user name to change
        :param new_pwd: new password to change
        :return: True or False
        """
        user_dn = f"uid={username},{self._user_table()},{self._base_dn()}"
        user_record = {
            'userPassword': [(ldap3.MODIFY_REPLACE, [new_pwd])]
        }
        with Connection(self.server, user=self.admin_user, password=self.admin_secret, auto_bind=True) as connection:
            return connection.modify(user_dn, user_record)

    def fetch_users(self, *user_names, full=False):
        """
        Fetch users
        :user_names:  names of users to find.
        :full: if True, return all attributes otherwise just uid and uidNumber, forced to True if user_names are provided
        :return: entries.
        """
        search_dn = f"{self._user_table()},{self._base_dn()}"
        if not user_names:
            search_filter = '(objectclass=posixAccount)'
        else:
            uid_filter = ''.join([f'(uid={name})' for name in user_names])
            search_filter = f'(&(objectclass=posixAccount)(|{uid_filter})'
        search_attrs = ['uid', 'uidNumber', 'objectclass'] if not full else USER_ATTRIBUTES
        with Connection(self.server, user=self.admin_user, password=self.admin_secret, auto_bind=True) as connection:
            connection.extend.standard.paged_search(search_dn, search_filter, attributes=search_attrs,
                                                    paged_size=PAGE_SIZE, generator=False)
            return connection.entries
