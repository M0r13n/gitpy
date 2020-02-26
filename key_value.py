import collections


class KeyValueStore(collections.OrderedDict):
    """
    Store key-value pairs.
    Instead of replacing existing entries they are transformed to a list and then appended.
    """

    def __setitem__(self, key, value):
        # duplicate entries are not overwritten but stored as a list
        if key in self:
            if isinstance(self[key], list):
                value = self[key] + [value]
            else:
                value = [self[key]] + [value]

        return super().__setitem__(key, value)

    @classmethod
    def from_data(cls, raw: bytes):
        """
        Parse a binary commit object.
        Format is a simplified version of RFC 2822.

        TODO:
        This works for valid commits. But I am not sure what happens on malformed data.
        """
        obj = cls()

        start = 0
        space = raw.find(b' ')
        end = space

        while end != -1:
            key = raw[start:end]  # key lies between the start and next space
            while True:  # get value
                end = raw.find(b'\n', end + 1)
                if end == -1:
                    value = raw[space + 1:len(raw)].replace(b'\n ', b'\n')
                    break

                elif raw[end + 1] != ord(' '):
                    # either the newline was followed by space or we reached the end of file
                    value = raw[space + 1:end].replace(b'\n ', b'\n')
                    break

            # remove leading spaces from multiline values
            obj[key] = value
            if end == -1:
                # we reached the end
                break
            start = end + 1
            space = raw.find(b' ', start)
            end = space

        return obj

    def serialize(self, binary=True):
        ret = b'\n'.join([x + b' ' + y.replace(b'\n', b'\n ') for (x, y) in self.items()])

        if not binary:
            return ret.decode()

        return ret
