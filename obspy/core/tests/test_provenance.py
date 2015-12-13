# -*- coding: utf-8 -*-
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
from future.builtins import *  # NOQA

import unittest

import prov.model

import obspy


class ProvenanceTestCase(unittest.TestCase):
    """
    Test suite for the provenance handling in ObsPy.
    """
    def _filter_records_label(self, doc, label):
        """
        Filter all records to only return those with the given label.
        """
        return [_i for _i in doc._records if _i.label == label]

    def _filter_records_type(self, doc, type):
        type_map = {
            "usage": prov.model.PROV_USAGE,
            "generation": prov.model.PROV_GENERATION,
            "agent": prov.model.PROV_AGENT
        }
        return [_i for _i in doc._records if _i.get_type() == type_map[type]]

    def _get_record_with_id(self, doc, identifier):
        return [_i for _i in doc._records
                if _i.identifier and _i.identifier.localpart == identifier][0]

    def _map_attributes(self, record):
        """
        Map the attributes of a record to a dictionary that is much simpler
        to test.
        """
        return {name.localpart: (value.localpart if hasattr(value, "localpart")
                                 else value)
                for (name, value) in record.attributes}

    def _assert_has_obspy_agent(self, doc):
        """
        Asserts that the document has an ObsPy agent and that it is correct
        and as expected.
        """
        agents = self._filter_records_type(doc, "agent")
        obspy_agent = [_i for _i in agents if _i.label == "ObsPy"]
        self.assertTrue(len(obspy_agent) == 1)
        attrs = self._map_attributes(obspy_agent[0])
        self.assertEqual(attrs, {
            'website': 'http://www.obspy.org',
            'doi': '10.1785/gssrl.81.3.530',
            'software_version': obspy.__version__,
            'type': 'SoftwareAgent',
            'software_name': 'ObsPy',
            'label': 'ObsPy'})

    def _assert_activity_sequence(self, doc, first_label, second_label):
        """
        Asserts that activities happen in sequence.

        Can currently only assert this for fully linear sequences.
        """
        first = self._filter_records_label(doc, first_label)
        second = self._filter_records_label(doc, second_label)

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)

        first = first[0]

        # The initial activity generates an entity. Find that.
        entity = self._map_attributes([
            _i for _i in self._filter_records_type(doc, "generation")
            if self._map_attributes(_i)["activity"] ==
            first.identifier.localpart][0])["entity"]
        # That entity is again used by some activity. Find it.
        activity = self._map_attributes([
            _i for _i in self._filter_records_type(doc, "usage")
            if self._map_attributes(_i)["entity"] == entity][0])["activity"]

        # Find the record for that activity. It should be identifical to the
        # label of the second activity.
        activity = self._get_record_with_id(doc, activity)

        self.assertEqual(activity.label, second_label)

    def test_simple_processing_chain(self):
        """
        Tests a very simple processing chain.
        """
        tr = obspy.read()[0]
        tr.detrend("linear")
        tr.taper(0.05)
        tr.filter("bandpass", freqmin=0.1, freqmax=1.0)

        tr.stats.provenance.validate()

        # Make sure it has all the required records.
        self._assert_has_obspy_agent(tr.stats.provenance)

        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr.stats.provenance, "Detrend")[0]), {
                'label': 'Detrend',
                'detrending_method': 'linear fit',
                'type': 'seis_prov:detrend'})

        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr.stats.provenance, "Taper")[0]), {
                'label': 'Taper',
                'side': 'both',
                'taper_width': 0.05,
                'window_type': 'hann',
                'type': 'seis_prov:taper'})

        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr.stats.provenance, "Bandpass Filter")[0]), {
                'label': 'Bandpass Filter',
                'filter_type': 'Butterworth',
                'filter_order': 4,
                'lower_corner_frequency': 0.1,
                'upper_corner_frequency': 1.0,
                'type': 'seis_prov:bandpass_filter'})

        self._assert_activity_sequence(tr.stats.provenance,
                                       "Detrend", "Taper")
        self._assert_activity_sequence(tr.stats.provenance,
                                       "Taper", "Bandpass Filter")

    def test_trimming(self):
        """
        Test provenance tracking of a trimming operation.
        """
        tr = obspy.read()[0]
        tr.stats.starttime = obspy.UTCDateTime(10)
        tr.stats.sampling_rate = 1.0

        # This will only cut.
        tr_a = tr.copy().trim(starttime=obspy.UTCDateTime(20))
        tr_a.stats.provenance.validate()
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Cut")[0]), {
                'label': 'Cut',
                'new_start_time': obspy.UTCDateTime(20).datetime,
                'new_end_time': tr.stats.endtime.datetime,
                'type': 'seis_prov:cut'})
        self.assertEqual(
            self._filter_records_label(tr_a.stats.provenance, "Pad"), [])

        # Will only pad.
        tr_a = tr.copy().trim(starttime=obspy.UTCDateTime(0),
                              endtime=obspy.UTCDateTime(5000),
                              pad=True, fill_value=1.0)
        tr_a.stats.provenance.validate()
        self.assertEqual(
            self._filter_records_label(tr_a.stats.provenance, "Cut"), [])
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Pad")[0]), {
                'label': 'Pad',
                'new_start_time': obspy.UTCDateTime(0).datetime,
                'new_end_time': obspy.UTCDateTime(5000).datetime,
                'fill_value': 1.0,
                'type': 'seis_prov:pad'})

        # Will do both. The internal implementation will always first cut
        # and then pad but it does not really matter for the end results.
        tr_a = tr.copy().trim(starttime=obspy.UTCDateTime(20),
                              endtime=obspy.UTCDateTime(5000),
                              pad=True, fill_value=10.0)
        tr_a.stats.provenance.validate()
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Cut")[0]), {
                'label': 'Cut',
                'new_start_time': obspy.UTCDateTime(20).datetime,
                'new_end_time': obspy.UTCDateTime(3009).datetime,
                'type': 'seis_prov:cut'})
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Pad")[0]), {
                'label': 'Pad',
                'new_start_time': obspy.UTCDateTime(20).datetime,
                'new_end_time': obspy.UTCDateTime(5000).datetime,
                'fill_value': 10.0,
                'type': 'seis_prov:pad'})
        # Another variant of the same thing.
        tr_a = tr.copy().trim(starttime=obspy.UTCDateTime(0),
                              endtime=obspy.UTCDateTime(50),
                              pad=True, fill_value=12.0)
        tr_a.stats.provenance.validate()
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Cut")[0]), {
                'label': 'Cut',
                'new_start_time': obspy.UTCDateTime(10).datetime,
                'new_end_time': obspy.UTCDateTime(50).datetime,
                'type': 'seis_prov:cut'})
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Pad")[0]), {
                'label': 'Pad',
                'new_start_time': obspy.UTCDateTime(0).datetime,
                'new_end_time': obspy.UTCDateTime(50).datetime,
                'fill_value': 12.0,
                'type': 'seis_prov:pad'})

        # Also nothing might be recorded if the operation did not do anything.
        tr_a = tr.copy().trim(starttime=obspy.UTCDateTime(0),
                              endtime=obspy.UTCDateTime(5000),
                              pad=False)
        tr_a.stats.provenance.validate()
        self.assertEqual(
            self._filter_records_label(tr_a.stats.provenance, "Cut"), [])
        self.assertEqual(
            self._filter_records_label(tr_a.stats.provenance, "Pad"), [])

    def test_slicing(self):
        """
        Tests the slicing of trace objects. This is very similar to trimming
        but it does not generate a copy but only a view. The provenance will
        be a copy though.
        """
        tr = obspy.read()[0]
        tr.stats.starttime = obspy.UTCDateTime(10)
        tr.stats.sampling_rate = 1.0

        # This will only cut.
        tr_a = tr.copy().slice(starttime=obspy.UTCDateTime(20))
        tr_a.stats.provenance.validate()
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Cut")[0]), {
                'label': 'Cut',
                'new_start_time': obspy.UTCDateTime(20).datetime,
                'new_end_time': tr.stats.endtime.datetime,
                'type': 'seis_prov:cut'})
        # Slicing cannot pad.
        self.assertEqual(
            self._filter_records_label(tr_a.stats.provenance, "Pad"), [])

        # Will do both. The internal implementation will always first cut
        # and then pad but it does not really matter for the end results.
        tr_a = tr.copy().slice(starttime=obspy.UTCDateTime(20),
                               endtime=obspy.UTCDateTime(5000))
        tr_a.stats.provenance.validate()
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Cut")[0]), {
                'label': 'Cut',
                'new_start_time': obspy.UTCDateTime(20).datetime,
                'new_end_time': obspy.UTCDateTime(3009).datetime,
                'type': 'seis_prov:cut'})
        # Slicing cannot pad.
        self.assertEqual(
            self._filter_records_label(tr_a.stats.provenance, "Pad"), [])

        # Another variant of the same thing.
        tr_a = tr.copy().slice(starttime=obspy.UTCDateTime(0),
                               endtime=obspy.UTCDateTime(50))
        tr_a.stats.provenance.validate()
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Cut")[0]), {
                'label': 'Cut',
                'new_start_time': obspy.UTCDateTime(10).datetime,
                'new_end_time': obspy.UTCDateTime(50).datetime,
                'type': 'seis_prov:cut'})
        # Slicing cannot pad.
        self.assertEqual(
            self._filter_records_label(tr_a.stats.provenance, "Pad"), [])

        # Also nothing might be recorded if the operation did not do anything.
        tr_a = tr.copy().slice(starttime=obspy.UTCDateTime(0),
                               endtime=obspy.UTCDateTime(5000))
        tr_a.stats.provenance.validate()
        self.assertEqual(
            self._filter_records_label(tr_a.stats.provenance, "Cut"), [])
        self.assertEqual(
            self._filter_records_label(tr_a.stats.provenance, "Pad"), [])

        # Trim once to generate some initial provenance.
        tr2 = tr.copy().trim(starttime=obspy.UTCDateTime(15))
        tr2.stats.provenance.validate()
        # Slice.
        tr_a = tr2.slice(starttime=obspy.UTCDateTime(20))
        tr_a.stats.provenance.validate()

        # Make sure the resulting provenance is a different object.
        self.assertFalse(tr2.stats.provenance is tr_a.stats.provenance)
        # The first trace has only one cutting record, the second two.
        self.assertEqual(
            len(self._filter_records_label(tr2.stats.provenance, "Cut")), 1)
        self.assertEqual(
            len(self._filter_records_label(tr_a.stats.provenance, "Cut")), 2)

    def test_mul_method(self):
        """
        This method just creates copies of all the traces.

        Make sure they all contain the provenance information.
        """
        tr = obspy.read()[0]
        tr.stats.starttime = obspy.UTCDateTime(0)
        tr_a = tr.copy().trim(starttime=obspy.UTCDateTime(1))
        tr.trim(starttime=obspy.UTCDateTime(5))

        tr.stats.provenance.validate()
        tr_a.stats.provenance.validate()

        self.assertNotEqual(tr.stats.provenance, tr_a.stats.provenance)

        # Create a stream with 5 copies.
        st = tr_a * 5

        # They should all have the same provenance
        for _tr in st:
            self.assertEqual(_tr.stats.provenance, tr_a.stats.provenance)
            _tr.stats.provenance.validate()

        # Make sure the provenance documents are independent.
        st[2:].trim(starttime=obspy.UTCDateTime(10))
        for _tr in st[:2]:
            self.assertEqual(_tr.stats.provenance, tr_a.stats.provenance)
            _tr.stats.provenance.validate()
        for _tr in st[2:]:
            self.assertNotEqual(_tr.stats.provenance, tr_a.stats.provenance)
            _tr.stats.provenance.validate()
        # Also just check the ids.
        ids = set([id(_tr.stats.provenance) for _tr in st])
        self.assertEqual(len(ids), 5)

    def test_div_method(self):
        """
        Tests the div method of the Trace objects.
        """
        tr = obspy.read()[0]
        tr.stats.starttime = obspy.UTCDateTime(0)

        st = tr / 10

        self.assertEqual(len(st), 10)

        # Each of them should have one Cut provenance record.
        ids = []
        start_times = []
        end_times = []

        for _tr in st:
            _tr.stats.provenance.validate()
            ids.append(id(_tr.stats.provenance))

            self._assert_has_obspy_agent(_tr.stats.provenance)
            cut = self._filter_records_label(_tr.stats.provenance, "Cut")
            self.assertEqual(len(cut), 1)
            cut = cut[0]

            attrs = self._map_attributes(cut)
            st = attrs["new_start_time"]
            et = attrs["new_end_time"]
            self.assertGreater(et, st)
            start_times.append(st)
            end_times.append(et)

        # 10 independent provenance objects.
        self.assertEqual(len(set(ids)), 10)

        # Assert the times are monotonic.
        self.assertEqual(start_times, sorted(start_times))
        self.assertEqual(end_times, sorted(end_times))

        # Another test with an already existing provenance record.
        tr = obspy.read()[0]
        tr.stats.starttime = obspy.UTCDateTime(0)
        tr.trim(starttime=obspy.UTCDateTime(2))
        tr.stats.provenance.validate()

        st = tr / 10

        self.assertEqual(len(st), 10)
        ids = []

        for _tr in st:
            _tr.stats.provenance.validate()
            ids.append(id(_tr.stats.provenance))

            self._assert_has_obspy_agent(_tr.stats.provenance)
            cut = self._filter_records_label(_tr.stats.provenance, "Cut")
            # Make sure each has two provenance records this time around.
            self.assertEqual(len(cut), 2)

        # 10 independent provenance objects.
        self.assertEqual(len(set(ids)), 10)

    def test_mod_method(self):
        """
        Test provenance for the __mod__ method.
        """
        tr = obspy.read()[0]
        tr.stats.starttime = obspy.UTCDateTime(0)
        # Cut to 100 samples. Does not trigger provenance to be collected...
        tr.data = tr.data[:100]

        st = tr % 10

        self.assertEqual(len(st), 10)

        # Each of them should have one Cut provenance record.
        ids = []
        start_times = []
        end_times = []

        for _tr in st:
            _tr.stats.provenance.validate()
            ids.append(id(_tr.stats.provenance))

            self._assert_has_obspy_agent(_tr.stats.provenance)
            cut = self._filter_records_label(_tr.stats.provenance, "Cut")
            self.assertEqual(len(cut), 1)
            cut = cut[0]

            attrs = self._map_attributes(cut)
            st = attrs["new_start_time"]
            et = attrs["new_end_time"]
            self.assertGreater(et, st)
            start_times.append(st)
            end_times.append(et)

        # 10 independent provenance objects.
        self.assertEqual(len(set(ids)), 10)

        # Assert the times are monotonic.
        self.assertEqual(start_times, sorted(start_times))
        self.assertEqual(end_times, sorted(end_times))

        # Another test with an already existing provenance record.
        tr = obspy.read()[0]
        tr.stats.starttime = obspy.UTCDateTime(0)
        tr.trim(starttime=obspy.UTCDateTime(2))
        tr.stats.provenance.validate()
        tr.data = tr.data[:100]

        st = tr % 10

        self.assertEqual(len(st), 10)
        ids = []

        for _tr in st:
            _tr.stats.provenance.validate()
            ids.append(id(_tr.stats.provenance))

            self._assert_has_obspy_agent(_tr.stats.provenance)
            cut = self._filter_records_label(_tr.stats.provenance, "Cut")
            # Make sure each has two provenance records this time around.
            self.assertEqual(len(cut), 2)

        # 10 independent provenance objects.
        self.assertEqual(len(set(ids)), 10)

    def test_slide_method(self):
        """
        Tests provenance capturing for the trace.slide method.
        """
        tr = obspy.read()[0]
        tr.stats.starttime = obspy.UTCDateTime(0)
        tr.stats.sampling_rate = 1.0
        # Cut to 110 samples. Does not trigger provenance to be collected...
        tr.data = tr.data[:110]

        # Each of them should have one Cut provenance record.
        ids = []
        start_times = []
        end_times = []

        for _tr in tr.slide(window_length=10.0, step=10.0):
            _tr.stats.provenance.validate()
            ids.append(id(_tr.stats.provenance))

            self._assert_has_obspy_agent(_tr.stats.provenance)
            cut = self._filter_records_label(_tr.stats.provenance, "Cut")
            self.assertEqual(len(cut), 1)
            cut = cut[0]

            attrs = self._map_attributes(cut)
            st = attrs["new_start_time"]
            et = attrs["new_end_time"]
            self.assertGreater(et, st)
            start_times.append(st)
            end_times.append(et)

        # 10 independent provenance objects.
        self.assertEqual(len(set(ids)), 10)

        # Assert the times are monotonic.
        self.assertEqual(start_times, sorted(start_times))
        self.assertEqual(end_times, sorted(end_times))

        # Another test with an already existing provenance record.
        tr = obspy.read()[0]
        tr.stats.starttime = obspy.UTCDateTime(0)
        tr.stats.sampling_rate = 1.0
        tr.trim(starttime=obspy.UTCDateTime(2))
        tr.stats.provenance.validate()
        # Cut to 110 samples. Does not trigger provenance to be collected...
        tr.data = tr.data[:110]

        ids = []

        for _tr in tr.slide(window_length=10.0, step=10.0):
            _tr.stats.provenance.validate()
            ids.append(id(_tr.stats.provenance))

            self._assert_has_obspy_agent(_tr.stats.provenance)
            cut = self._filter_records_label(_tr.stats.provenance, "Cut")
            # Make sure each has two provenance records this time around.
            self.assertEqual(len(cut), 2)

        # 10 independent provenance objects.
        self.assertEqual(len(set(ids)), 10)

    def test_provenance_is_copied(self):
        """
        Tests that the provenance is copied and that the copies are
        independent.
        """
        tr = obspy.read()[0]
        tr.stats.starttime = obspy.UTCDateTime(0)
        tr.trim(starttime=obspy.UTCDateTime(1))
        tr.stats.provenance.validate()
        tr_a = tr.copy()
        tr_a.stats.provenance.validate()

        ids = set([id(_tr.stats.provenance) for _tr in [tr, tr_a]])
        self.assertEqual(len(ids), 2)

        self.assertEqual(tr.stats.provenance, tr_a.stats.provenance)
        tr_a.trim(starttime=obspy.UTCDateTime(10))
        tr_a.stats.provenance.validate()
        self.assertNotEqual(tr.stats.provenance, tr_a.stats.provenance)

    def test_detrend(self):
        """
        Tests the trace.detrend method.
        """
        tr = obspy.read()[0]

        # Test the various detrending methods.
        tr_a = tr.copy().detrend("simple")
        doc = tr_a.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Detrend")[0]), {
                'label': 'Detrend',
                'detrending_method': 'simple',
                'type': 'seis_prov:detrend'})

        tr_a = tr.copy().detrend("linear")
        doc = tr_a.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Detrend")[0]), {
                'label': 'Detrend',
                'detrending_method': 'linear fit',
                'type': 'seis_prov:detrend'})

        tr_a = tr.copy().detrend("constant")
        doc = tr_a.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Detrend")[0]), {
                'label': 'Detrend',
                'detrending_method': 'demean',
                'type': 'seis_prov:detrend'})

        tr_a = tr.copy().detrend("demean")
        doc = tr_a.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Detrend")[0]), {
                'label': 'Detrend',
                'detrending_method': 'demean',
                'type': 'seis_prov:detrend'})

        tr_a = tr.copy().detrend("polynomial", order=5)
        doc = tr_a.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Detrend")[0]), {
                'label': 'Detrend',
                'detrending_method': 'polynomial fit',
                'polynomial_order': 5,
                'type': 'seis_prov:detrend'})

        tr_a = tr.copy().detrend("spline", order=3, dspline=100)
        doc = tr_a.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
            self._map_attributes(self._filter_records_label(
                tr_a.stats.provenance, "Detrend")[0]), {
                'label': 'Detrend',
                'detrending_method': 'spline fit',
                'spline_degree': 3,
                'distance_between_spline_nodes_in_samples': 100,
                'type': 'seis_prov:detrend'})

    def test_differentiate(self):
        """
        Tests the trace.differentiate method.
        """
        tr = obspy.read()[0]
        tr.differentiate(method="gradient")
        doc = tr.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
                self._map_attributes(self._filter_records_label(
                        doc, "Differentiate")[0]), {
                    'label': 'Differentiate',
                    'differentiation_method':
                        'second order central differences',
                    'order': 1,
                    'type': 'seis_prov:differentiate'})

        # Test the default value.
        tr = obspy.read()[0]
        tr.differentiate()
        doc = tr.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
                self._map_attributes(self._filter_records_label(
                        doc, "Differentiate")[0]), {
                    'label': 'Differentiate',
                    'differentiation_method':
                        'second order central differences',
                    'order': 1,
                    'type': 'seis_prov:differentiate'})

    def test_integration(self):
        """
        Tests provenance collections for the trace.integration method.
        """
        # Test the default value.
        tr = obspy.read()[0]
        tr.integrate()
        doc = tr.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
                self._map_attributes(self._filter_records_label(
                        doc, "Integrate")[0]), {
                    'label': 'Integrate',
                    'integration_method': 'trapezoidal rule',
                    'order': 1,
                    'type': 'seis_prov:integrate'})

        # Test cumtrapz method.
        tr = obspy.read()[0]
        tr.integrate(method="cumtrapz")
        doc = tr.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
                self._map_attributes(self._filter_records_label(
                        doc, "Integrate")[0]), {
                    'label': 'Integrate',
                    'integration_method': 'trapezoidal rule',
                    'order': 1,
                    'type': 'seis_prov:integrate'})

        # Test the spline method.
        tr = obspy.read()[0]
        tr.integrate(method="spline", k=2)
        doc = tr.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
                self._map_attributes(self._filter_records_label(
                        doc, "Integrate")[0]), {
                    'label': 'Integrate',
                    'integration_method': 'interpolating spline',
                    'order': 1,
                    'spline_degree': 2,
                    'type': 'seis_prov:integrate'})

    def test_multiply(self):
        """
        Tests provenance tracking for the Trace.multiply() method.
        """
        tr = obspy.read()[0]
        tr.multiply(2.5)
        doc = tr.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
                self._map_attributes(self._filter_records_label(
                        doc, "Multiply")[0]), {
                    'label': 'Multiply',
                    'factor': 2.5,
                    'type': 'seis_prov:multiply'})

    def test_divide(self):
        """
        Tests provenance tracking for the Trace.divide() method.
        """
        tr = obspy.read()[0]
        tr.divide(3.5)
        doc = tr.stats.provenance
        doc.validate()
        self._assert_has_obspy_agent(doc)
        self.assertEqual(
                self._map_attributes(self._filter_records_label(
                        doc, "Divide")[0]), {
                    'label': 'Divide',
                    'divisor': 3.5,
                    'type': 'seis_prov:divide'})

        # def test_processing_information(self):
    #     """
    #     Test case for the automatic processing information.
    #     """
    #     tr = read()[0]
    #     trimming_starttime = tr.stats.starttime + 1
    #     tr.trim(trimming_starttime)
    #     tr.filter("lowpass", freq=2.0)
    #     tr.simulate(paz_remove={
    #         'poles': [-0.037004 + 0.037016j, -0.037004 - 0.037016j,
    #                   -251.33 + 0j],
    #         'zeros': [0j, 0j],
    #         'gain': 60077000.0,
    #         'sensitivity': 2516778400.0})
    #     tr.trigger(type="zdetect", nsta=20)
    #     tr.decimate(factor=2, no_filter=True)
    #     tr.resample(tr.stats.sampling_rate / 2.0)
    #     tr.differentiate()
    #     tr.integrate()
    #     tr.detrend()
    #     tr.taper(max_percentage=0.05, type='cosine')
    #     tr.normalize()
    #
    #     pr = tr.stats.processing
    #
    #     self.assertIn("trim", pr[0])
    #     self.assertEqual(
    #         "ObsPy %s: trim(endtime=None::fill_value=None::"
    #         "nearest_sample=True::pad=False::starttime=%s)" % (
    #             __version__, str(trimming_starttime)),
    #         pr[0])
    #     self.assertIn("filter", pr[1])
    #     self.assertIn("simulate", pr[2])
    #     self.assertIn("trigger", pr[3])
    #     self.assertIn("decimate", pr[4])
    #     self.assertIn("resample", pr[5])
    #     self.assertIn("differentiate", pr[6])
    #     self.assertIn("integrate", pr[7])
    #     self.assertIn("detrend", pr[8])
    #     self.assertIn("taper", pr[9])
    #     self.assertIn("normalize", pr[10])
    #
    # def test_no_processing_info_for_failed_operations(self):
    #     """
    #     If an operation fails, no processing information should be attached
    #     to the Trace object.
    #     """
    #     # create test Trace
    #     tr = Trace(data=np.arange(20))
    #     self.assertFalse("processing" in tr.stats)
    #     # This decimation by a factor of 7 in this case would change the
    #     # end time of the time series. Therefore it fails.
    #     self.assertRaises(ValueError, tr.decimate, 7, strict_length=True)
    #     # No processing should be applied yet.
    #     self.assertFalse("processing" in tr.stats)
    #
    #     # Test the same but this time with an already existing processing
    #     # information.
    #     tr = Trace(data=np.arange(20))
    #     tr.detrend()
    #     self.assertEqual(len(tr.stats.processing), 1)
    #     info = tr.stats.processing[0]
    #
    #     self.assertRaises(ValueError, tr.decimate, 7, strict_length=True)
    #     self.assertEqual(tr.stats.processing, [info])


def suite():
    return unittest.makeSuite(ProvenanceTestCase, 'test')


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
