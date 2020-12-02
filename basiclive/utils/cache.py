import hashlib


def make_key(key, key_prefix, version):
    hashed_key = hashlib.md5(key.encode("utf-8")).hexdigest()
    return f'{key_prefix}:{version}:{hashed_key}'

