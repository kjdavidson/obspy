# -*- coding: utf-8 -*-
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
from future.builtins import *  # NOQA

import collections
import io
import itertools
import os
import unittest
import warnings

import numpy as np

import obspy
from obspy.core.util.testing import NamedTemporaryFile
from obspy.io.xseed import Parser
from obspy.io.xseed.core import _is_resp, _is_xseed, _is_seed, _read_resp, \
    _read_seed, _read_xseed
from obspy.signal.invsim import evalresp_for_frequencies


class CoreTestCase(unittest.TestCase):
    """
    Test integration with ObsPy's inventory objects.
    """
    def setUp(self):
        self.data_path = os.path.join(os.path.dirname(__file__), "data")

        self.seed_files = [
            "AI.ESPZ._.BHE.dataless",
            "AI.ESPZ._.BH_.dataless",
            "BN.LPW._.BHE.dataless",
            "CL.AIO.dataless",
            "G.SPB.dataless",
            "arclink_full.seed",
            "bug165.dataless",
            "dataless.seed.BW_DHFO",
            "dataless.seed.BW_FURT",
            "dataless.seed.BW_MANZ",
            "dataless.seed.BW_RJOB",
            "dataless.seed.BW_ROTZ",
            "dataless.seed.BW_ZUGS",
            "dataless.seed.II_COCO"
        ]
        self.xseed_files = ["dataless.seed.BW_FURT.xml"]

        self.resp_files = ["RESP.BW.FURT..EHZ",
                           "RESP.XX.NR008..HHZ.130.1.100",
                           "RESP.XX.NS085..BHZ.STS2_gen3.120.1500",
                           "RESP.AZ.DHL..BS1"]
        self.other_files = ["II_COCO_three_channel_borehole.mseed",
                            "xml-seed-1.0.xsd",
                            "xml-seed-1.1.xsd"]

        self.seed_files = [
            os.path.join(self.data_path, _i) for _i in self.seed_files]
        self.xseed_files = [
            os.path.join(self.data_path, _i) for _i in self.xseed_files]
        self.resp_files = [
            os.path.join(self.data_path, _i) for _i in self.resp_files]
        self.other_files = [
            os.path.join(self.data_path, _i) for _i in self.other_files]

        # There are a couple more SEED files in the core test suite.
        core_data = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(self.data_path)))), "core",
            "tests", "data")
        self.seed_files.append(os.path.join(core_data, "AU.MEEK.seed"))
        self.seed_files.append(os.path.join(
            core_data, "IRIS_single_channel_with_response.seed"))

        for _i in itertools.chain.from_iterable([
                self.seed_files, self.xseed_files, self.resp_files,
                self.other_files]):
            assert os.path.exists(_i), _i

    def test_is_seed(self):
        for filename in self.seed_files:
            self.assertTrue(_is_seed(filename), filename)

        for filename in self.xseed_files:
            self.assertFalse(_is_seed(filename), filename)

        for filename in self.resp_files:
            self.assertFalse(_is_seed(filename), filename)

        for filename in self.other_files:
            self.assertFalse(_is_seed(filename), filename)

    def test_is_xseed(self):
        for filename in self.seed_files:
            self.assertFalse(_is_xseed(filename), filename)

        for filename in self.xseed_files:
            self.assertTrue(_is_xseed(filename), filename)

        for filename in self.resp_files:
            self.assertFalse(_is_xseed(filename), filename)

        for filename in self.other_files:
            self.assertFalse(_is_xseed(filename), filename)

    def test_is_resp(self):
        for filename in self.seed_files:
            self.assertFalse(_is_resp(filename), filename)

        for filename in self.xseed_files:
            self.assertFalse(_is_resp(filename), filename)

        for filename in self.resp_files:
            self.assertTrue(_is_resp(filename), filename)

        for filename in self.other_files:
            self.assertFalse(_is_resp(filename), filename)

    def test_simple_read_resp(self):
        """
        Currently just tests that all test RESP files can be read without an
        error.
        """
        for f in self.resp_files:
            _read_resp(f)

    def test_simple_read_seed(self):
        """
        Currently just tests that all test SEED files can be read without an
        error.
        """
        # One seed file is a bit faulty and thus raises a warning when read
        # - catch it.
        with warnings.catch_warnings(record=True):
            for f in self.seed_files:
                _read_seed(f)

    def test_simple_read_xseed(self):
        """
        Currently just tests that all test X(SEED) files can be read without
        an error.
        """
        for f in self.xseed_files:
            _read_xseed(f)

    def test_read_resp_metadata(self):
        """
        Manually assert that the meta-data is read correctly for all the
        RESP files.
        """
        # File A
        filename_a = os.path.join(self.data_path,
                                  "RESP.BW.FURT..EHZ")
        inv = obspy.read_inventory(filename_a)
        self.assertEqual(len(inv), 1)
        self.assertEqual(len(inv[0]), 1)
        self.assertEqual(len(inv[0][0]), 1)

        network = inv[0]
        station = inv[0][0]
        channel = inv[0][0][0]
        resp = inv[0][0][0].response

        self.assertEqual(network.code, "BW")
        self.assertEqual(station.code, "FURT")
        self.assertEqual(station.start_date, None)
        self.assertEqual(station.end_date, None)
        self.assertEqual(channel.location_code, "")
        self.assertEqual(channel.code, "EHZ")
        self.assertEqual(channel.start_date, obspy.UTCDateTime(2001, 1, 1))
        self.assertEqual(channel.end_date, None)
        # Also check the input and output units.
        self.assertEqual(resp.instrument_sensitivity.input_units, "M/S")
        self.assertEqual(resp.instrument_sensitivity.input_units_description,
                         "Velocity in Meters per Second")
        self.assertEqual(resp.instrument_sensitivity.output_units, "COUNTS")
        self.assertEqual(resp.instrument_sensitivity.output_units_description,
                         "Digital Counts")

        # File B
        filename_b = os.path.join(self.data_path,
                                  "RESP.XX.NR008..HHZ.130.1.100")
        inv = obspy.read_inventory(filename_b)
        self.assertEqual(len(inv), 1)
        self.assertEqual(len(inv[0]), 1)
        self.assertEqual(len(inv[0][0]), 1)

        network = inv[0]
        station = inv[0][0]
        channel = inv[0][0][0]
        resp = inv[0][0][0].response

        self.assertEqual(network.code, "XX")
        self.assertEqual(station.code, "NR008")
        self.assertEqual(station.start_date, None)
        self.assertEqual(station.end_date, None)
        self.assertEqual(channel.location_code, "")
        self.assertEqual(channel.code, "HHZ")
        self.assertEqual(channel.start_date, obspy.UTCDateTime(2006, 1, 1))
        self.assertEqual(channel.end_date,
                         obspy.UTCDateTime(3000, 1, 1) - 1)
        # Also check the input and output units.
        self.assertEqual(resp.instrument_sensitivity.input_units, "M/S")
        self.assertEqual(resp.instrument_sensitivity.input_units_description,
                         "Velocity in Meters per Second")
        self.assertEqual(resp.instrument_sensitivity.output_units, "COUNTS")
        self.assertEqual(resp.instrument_sensitivity.output_units_description,
                         "Digital Counts")

        # File C
        filename_c = os.path.join(self.data_path,
                                  "RESP.XX.NS085..BHZ.STS2_gen3.120.1500")
        inv = obspy.read_inventory(filename_c)
        self.assertEqual(len(inv), 1)
        self.assertEqual(len(inv[0]), 1)
        self.assertEqual(len(inv[0][0]), 1)

        network = inv[0]
        station = inv[0][0]
        channel = inv[0][0][0]
        resp = inv[0][0][0].response

        self.assertEqual(network.code, "XX")
        self.assertEqual(station.code, "NS085")
        self.assertEqual(station.start_date, None)
        self.assertEqual(station.end_date, None)
        self.assertEqual(channel.location_code, "")
        self.assertEqual(channel.code, "BHZ")
        self.assertEqual(channel.start_date, obspy.UTCDateTime(2006, 1, 1))
        self.assertEqual(channel.end_date, None)
        # Also check the input and output units.
        self.assertEqual(resp.instrument_sensitivity.input_units, "M/S")
        self.assertEqual(resp.instrument_sensitivity.input_units_description,
                         "Velocity in Meters per Second")
        self.assertEqual(resp.instrument_sensitivity.output_units, "COUNTS")
        self.assertEqual(resp.instrument_sensitivity.output_units_description,
                         "Digital Counts")

        # Merge A + B to get a multi-response file.
        with NamedTemporaryFile() as tf:
            with io.open(filename_a, "rb") as fh:
                tf.write(fh.read())
            tf.write(b"\n")
            with io.open(filename_b, "rb") as fh:
                tf.write(fh.read())
            tf.seek(0, 0)
            inv = obspy.read_inventory(tf.name)
        self.assertEqual(len(inv), 2)
        self.assertEqual(len(inv[0]), 1)
        self.assertEqual(len(inv[0][0]), 1)
        self.assertEqual(len(inv[1]), 1)
        self.assertEqual(len(inv[1][0]), 1)

        network = inv[0]
        station = inv[0][0]
        channel = inv[0][0][0]
        resp = inv[0][0][0].response

        self.assertEqual(network.code, "BW")
        self.assertEqual(station.code, "FURT")
        self.assertEqual(station.start_date, None)
        self.assertEqual(station.end_date, None)
        self.assertEqual(channel.location_code, "")
        self.assertEqual(channel.code, "EHZ")
        self.assertEqual(channel.start_date, obspy.UTCDateTime(2001, 1, 1))
        self.assertEqual(channel.end_date, None)
        # Also check the input and output units.
        self.assertEqual(resp.instrument_sensitivity.input_units, "M/S")
        self.assertEqual(resp.instrument_sensitivity.input_units_description,
                         "Velocity in Meters per Second")
        self.assertEqual(resp.instrument_sensitivity.output_units, "COUNTS")
        self.assertEqual(resp.instrument_sensitivity.output_units_description,
                         "Digital Counts")

        network = inv[1]
        station = inv[1][0]
        channel = inv[1][0][0]
        resp = inv[1][0][0].response

        self.assertEqual(network.code, "XX")
        self.assertEqual(station.code, "NR008")
        self.assertEqual(station.start_date, None)
        self.assertEqual(station.end_date, None)
        self.assertEqual(channel.location_code, "")
        self.assertEqual(channel.code, "HHZ")
        self.assertEqual(channel.start_date, obspy.UTCDateTime(2006, 1, 1))
        self.assertEqual(channel.end_date,
                         obspy.UTCDateTime(3000, 1, 1) - 1)
        # Also check the input and output units.
        self.assertEqual(resp.instrument_sensitivity.input_units, "M/S")
        self.assertEqual(resp.instrument_sensitivity.input_units_description,
                         "Velocity in Meters per Second")
        self.assertEqual(resp.instrument_sensitivity.output_units, "COUNTS")
        self.assertEqual(resp.instrument_sensitivity.output_units_description,
                         "Digital Counts")

    def test_read_seed_metainformation(self):
        """
        Test the mapping of meta-information for SEED files. This will be
        exactly identical for XML-SEED files so no need to test these as well.
        """
        filename = os.path.join(self.data_path, "dataless.seed.BW_ROTZ")
        inv = obspy.read_inventory(filename)

        self.assertEqual(len(inv), 1)
        self.assertEqual(len(inv[0]), 1)
        self.assertEqual(len(inv[0][0]), 3)

        network = inv[0]
        self.assertEqual(network.code, "BW")
        self.assertEqual(network.description, "BayernNetz")

        station = inv[0][0]
        self.assertEqual(station.code, "ROTZ")
        self.assertAlmostEqual(station.latitude, 49.766899)
        self.assertAlmostEqual(station.longitude, 12.207)
        self.assertAlmostEqual(station.elevation, 430.0)
        self.assertEqual(station.site.name, "Rotzenmuhle,Bavaria, BW-Net")
        self.assertEqual(station.start_date,
                         obspy.UTCDateTime("2006-06-04T00:00:00.000000Z"))
        self.assertEqual(station.end_date, None)

        # First channel.
        channel = inv[0][0][0]
        self.assertEqual(channel.code, "EHZ")
        self.assertEqual(channel.location_code, "")
        self.assertAlmostEqual(channel.latitude, 49.766899)
        self.assertAlmostEqual(channel.longitude, 12.207)
        self.assertAlmostEqual(channel.elevation, 430.0)
        self.assertAlmostEqual(channel.depth, 0.0)
        self.assertEqual(channel.azimuth, 0.0)
        self.assertEqual(channel.dip, -90.0)
        self.assertEqual(channel.start_date,
                         obspy.UTCDateTime("2006-06-04T00:00:00.000000Z"))
        self.assertEqual(channel.end_date, None)
        self.assertEqual(channel.sample_rate, 200.0)
        self.assertEqual(channel.sensor.type,
                         "Streckeisen STS-2/N seismometer")
        resp = channel.response
        self.assertEqual(resp.instrument_sensitivity.input_units, "M/S")
        self.assertEqual(resp.instrument_sensitivity.input_units_description,
                         "Velocity in Meters per Second")
        self.assertEqual(resp.instrument_sensitivity.output_units, "COUNTS")
        self.assertEqual(resp.instrument_sensitivity.output_units_description,
                         "Digital Counts")

        # Second channel.
        channel = inv[0][0][1]
        self.assertEqual(channel.code, "EHN")
        self.assertEqual(channel.location_code, "")
        self.assertAlmostEqual(channel.latitude, 49.766899)
        self.assertAlmostEqual(channel.longitude, 12.207)
        self.assertAlmostEqual(channel.elevation, 430.0)
        self.assertAlmostEqual(channel.depth, 0.0)
        self.assertEqual(channel.azimuth, 0.0)
        self.assertEqual(channel.dip, 0.0)
        self.assertEqual(channel.start_date,
                         obspy.UTCDateTime("2006-06-04T00:00:00.000000Z"))
        self.assertEqual(channel.end_date, None)
        self.assertEqual(channel.sample_rate, 200.0)
        self.assertEqual(channel.sensor.type,
                         "Streckeisen STS-2/N seismometer")
        resp = channel.response
        self.assertEqual(resp.instrument_sensitivity.input_units, "M/S")
        self.assertEqual(resp.instrument_sensitivity.input_units_description,
                         "Velocity in Meters per Second")
        self.assertEqual(resp.instrument_sensitivity.output_units, "COUNTS")
        self.assertEqual(resp.instrument_sensitivity.output_units_description,
                         "Digital Counts")

        # Third channel.
        channel = inv[0][0][2]
        self.assertEqual(channel.code, "EHE")
        self.assertEqual(channel.location_code, "")
        self.assertAlmostEqual(channel.latitude, 49.766899)
        self.assertAlmostEqual(channel.longitude, 12.207)
        self.assertAlmostEqual(channel.elevation, 430.0)
        self.assertAlmostEqual(channel.depth, 0.0)
        self.assertEqual(channel.azimuth, 90.0)
        self.assertEqual(channel.dip, 0.0)
        self.assertEqual(channel.start_date,
                         obspy.UTCDateTime("2006-06-04T00:00:00.000000Z"))
        self.assertEqual(channel.end_date, None)
        self.assertEqual(channel.sample_rate, 200.0)
        self.assertEqual(channel.sensor.type,
                         "Streckeisen STS-2/N seismometer")
        resp = channel.response
        self.assertEqual(resp.instrument_sensitivity.input_units, "M/S")
        self.assertEqual(resp.instrument_sensitivity.input_units_description,
                         "Velocity in Meters per Second")
        self.assertEqual(resp.instrument_sensitivity.output_units, "COUNTS")
        self.assertEqual(resp.instrument_sensitivity.output_units_description,
                         "Digital Counts")

    def test_response_calculation_from_resp_files(self):
        """
        Test the response calculations with the obspy.core interface.

        Compares with directly calling evalresp.
        """
        # Very broad range but the responses should be exactly identical as
        # they use the same code under the hood so it should prove no issue.
        frequencies = np.logspace(-3, 3, 100)

        for filename in self.resp_files:
            # Set the times for the response.
            t = obspy.UTCDateTime(2008, 1, 1)
            if "AZ.DHL..BS1" in filename:
                t = obspy.UTCDateTime(1999, julday=351)
            for unit in ("DISP", "VEL", "ACC"):
                r = obspy.read_inventory(filename)[0][0][0].response
                e_r = evalresp_for_frequencies(
                    t_samp=None, frequencies=frequencies, filename=filename,
                    date=t, units=unit)
                i_r = r.get_evalresp_response_for_frequencies(
                    frequencies=frequencies, output=unit)
                # This is in general very dangerous for floating point numbers
                # but they use exactly the same code under the hood here so it
                # is okay - if we ever have our own response calculation code
                # this will have to be changed.
                np.testing.assert_equal(e_r, i_r, "%s - %s" % (filename, unit))

    def test_response_calculation_from_seed_and_xseed(self):
        """
        Test the response calculations with the obspy.core interface.

        It does it by converting whatever it gets to RESP files and then
        uses evalresp to get the response. This is compared to using the
        ObsPy Response object - this also uses evalresp but the actual flow
        of the data is very different.

        This is an expensive test but worth it for the trust it builds and
        the bugs it found and prevents.
        """
        # Very broad range but the responses should be exactly identical as
        # they use the same code under the hood so it should prove no issue.
        frequencies = np.logspace(-3, 3, 100)

        for filename in self.seed_files + self.xseed_files:
            # Parse the files using the Parser object.
            with warnings.catch_warnings(record=True):
                p = Parser(filename)
                p_resp = {_i[0]: _i[1] for _i in p.get_resp()}
                # Also read using the core routines.
                inv = obspy.read_inventory(filename)

            # Get all the channels and epochs.
            channels = collections.defaultdict(list)
            for c in p.get_inventory()["channels"]:
                channels[c["channel_id"]].append(
                    (c["start_date"], c["end_date"]))

            # Loop over each.
            for channel, epochs in channels.items():
                with NamedTemporaryFile() as tf:
                    r = p_resp["RESP.%s" % channel]
                    r.seek(0, 0)
                    tf.write(r.read())

                    # Now loop over the epochs.
                    for start, end in epochs:
                        if end:
                            t = start + (end - start) / 2
                        else:
                            t = start + 10

                        # Find response
                        n, s, l, c = channel.split(".")
                        _inv_t = inv.select(network=n, station=s,
                                            location=l, channel=c,
                                            starttime=t - 1, endtime=t + 1)
                        # Should now only be a single channel.
                        self.assertEqual(_inv_t.get_contents()["channels"],
                                         [channel])
                        inv_r = _inv_t[0][0][0].response

                        for unit in ("DISP", "VEL", "ACC"):
                            # Directly call evalresp.
                            e_r = evalresp_for_frequencies(
                                t_samp=None, frequencies=frequencies,
                                filename=tf.name, date=t, units=unit)
                            i_r = inv_r.get_evalresp_response_for_frequencies(
                                frequencies=frequencies, output=unit)
                            # Adaptive absolute tolerance to deal with very
                            # small values.
                            atol = 1E-7 * max(np.abs(e_r).max(),
                                              np.abs(i_r).max())
                            np.testing.assert_allclose(
                                e_r.real, i_r.real,
                                err_msg="real - %s - %s" % (filename, unit),
                                rtol=1E-6, atol=atol)
                            np.testing.assert_allclose(
                                e_r.imag, i_r.imag,
                                err_msg="imag - %s - %s" % (filename, unit),
                                rtol=1E-6, atol=atol)

                            # Bonus: Also read the RESP file directly with
                            # obspy.core and test the response.
                            i_r_r = obspy.read_inventory(tf.name).select(
                                starttime=t - 1,
                                endtime=t + 1)[0][0][0].response\
                                .get_evalresp_response_for_frequencies(
                                frequencies=frequencies, output=unit)
                            np.testing.assert_allclose(
                                e_r.real, i_r_r.real,
                                err_msg="RESP real - %s - %s" % (filename,
                                                                 unit),
                                rtol=1E-6, atol=atol)
                            np.testing.assert_allclose(
                                e_r.imag, i_r_r.imag,
                                err_msg="RESP imag - %s - %s" % (filename,
                                                                 unit),
                                rtol=1E-6, atol=atol)


def suite():
    return unittest.makeSuite(CoreTestCase, 'test')


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
