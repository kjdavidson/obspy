#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mustang client for ObsPy.

:copyright:
    The ObsPy Development Team (devs@obspy.org)
:license:
    GNU Lesser General Public License, Version 3
    (http://www.gnu.org/copyleft/lesser.html)
"""
from __future__ import print_function
from __future__ import unicode_literals
from collections import defaultdict, namedtuple
from future import standard_library  # NOQA
from future.builtins import str
from future.utils import PY2, native_str
from obspy import UTCDateTime, read_inventory

def convert_to_string(value):
    """
    Takes any value and converts it to a string compliant with the FDSN
    webservices.

    Will raise a ValueError if the value could not be converted.

    >>> print(convert_to_string("abcd"))
    abcd
    >>> print(convert_to_string(1))
    1
    >>> print(convert_to_string(1.2))
    1.2
    >>> print(convert_to_string( \
              UTCDateTime(2012, 1, 2, 3, 4, 5, 666666)))
    2012-01-02T03:04:05.666666
    >>> print(convert_to_string(True))
    true
    >>> print(convert_to_string(False))
    false
    """
    if isinstance(value, (str, native_str)):
        return value
    # Boolean test must come before integer check!
    elif isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, float):
        return str(value)
    elif isinstance(value, UTCDateTime):
        return str(value).replace("Z", "")
    elif PY2 and isinstance(value, bytes):
        return value
    else:
        raise TypeError("Unexpected type %s" % repr(value))



QuerySelection = namedtuple("QuerySelection", ["name", "operation", "value"])


class MustangException(Exception):
    pass


class MustangQueryException(MustangException):
    pass


class MustangQueryFilter(object):
    def __init__(self, name=None, stack=None):
        self.name = name
        if stack is None:
            stack = []
        self.stack = stack

    def __and__(self, other):
        self.stack.extend(other.stack)
        return self

    def __operator__(self, other, operator):
        if self.name is None:
            raise MustangQueryException(
                "Cannot use comparison operator on unnamed query selector.")
        self.stack.append(QuerySelection(
            self.name, operator, convert_to_string(other)))
        return MustangQueryFilter(stack=self.stack)

    def __lt__(self, other):
        return self.__operator__(other, "<")

    def __le__(self, other):
        return self.__operator__(other, "<=")

    def __eq__(self, other):
        return self.__operator__(other, "==")

    def __ne__(self, other):
        return self.__operator__(other, "!=")

    def __gt__(self, other):
        return self.__operator__(other, ">")

    def __ge__(self, other):
        return self.__operator__(other, ">=")


class MustangClient(object):
    def __init__(self, base_url="http://service.iris.edu/mustangbeta"):
        self.base_url = base_url

    def __getattr__(self, item):
        return MustangQueryFilter(name=item)

    def query(self, network=None, station=None, location=None, channel=None,
              quality=None, starttime=None, endtime=None):
        return MustangQuery(base_url=self.base_url, network=network,
                            station=station, location=location,
                            channel=channel, quality=quality,
                            starttime=starttime, endtime=endtime)


class MustangQuery(object):
    def __init__(self, base_url, network=None, station=None, location=None,
                 channel=None, starttime=None, endtime=None, quality=None):
        self.base_url = base_url
        self.network = network
        self.station = station
        self.location = location
        self.channel = channel
        self.startime = starttime
        self.endtime = endtime
        self.quality = quality

        self._current_metric_name = None
        self._metric_queries = defaultdict(list)

    def metric(self, metric_name):
        self._current_metric_name = metric_name
        return self

    def filter(self, query_filter):
        if self._current_metric_name is None:
            msg = "Cannot apply filter when no metric is selected."
            raise MustangQueryException(msg)
        self._metric_queries[self._current_metric_name].extend(
            query_filter.stack)
        return self

    def get(self):
        """
        Actually download the chosen metrics.
        """
        from IPython.core.debugger import Tracer; Tracer(colors="Linux")()


m = MustangClient()


m.query(network="IU", station="ANMO", location="00", channel="BH1")\
    .metric("max_gaps").filter((m.value >= 2) & (m.value <= 3))\
    .metric("sample_snr_value").filter(m.value != "NULL")\
    .get()

from IPython.core.debugger import Tracer; Tracer(colors="Linux")()


if __name__ == '__main__':
    import doctest
    doctest.testmod(exclude_empty=True)
