
class MultiKeyDict(object):
    """
    Convert a dictionary with tuple keys into one that can use any of the tuple values as a key
    """
    def __init__(self, source):
        self.items_dict = source
        self.access_dict = {
            key: keys
            for keys in source.keys()
            for key in keys
        }

    def __getitem__(self, key):
        """
        Return value for given key
        :param key: a unique key element
        :return: value
        """
        if isinstance(key, (tuple,)):
            for k in key:
                if k in self:
                    return self.items_dict[self.access_dict[k]]
            raise KeyError('{}'.format(key))
        else:
            return self.items_dict[self.access_dict[key]]

    def __setitem__(self, keys, value):
        if isinstance(keys, (tuple,)):
            if keys in self:
                # some of keys exist, update key tuple and value
                old_keys = next((self.access_dict[k] for k in keys if k in self.access_dict))
                new_keys = tuple(set(keys) | set(old_keys))
            else:
                # entirely new tuple
                new_keys = keys
            self.items_dict[new_keys] = value
            self.access_dict.update({
                key: new_keys
                for key in new_keys
            })
        else:
            if keys in self:
                # single value of tuple which exists, simply update value
                self.items_dict[self.access_dict[keys]] = value
            else:
                # entirely new key, create one-tuple for it
                new_keys = (keys,)
                self.access_dict[keys] = new_keys
                self.items_dict[new_keys] = value

    def __delitem__(self, key):
        """
        Called to implement deletion of self[key].
        """

        if key in self.access_dict:
            keys = self.access_dict[key]
            value = self.items_dict[keys]
            new_keys = tuple(set(keys) - {key})
            del self.items_dict[keys]
            del self.access_dict[key]
            if new_keys:
                self.items_dict[new_keys] = value

    def __contains__(self, key):
        if isinstance(key, (tuple,)):
            return any(k in self.access_dict for k in key)
        return key in self.access_dict

    def has_key(self, key):
        return key in self

    def items(self, raw=True):
        if raw:
            return self.items_dict.items()
        else:
            return ((k, self.access_dict[keys]) for k, keys in self.access_dict.items())

    def keys(self, raw=True):
        if raw:
            return self.items_dict.keys()
        else:
            return self.access_dict.keys()

    def values(self, raw=True):
        if raw:
            return self.items_dict.values()
        else:
            return (self.access_dict[keys] for k, keys in self.access_dict.items())

    def __len__(self):
        return len(self.items_dict)

    def get(self, key, default=None):
        if key in self:
            return self[key]
        else:
            return default

    def __str__(self):
        return str(self.items_dict)