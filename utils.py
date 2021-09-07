#coding: utf-8
import os
from datetime import datetime, timedelta
import weakref

from ConfigParser import SafeConfigParser


def _yyyymmdd_to_datetime(YYYYMMDD):
    try:
        return datetime(
            int(YYYYMMDD[:4]), int(YYYYMMDD[4:6]), int(YYYYMMDD[6:]))
    except:
        return None


def earlier_yyyymmdd(yyyymmdd=None, days=None):
    d0 = earlier_datetime(yyyymmdd, days)
    return d0.isoformat().replace("-", "")[:8]


def earlier_datetime(yyyymmdd=None, days=None):
    days = days or 30
    if isinstance(yyyymmdd, str):
        _date = _yyyymmdd_to_datetime(yyyymmdd)
    else:
        _date = datetime.now()
    return _date - timedelta(days=days)


class SingletonMixin(object):
    """
    Adds a singleton behaviour to an existing class.

    weakrefs are used in order to keep a low memory footprint.
    As a result, args and kwargs passed to classes initializers
    must be of weakly refereable types.
    """
    _instances = weakref.WeakValueDictionary()

    def __new__(cls, *args, **kwargs):
        key = (cls, args, tuple(kwargs.items()))

        if key in cls._instances:
            return cls._instances[key]

        new_instance = super(type(cls), cls).__new__(cls, *args, **kwargs)
        cls._instances[key] = new_instance

        return new_instance


class Configuration(SingletonMixin):
    """
    Acts as a proxy to the ConfigParser module
    """
    def __init__(self, fp, parser_dep=SafeConfigParser):
        self.conf = parser_dep()
        self.conf.readfp(fp)

    @classmethod
    def from_env(cls):
        try:
            filepath =  os.environ['EXPORTSCI_SETTINGS_FILE']
        except KeyError:
            raise ValueError('missing env variable EXPORTSCI_SETTINGS_FILE')

        return cls.from_file(filepath)

    @classmethod
    def from_file(cls, filepath):
        """
        Returns an instance of Configuration

        ``filepath`` is a text string.
        """
        fp = open(filepath, 'rb')
        return cls(fp)

    def __getattr__(self, attr):
        return getattr(self.conf, attr)

    def items(self):
        """Settings as key-value pair.
        """
        return [(section, dict(self.conf.items(section))) for \
            section in [section for section in self.conf.sections()]]