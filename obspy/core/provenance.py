from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
from future.builtins import *  # NOQA

import json
import os
import uuid

import obspy


NS_PREFIX = "seis_prov"
NS_SEIS = (NS_PREFIX, "http://seisprov.org/seis_prov/0.1/#")

DEFINITION = os.path.join(os.path.dirname(__file__), "data",
                          "seis_prov_0_1.json")


import prov.model

_CACHE = {}


class SeisProvDocument(prov.model.ProvDocument):
    """
    SEIS-PROV document.
    """
    def plot(self):
        prov.model.ProvDocument.plot(self, use_labels=True)


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
        ("seis_prov:seed_id", trace.id),
        ("seis_prov:start_time",
         prov.model.Literal(trace.stats.starttime.datetime,
                            prov.constants.XSD_DATETIME)),
        ("seis_prov:number_of_samples",
         prov.model.Literal(trace.stats.npts,
                            prov.constants.XSD_INT)),
        ("seis_prov:sampling_rate",
         prov.model.Literal(trace.stats.sampling_rate,
                            prov.constants.XSD_DOUBLE)),
    ))


def create_prov_doc_for_trace(trace):
    # Create doc and default namespace.
    doc =  SeisProvDocument()
    doc.add_namespace(*NS_SEIS)

    entity = trace2prov_entity(doc, trace, step=1)

    return doc, str(entity.identifier)


def add_processing_step_to_prov(doc, prev_id, new_trace, info):
    # Find the entity with the previous id.
    rec = [_i for _i in doc._records if str(_i.identifier) == prev_id]
    if not rec:
        raise ValueError("Could not find the record of the entity representing"
                         "the previous state of the trace.")
    previous_entity = rec[0]

    # Parse the identifier to extract the previous step number.
    step = int(previous_entity.identifier.localpart.split("_")[0].strip("sp"))

    entity = trace2prov_entity(doc=doc, trace=new_trace, step=step + 2)

    activity = _create_activity(doc=doc, info=info, step=step+1)

    doc.usage(activity, previous_entity)
    doc.generation(entity, activity)

    return str(entity.identifier)


def get_record_for_id(doc, identifier):
    """
    Search the provenance document and return a record with the passed id.
    Raises a ValueError if it cannot find a record with the given id.

    :param doc: A provenance document
    :param identifier: The identifier to search for.
    """
    pass


def _extract_detrend(info):
    name = "detrend"
    attributes = {
        "detrending_method": str(info["arguments"]["type"])
    }
    return name, attributes


def _extract_taper(info):
    name = "taper"
    attributes = {
        "window_type": str(info["arguments"]["type"]),
        "taper_width": float(info["arguments"]["max_percentage"]),
        "side": str(info["arguments"]["side"])
    }
    return name, attributes


def _extract_filter(info):
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
        from IPython.core.debugger import Tracer; Tracer(colors="Linux")()
        raise NotImplementedError
    return name, attributes


# Map the function names to function actually converting the information.
FCT_MAP = {
    "detrend": _extract_detrend,
    "taper": _extract_taper,
    "filter": _extract_filter,
}


def _create_activity(doc, info, step):
    """
    This central function parses the info dictionary to a corresponding
    SEIS-PROV activity.

    :param doc: The provenance document to add the activity to.
    :param info: The info dictionary.

    :return: The newly created activity.
    """
    fct_name = info["function_name"]

    if fct_name not in FCT_MAP:
        raise NotImplementedError("Function %s" % fct_name)
    name, attributes = FCT_MAP[fct_name](info)

    definition = _get_definition_for_record(record_type="activity",
                                            name=name)
    identifier = _get_identifier(record_type="activity", name=name, step=step)

    other_attributes = {
        "prov:label": definition["label"],
        "prov:type": "%s:%s" % (NS_PREFIX, definition["type"])
    }

    for key, value in attributes.items():
        if isinstance(value, obspy.UTCDateTime):
            new_value = prov.model.Literal(value.datetime,
                                           prov.constants.XSD_DATETIME)
        elif isinstance(value, bytes):
            new_value= value.decode()
        else:
            new_value = value
        other_attributes["%s:%s" % (NS_PREFIX, key)] = new_value

    activity = doc.activity(identifier, other_attributes=other_attributes)

    # Associate with ObsPy as ObsPy did it.
    obspy_agent = _get_obspy_agent(doc)
    doc.association(activity, obspy_agent)

    return activity

