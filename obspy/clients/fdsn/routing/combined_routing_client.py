#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Routing client combining many different routers.

:copyright:
    The ObsPy Development Team (devs@obspy.org)
:license:
    GNU Lesser General Public License, Version 3
    (https://www.gnu.org/copyleft/lesser.html)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
from future.builtins import *  # NOQA

import collections
import copy

from obspy.core.compatibility import mock
from ..client import get_bulk_string
from ..header import FDSNNoDataException
from .routing_client import (
    BaseRoutingClient, _assert_attach_response_not_in_kwargs,
    _assert_filename_not_in_kwargs, _strip_protocol)
from .federator_routing_client import FederatorRoutingClient
from .eidaws_routing_client import EIDAWSRoutingClient


class CombinedRoutingClient(BaseRoutingClient):
    """
    Will combine information from many different routing clients.

    One possible issue with this is that it may return duplicate data. The
    routing services usually take care of this but this of course breaks
    down if multiple routers are involved. In practice this still works well
    though.
    """
    def __init__(self, routers=[FederatorRoutingClient, EIDAWSRoutingClient],
                 include_providers=None, exclude_providers=None,
                 debug=False, timeout=120):
        """
        Initialize a combined routers.

        Will route with all passed routers. Only the data from one router
        will be used per data center, whichever comes first will take
        precedence.

        All parameters except ``routers`` are passed on to the
        :class:`~obspy.clients.fdsn.routing.routing_clieng.BaseRoutingClient`
        parent class

        :param routers: The URL of the routing service.
        :type routers: List of routing classes or instances.
        """
        # Initialize all routers if types are given - otherwise just use the
        # initialized object.
        self.routers = [_i(include_providers=include_providers,
                           exclude_providers=exclude_providers, debug=debug,
                           timeout=timeout) if isinstance(_i, type) else _i
                        for _i in routers]
        BaseRoutingClient.__init__(self, debug=debug, timeout=timeout,
                                   include_providers=include_providers,
                                   exclude_providers=exclude_providers)

    def _combine_data(self, method_name, *args, **kwargs):
        this_args = copy.deepcopy(args)
        this_kwargs = copy.deepcopy(kwargs)
        routes = {}
        data_centers = []

        for router in self.routers:
            name = "%s.%s" % (router.__class__.__module__,
                              router.__class__.__name__)
            original_method = router._download_parallel
            def mocked_method(self, *args, **kwargs):
                if kwargs["data_type"] in method_name:
                    return None
                return original_method(*args, **kwargs)

            # Just use mock to patch out the function - this relies on some
            # internals but it is tested and thus should be fine.
            with mock.patch("%s._download_parallel" % name,
                            side_effect=mocked_method, autospec=True) as p:
                try:
                    getattr(router, method_name)(*this_args, **this_kwargs)
                # Might just not have data.
                except FDSNNoDataException:
                    continue
            if not p.call_count or len(p.call_args[0]) < 2:
                continue
            split = p.call_args[0][1]
            for key, value in split.items():
                url = _strip_protocol(key)
                if url in data_centers:
                    continue
                routes[key] = value
                data_centers.append(key)
                _kwargs = p.call_args[1]

        if not routes:
            raise FDSNNoDataException("")

        return self._download_parallel(split=routes, **_kwargs)

    @_assert_filename_not_in_kwargs
    @_assert_attach_response_not_in_kwargs
    def get_waveforms_bulk(self, bulk, **kwargs):
        """
        """
        return self._combine_data("get_waveforms_bulk", bulk=bulk, **kwargs)

    @_assert_filename_not_in_kwargs
    def get_stations(self, **kwargs):
        """
        """
        return self._combine_data("get_stations", **kwargs)

    @_assert_filename_not_in_kwargs
    def get_stations_bulk(self, bulk, **kwargs):
        """
        """
        return self._combine_data("get_stations_bulk", bulk=bulk, **kwargs)

    def get_service_version(self):
        """
        Return a semantic version number of the remote service as a string.
        """
        r = self._download(self._url + "/version")
        return r.content.decode() if \
            hasattr(r.content, "decode") else r.content


if __name__ == '__main__':  # pragma: no cover
    import doctest
    doctest.testmod(exclude_empty=True)
