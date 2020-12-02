import os
import random
import string

import ldap3
from django.conf import settings
from django.core.mail import mail_managers
from ldap3 import Server, Connection

BASE_DN = getattr(settings, 'LDAP_BASE_DN', 'dc=demo1,dc=freeipa,dc=org')
SERVER_URI = getattr(settings, 'LDAP_SERVER_URI', 'ipa.demo1.freeipa.org')
MANAGER_DN = getattr(settings, 'LDAP_MANAGER_DN', None)
MANAGER_SECRET = getattr(settings, 'LDAP_MANAGER_SECRET', None)
USER_TABLE = getattr(settings, 'LDAP_USER_TABLE', 'ou=People')
USER_ROOT = getattr(settings, 'LDAP_USER_ROOT', '/home')
GROUP_TABLE = getattr(settings, 'LDAP_GROUP_TABLE', 'ou=Groups')
USER_SHELL = getattr(settings, 'LDAP_USER_SHELL', '/bin/bash')
EMAIL_NEW_ACCOUNTS = getattr(settings, 'LDAP_SEND_EMAILS', False)

USER_ATTRIBUTES = ['cn', 'uid', 'uidNumber', 'gidNumber', 'homeDirectory', 'loginShell', 'description', 'gecos',
                   'objectclass']
PAGE_SIZE = 1000


def uniquefy(name, existing):
    """
    Generate a unique name given the requested name and a list of existing names
    :param name: initial guess of name
    :param existing: list of existing names
    :return: a unique name based on the suggested name
    """
    root = (u'%s' % name).replace('-', '').replace(' ', '').strip().lower()
    choices = [root] + ['{}{}'.format(root, i) for i in range(1, 20)]
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
    """

    """
    vowels = ['a', 'e', 'i', 'o', 'u']
    consonants = [a for a in string.ascii_lowercase if a not in vowels]
    digits = string.digits

    ####utility functions
    def a_part(slen):
        ret = ''
        for i in range(int(slen)):
            if i % 2 == 0:
                randid = random.randint(0, 20)  # number of consonants
                ret += consonants[randid]
            else:
                randid = random.randint(0, 4)  # number of vowels
                ret += vowels[randid]
        ret = ''.join([random.choice([k, k, k, k.upper()]) for k in ret])
        return ret

    def n_part(slen):
        ret = ''
        for i in range(int(slen)):
            randid = random.randint(0, 9)  # number of digits
            ret += digits[randid]
        return ret

    ####
    fpl = alpha / 2
    if alpha % 2:
        fpl = int(alpha / 2) + 1
    lpl = alpha - fpl

    start = a_part(fpl)
    mid = n_part(numeric)
    end = a_part(lpl)

    return "{}{}{}".format(start, mid, end)


