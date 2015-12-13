# -*- coding: utf-8 -*-
"""
Module to track and store provenance for ObsPy waveform objects.

:copyright:
    The ObsPy Development Team (devs@obspy.org)
:license:
    GNU Lesser General Public License, Version 3
    (http://www.gnu.org/copyleft/lesser.html)


This module attempts to automatically track the data provenance for
:class:`~obspy.core.trace.Trace` objects.

.. rubric:: Caveats

1. It only works for the :class:`~obspy.core.stream.Stream` and
   :class:`~obspy.core.trace.Trace` methods included in ObsPy. External methods
   might works but that depends on the specific implementation.
2. Methods that return/work on views of the data, e.g.
   :meth:`obspy.core.trace.Trace.slice`, have valid provenance immediately
   after the operation. Afterwards there are multiple
   :class:`~obspy.core.trace.Trace` objects that might contain the same data
   but the provenance might diverge and thus no longer be valid.
3. Direct manipulations of the data array are also not captured.

If you feel like it does not capture something it really should, please
contact the ObsPy developers.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
from future.builtins import *  # NOQA

from copy import copy
import io
import json
import os
import uuid

import prov.model

import obspy


NS_PREFIX = "seis_prov"
NS_SEIS = (NS_PREFIX, "http://seisprov.org/seis_prov/0.1/#")

DEFINITION = os.path.join(os.path.dirname(__file__), "data",
                          "seis_prov_0_1.json")


_CACHE = {}


class SeisProvValidationError(Exception):
    pass


class SeisProvDocument(prov.model.ProvDocument):
    """
    SEIS-PROV document.
    """
    def plot(self):
        prov.model.ProvDocument.plot(self, use_labels=True)

    def validate(self):
        """
        Validate the SEIS-PROV document. Currently uses the official
        seis-prov validator.
        """
        from seis_prov_validate import validate  # NOQA

        with io.BytesIO() as fh:
            self.serialize(fh, format="xml")
            fh.seek(0, 0)
            result = validate(fh)
        if not result.is_valid:
            if result.warnings:
                msg = "Warnings:\n" + ", ".join(result.warnings) + "\n"
            else:
                msg = ""

            msg += "Errors:\n" + ", ".join(result.errors)

            raise SeisProvValidationError(msg)


def _get_definition():
    """
    Helper to not have to load it upon import.
    """
    if "definition" not in _CACHE:
        with open(DEFINITION, "rt") as fh:
            _CACHE["definition"] = json.load(fh)
    return _CACHE["definition"]


def _get_definition_for_record(record_type, name):
    rec_type_map = {
        "activity": "activities",
        "entity": "entities",
        "agent": "agents"
    }

    return _get_definition()[rec_type_map[record_type]][name]


def _get_identifier(record_type, name, step):
    """
    Get the identifier for a provenance record.

    :param record_type: The record type. One of "agent", "activity", "entity".
    :param name: The name of the record in the SEIS-PROV definition.
    :param step: The step number. Used to give successive ids.
    """
    definition = _get_definition_for_record(record_type=record_type,
                                            name=name)
    # Twelve digits of a uuid should be unique enough.
    return "%s:sp%05i_%s_%s" % (NS_PREFIX, step,
                                definition["two_letter_code"],
                                uuid.uuid4().hex[:12])


def _get_obspy_agent(doc):
    """
    Return an agent representing ObsPy. This will be cached so its always the
    same for a single run of ObsPy but that is precisely what one wants.
    """
    # First try to find one in the existing doc.
    agents = [_i for _i in doc._records if isinstance(_i,
                                                      prov.model.ProvAgent)]
    for agent in agents:
        # A bit fuzzy in the way it deals with namespaces but it should be
        # safe enough.
        attribs = {k.localpart: v for k, v in agent.extra_attributes}

        if "type" not in attribs or \
                attribs["type"].localpart != "SoftwareAgent":
            continue
        elif "label" not in attribs or attribs["label"] != "ObsPy":
            continue
        elif "software_name" not in attribs or \
                attribs["software_name"] != "ObsPy":
            continue
        elif "software_version" not in attribs or \
                attribs["software_version"] != obspy.__version__:
            continue
        return agent

    identifier = _get_identifier(record_type="agent", name="software_agent",
                                 step=0)

    obspy_agent = doc.agent(identifier, other_attributes=(
        ("prov:type",
            prov.identifier.QualifiedName(prov.constants.PROV,
                                          "SoftwareAgent")),
        ("prov:label", "ObsPy"),
        ("seis_prov:software_name", "ObsPy"),
        ("seis_prov:software_version", obspy.__version__),
        ("seis_prov:website", "http://www.obspy.org"),
        ("seis_prov:doi", "10.1785/gssrl.81.3.530")))
    return obspy_agent


def trace2prov_entity(doc, trace, step=0):
    """
    Converts a trace object to a waveform trace entity.

    :param doc: The provenance document to attach the entity to.
    :param trace: The trace.
    :type trace: :class:`~obspy.core.trace.Trace`
    :param step: The step in the processing chain.

    :return: The created entity.
    """
    identifier = _get_identifier(record_type="entity",
                                 name="waveform_trace",
                                 step=step)
    return doc.entity(identifier, other_attributes=(
        ("prov:label", "Waveform Trace"),
        ("prov:type", "seis_prov:waveform_trace"),
        ("seis_prov:seed_id", trace["id"]),
        ("seis_prov:start_time",
         prov.model.Literal(trace["starttime"].datetime,
                            prov.constants.XSD_DATETIME)),
        ("seis_prov:number_of_samples",
         prov.model.Literal(trace["npts"],
                            prov.constants.XSD_INT)),
        ("seis_prov:sampling_rate",
         prov.model.Literal(trace["sampling_rate"],
                            prov.constants.XSD_DOUBLE)),
    ))


def create_prov_doc_for_trace(trace):
    # Create doc and default namespace.
    doc = SeisProvDocument()
    doc.add_namespace(*NS_SEIS)

    entity = trace2prov_entity(
        doc,
        {"id": trace.id,
         "npts": trace.stats.npts,
         "starttime": copy(trace.stats.starttime),
         "endtime": copy(trace.stats.endtime),
         "sampling_rate": trace.stats.sampling_rate},
        step=1)

    return doc, str(entity.identifier)


def add_processing_step_to_prov(doc, prev_id, state_before, state_after,
                                info):
    # Find the entity with the previous id.
    rec = [_i for _i in doc._records if str(_i.identifier) == prev_id]
    if not rec:
        raise ValueError("Could not find the record of the entity representing"
                         " the previous state of the trace.")

    return _create_activites(doc=doc, info=info, previous_entity=rec[0],
                             state_before=state_before,
                             state_after=state_after)


def get_record_for_id(doc, identifier):
    """
    Search the provenance document and return a record with the passed id.
    Raises a ValueError if it cannot find a record with the given id.

    :param doc: A provenance document
    :param identifier: The identifier to search for.
    """
    pass


def _extract_detrend(info, state_before, state_after):
    name = "detrend"
    method = str(info["arguments"]["type"])

    # Make sure the method is allowed.
    if method not in ("simple", "linear", "demean", "constant",
                      "polynomial", "spline"):
        raise NotImplementedError("Provenance tracking for the detrending "
                                  "method '%s' is not yet implemented." % (
                                      method))

    attributes = {}

    # Special case handling for some methods.
    if method == "constant":
        method = "demean"
    elif method == "linear":
        method = "linear fit"
    elif method == "polynomial":
        method = "polynomial fit"
        attributes["polynomial_order"] = info["arguments"]["options"]["order"]
    elif method == "spline":
        method = "spline fit"
        attributes["spline_degree"] = info["arguments"]["options"]["order"]
        attributes["distance_between_spline_nodes_in_samples"] = \
            info["arguments"]["options"]["dspline"]

    attributes["detrending_method"] = method

    return [(name, attributes, state_after)]


def _extract_trim(info, state_before, state_after):
    steps = []
    # This can potentially generate two separate activities: one cutting
    # activity and one padding activity.

    if state_before["starttime"] < state_after["starttime"] or \
            state_before["endtime"] > state_after["endtime"]:
        state = copy(state_before)
        state["starttime"] = max(state_after["starttime"],
                                 state_before["starttime"])
        state["endtime"] = min(state_after["endtime"],
                               state_before["endtime"])
        attributes = {
            "new_start_time": state["starttime"],
            "new_end_time": state["endtime"]
        }
        steps.append(("cut", attributes, state))

    if state_before["starttime"] > state_after["starttime"] or \
            state_before["endtime"] < state_after["endtime"]:
        state = copy(state_before)
        state["starttime"] = state_after["starttime"]
        state["endtime"] = state_after["endtime"]

        attributes = {
            "new_start_time": state["starttime"],
            "new_end_time": state["endtime"],
            "fill_value": info["arguments"]["fill_value"]
        }
        steps.append(("pad", attributes, state))

    return steps


def _extract_taper(info, state_before, state_after):
    name = "taper"
    attributes = {
        "window_type": str(info["arguments"]["type"]),
        "taper_width": float(info["arguments"]["max_percentage"]),
        "side": str(info["arguments"]["side"])
    }
    return [(name, attributes, state_after)]


def _extract_differentiate(info, state_before, state_after):
    name = "differentiate"

    method = info["arguments"]["method"].lower()

    if method == "gradient":
        method = "second order central differences"
    else:
        raise NotImplementedError("Method '%s' not known to the provenance "
                                  "tracker for the trace differentiation." %
                                  method)

    attributes = {
        "differentiation_method": method,
        # Always first order.
        "order": 1
    }
    return [(name, attributes, state_after)]


def _extract_integrate(info, state_before, state_after):
    name = "integrate"

    method = info["arguments"]["method"].lower()

    if method == "cumtrapz":
        method = "trapezoidal rule"
        extra_args = {}
    elif method == "spline":
        method = "interpolating spline"
        extra_args = {"spline_degree": int(info["arguments"]["options"]["k"])}
    else:
        raise NotImplementedError("Method '%s' not known to the provenance "
                                  "tracker for the trace integration." %
                                  method)

    attributes = {
        "integration_method": method,
        # Always first order.
        "order": 1
    }
    attributes.update(extra_args)

    return [(name, attributes, state_after)]


def _extract_filter(info, state_before, state_after):
    attributes = {}

    filter_type = info["arguments"]["type"].lower()
    if filter_type == "bandpass":
        name = "bandpass_filter"
        attributes["filter_type"] = "Butterworth"
        attributes["lower_corner_frequency"] = \
            float(info["arguments"]["options"]["freqmin"])
        attributes["upper_corner_frequency"] = \
            float(info["arguments"]["options"]["freqmax"])
        if "corners" in info["arguments"]["options"]:
            attributes["filter_order"] = \
                int(info["arguments"]["options"]["freqmin"])
        else:
            # Hardcoded in ObsPy! Extract it somehow?
            attributes["filter_order"] = 4
    else:
        raise NotImplementedError
    return [(name, attributes, state_after)]


def _extract_normalize(info, state_before, state_after):
    name = "normalize"
    attributes = {
        "normalization_method": "amplitude"
    }
    return [(name, attributes, state_after)]


def _extract_multiply(info, state_before, state_after):
    name = "multiply"
    attributes = {
        "factor": info["arguments"]["factor"]
    }
    return [(name, attributes, state_after)]


def _extract_divide(info, state_before, state_after):
    name = "divide"
    attributes = {
        "divisor": info["arguments"]["factor"]
    }
    return [(name, attributes, state_after)]


# Map the function names to function actually converting the information.
FCT_MAP = {
    "detrend": _extract_detrend,
    "taper": _extract_taper,
    "filter": _extract_filter,
    "trim": _extract_trim,
    "differentiate": _extract_differentiate,
    "integrate": _extract_integrate,
    "normalize": _extract_normalize,
    "multiply": _extract_multiply,
    "divide": _extract_divide
}


def _create_activites(doc, info, previous_entity, state_before, state_after):
    """
    This central function parses the info dictionary to a corresponding
    SEIS-PROV activity.

    :param doc: The provenance document to add the activity to.
    :param info: The info dictionary.
    :param step: The sequential step number.
    :param state_before: The Trace's state before the activity has acted.
    :param state_after: The Trace's state after the activity has acted.

    :return: The newly created activity.
    """
    fct_name = info["function_name"]

    if fct_name not in FCT_MAP:
        raise NotImplementedError("Function %s" % fct_name)

    # Parse the identifier to extract the previous step number.
    step = int(previous_entity.identifier.localpart.split("_")[0].strip("sp"))
    step += 1

    items = FCT_MAP[fct_name](info, state_before, state_after)
    # Operations might end up no-ops in which case no provenance should be
    # recorded as nothing changed the data.
    if not items:
        return str(previous_entity.identifier)

    for name, attributes, state in items:
        definition = _get_definition_for_record(record_type="activity",
                                                name=name)
        identifier = _get_identifier(record_type="activity", name=name,
                                     step=step)

        other_attributes = {
            "prov:label": definition["label"],
            "prov:type": "%s:%s" % (NS_PREFIX, name)
        }

        for key, value in attributes.items():
            if isinstance(value, obspy.UTCDateTime):
                new_value = prov.model.Literal(value.datetime,
                                               prov.constants.XSD_DATETIME)
            elif isinstance(value, bytes):
                new_value = value.decode()
            else:
                new_value = value
            other_attributes["%s:%s" % (NS_PREFIX, key)] = new_value

        activity = doc.activity(identifier, other_attributes=other_attributes)

        # Associate with ObsPy as ObsPy did it.
        obspy_agent = _get_obspy_agent(doc)
        doc.association(activity, obspy_agent)

        step += 1
        entity = trace2prov_entity(doc=doc, trace=state_after, step=step)
        step += 1

        doc.usage(activity, previous_entity)
        doc.generation(entity, activity)

    return str(entity.identifier)
