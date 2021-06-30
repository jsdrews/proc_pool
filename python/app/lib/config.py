import os
import json


class ConfigError(Exception):
    pass


class ConfigFormatError(ConfigError):
    pass


class KeyNotAvailableError(ConfigError):
    pass


class Struct(object):

    __slots__ = (
        '_parent_key'
    )

    def __init__(self, **kwargs):
        self._parent_key = self.__class__.__name__
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        return '{}{}'.format(self._parent_key, self.__slots__)

    def __setattr__(self, key, value):
        try:
            if isinstance(value, dict):
                class SubStruct(Struct):
                    __slots__ = tuple(value.keys())

                setattr(self, key, SubStruct(_parent_key=key, **value))
            else:
                super(Struct, self).__setattr__(key, value)
        except (AttributeError, RecursionError):
            pass

    def __getattr__(self, item):
        try:
            return super(Struct, self).__getattribute__(item)
        except AttributeError:
            if self._parent_key == 'endpoints':
                raise KeyNotAvailableError('Endpoint: "{}" is not available\nAvailable Endpoints:\n'
                                           '{}'.format(item, '\n'.join(self.values)))
            return None

    @property
    def dict(self):
        tmp = {}
        for k in self.__slots__:
            v = getattr(self, k)
            if isinstance(v, Struct):
                tmp[k] = v.dict
            else:
                tmp[k] = v
        return tmp

    @property
    def keys(self):
        return self.__slots__

    @property
    def values(self):
        return [getattr(self, x) for x in self.keys]


class Config(object):

    @staticmethod
    def load(path=os.getenv('PROC_POOL_CONFIG')):

        assert path, "Config must be passed either a path or the PROC_POOL_CONFIG variable must be set"
        assert os.path.exists(path), "\'{}\' does not exist locally".format(path)

        with open(path, 'rb') as f:
            try:
                config = json.loads(f.read())
            except AttributeError:
                raise ConfigFormatError('Check the formatting of {}'.format(path))

        return Config.__struct(config)

    @staticmethod
    def __struct(d):

        class ConfigStruct(Struct):
            __slots__ = tuple(d.keys())

        return ConfigStruct(**d)