class Directory(object):
    """
    A Directory manager implementing methods for listing and modifying a directory
    """

    def __init__(self, uri=SERVER_URI, user=MANAGER_DN, secret=MANAGER_SECRET, use_ssl=True):
        """
        :param uri: Server URI
        :param user: user name to bind or None for anonymous bind
        :param secret: password to bind or None for anonymous.
        :param use_ssl: whether to use SSL or not. Default True.
        """
        self.admin_user = user
        self.admin_secret = secret
        self.server = Server(uri, use_ssl=use_ssl, get_info=ldap3.ALL)

    def add_user(self, info):
        """
        Add a user entry
        :param info:
        :return: dictionary of new user information
        """

        users = {user['uid'].value: user['uidNumber'].value for user in self.fetch_users()}
        uidNumber = gidNumber = max(list(users.values())) + 1
        if not info.get('username', '').strip():
            info['username'] = uniquefy(info['last_name'], list(users.keys()))
        if not info.get('password', '').strip():
            info['password'] = pwd_generator()

        # Create group
        group_dn = 'cn={username},{group_table},{base_dn}'.format(
            username=info['username'], group_table=GROUP_TABLE, base_dn=BASE_DN
        )
        group_object_classes = ['top', 'groupOfUniqueNames', 'posixGroup']
        group_record = {
            'cn': info['username'],
            'gidNumber': gidNumber,
            'memberUid': info['username'],
            'objectClass': group_object_classes,
        }

        # Create user
        user_dn = 'uid={username},{user_table},{base_dn}'.format(
            username=info['username'], user_table=USER_TABLE, base_dn=BASE_DN
        )
        user_object_classes = ['top', 'account', 'posixAccount', 'shadowAccount']
        user_record = {
            'cn': info['username'],
            'uid': info['username'],
            'gecos': '{first_name} {last_name}'.format(**info),
            'homeDirectory': os.path.join(USER_ROOT, info['username']),
            'loginShell': USER_SHELL,
            'uidNumber': uidNumber,
            'gidNumber': gidNumber,
            'objectClass': user_object_classes,
            'userPassword': info['password'],
        }
        with Connection(self.server, user=self.admin_user, password=self.admin_secret, auto_bind=True) as connection:
            group_success = connection.add(group_dn, group_object_classes, group_record)
            user_success = connection.add(user_dn, user_object_classes, user_record)

        if user_success and group_success and EMAIL_NEW_ACCOUNTS:
            mail_managers(
                "New Account -  {first_name} {last_name}".format(**info),
                ("A new account has been created \n"
                 "-------------------------------\n"
                 " Full Name: {first_name} {last_name}\n"
                 " Login: {username}\n"
                 " Password: {password}\n"
                 "-------------------------------\n").format(**info)
            )

        del info['password']  # remove password from dictionary before returning
        return info

    def add_group_member(self, group, user):
        """
        Add a user to a group
        :param group: group name
        :param user: user name
        :return: True if successful
        """
        group_dn = 'cn={group},{group_table},{base_dn}'.format(
            group=group, group_table=GROUP_TABLE, base_dn=BASE_DN
        )
        with Connection(self.server, user=self.admin_user, password=self.admin_secret, auto_bind=True) as connection:
            return connection.modify(group_dn, {'memberUid': [(ldap3.MODIFY_ADD, [user])]})

    def delete_user(self, username):
        """
        Delete a user entry
        :param username: username of user to delete
        :return: True or false based on success
        """
        group_dn = 'cn={group},{group_table},{base_dn}'.format(
            group=username, group_table=GROUP_TABLE, base_dn=BASE_DN
        )
        user_dn = 'uid={username},{user_table},{base_dn}'.format(
            username=username, user_table=USER_TABLE, base_dn=BASE_DN
        )

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

        user_dn = 'uid={username},{user_table},{base_dn}'.format(
            username=username, user_table=USER_TABLE, base_dn=BASE_DN
        )

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

        user_dn = 'uid={username},{user_table},{base_dn}'.format(
            username=username, user_table=USER_TABLE, base_dn=BASE_DN
        )
        user_record = {
            'userPassword': [(ldap3.MODIFY_REPLACE, [new_pwd])]
        }
        with Connection(self.server, user_dn, old_pwd, auto_bind=True) as connection:
            return connection.modify(user_dn, user_record)

    def fetch_users(self, *user_names, full=False):
        """
        Fetch users
        :user_names:  names of users to find.
        :full: if True, return all attributes otherwise just uid and uidNumber, forced to True if user_names are provided
        :return: entries.
        """
        search_dn = '{user_table},{base_dn}'.format(
            user_table=USER_TABLE, base_dn=BASE_DN
        )
        if not user_names:
            search_filter = '(objectclass=posixAccount)'
        else:
            uid_filter = ''.join(['(uid={})'.format(name) for name in user_names])
            search_filter = '(&(objectclass=posixAccount)(|{})'.format(uid_filter)
        search_attrs = ['uid', 'uidNumber', 'objectclass'] if not full else USER_ATTRIBUTES
        with Connection(self.server, user=self.admin_user, password=self.admin_secret, auto_bind=True) as connection:
            connection.extend.standard.paged_search(search_dn, search_filter, attributes=search_attrs,
                                                    paged_size=PAGE_SIZE, generator=False)
            return connection.entries
