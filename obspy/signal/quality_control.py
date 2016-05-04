# -*- coding: utf-8 -*-
"""
Quality control module for ObsPy.

Currently requires MiniSEED files as that is the dominant data format in
data centers.

:author:
    Luca Trani (trani@knmi.nl)
    Lion Krischer (krischer@geophysik.uni-muenchen.de)
:copyright:
    The ObsPy Development Team (devs@obspy.org)
:license:
    GNU Lesser General Public License, Version 3
    (http://www.gnu.org/copyleft/lesser.html)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
from future.builtins import *  # NOQA

import collections
import json

import numpy as np
import obspy
from obspy.io.mseed.util import get_flags


class DataQualityEncoder(json.JSONEncoder):
    """
    Custom encoder capable of dealing with NumPy and ObsPy types.
    """
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, obspy.UTCDateTime):
            return str(obj)
        else:
            return super(DataQualityEncoder, self).default(obj)


class MSEEDMetadata(object):
    """
    A container for MSEED specific metadata including QC.
    """
    def __init__(self, files, starttime=None, endtime=None, c_seg=True):
        """
        Reads the MiniSEED files and extracts the data quality metrics.

        :param files: The MiniSEED files.
        :type files: list
        :param starttime: Only use records whose end time is larger then this
            given time. Also specifies the new official start time of the
            metadata object.
        :type starttime: :class:`obspy.core.utcdatetime.UTCDateTime`
        :param endtime: Only use records whose start time is smaller then this
            given time. Also specifies the new official end time of the
            metadata object
        :type endtime: :class:`obspy.core.utcdatetime.UTCDateTime`
        :param c_seg: Calculate metrics for each continuous segment.
        :type c_seg: bool
        """

        self.data = obspy.Stream()
        self.files = []

        # Allow anything UTCDateTime can parse.
        if starttime is not None:
            starttime = obspy.UTCDateTime(starttime)
        if endtime is not None:
            endtime = obspy.UTCDateTime(endtime)

        self.window_start = starttime
        self.window_end = endtime

        # We are required to exclude samples at T1. Therefore, shift the
        # time window to the left by 1μs and set nearest_sample to False.
        # This will force ObsPy to fall back to the sample left of the endtime
        if endtime is not None:
            endtime_left = endtime - 1e-6
        else:
            endtime_left = None

        # Will raise if not a MiniSEED files.
        for file in files:

            st = obspy.read(file, starttime=starttime, endtime=endtime_left,
                            format="mseed", nearest_sample=False)

            # Empty stream or maybe there is no data in the stream for the
            # requested time span.
            if not st:
                continue

            self.files.append(file)

            # Only extend traces with data (npts > 0)
            for tr in st:
                if(tr.stats.npts != 0):
                    self.data.extend([tr])

        if not self.data:
            raise ValueError("No data within the temporal constraints.")

        # Do some sanity checks. The class only works with data from a
        # single location so we have to make sure that the existing data on
        # this object and the newly added all have the same identifier.
        ids = set(tr.id + "." + tr.stats.mseed.dataquality for tr in self.data)
        if len(ids) != 1:
            raise ValueError("All traces must have the same SEED id and "
                             "quality")

        self.data.sort()

        # Set the metric start and endtime specified by the user.
        # If no start and endtime are given, we pick our own and the window
        # will start on the first sample and end on the last sample + Δt.
        end_stats = self.data[-1].stats
        self.starttime = starttime or self.data[0].stats.starttime
        self.endtime = endtime or end_stats.endtime + end_stats.delta
        self.total_time = self.endtime - self.starttime

        # Get sample left of the user specified starttime
        # This will allow us to determine start continuity in our window
        if self.window_start is not None:
            self._get_left_sample()

        # The calculation of all the metrics begins here
        self.meta = {}
        self._extract_mseed_stream_metadata()
        self._compute_sample_metrics()

        if c_seg:
            self._compute_continuous_seg_sample_metrics()

    def _get_left_sample(self):
        """
        Finds the most first sample BEFORE the user specified starttime
        The most reliable way to do this is to set the starttime as the
        endtime, and using nearest_sample=False to fall back to the
        previous sample. A little bit hacky, but reading takes only a few
        0.01s so it is not a bottleneck in the procedure.
        """
        self.end_data = obspy.Stream()
        self.start_offset = None
        for file in self.files:
            self.end_data.extend(obspy.read(file, endtime=self.starttime-1e-6,
                                 nearest_sample=False, format="mseed"))
        # Determine the expected first sample AFTER the starttime
        # Which is equivalent to the first sample BEFORE the starttime,
        # in addition to delta (include the time tolerance).
        if self.end_data:
            end_stats = self.end_data[-1].stats
            self.start_offset = end_stats.endtime + end_stats.delta
            self.start_tolerance = 0.5*end_stats.delta

    @property
    def number_of_records(self):
        """
        Number of records across files.
        """
        return sum(tr.stats.mseed.number_of_records for tr in self.data)

    @property
    def number_of_samples(self):
        """
        Number of samples across files.
        """
        return sum(tr.stats.npts for tr in self.data)

    def _extract_mseed_stream_stats(self):
        """
        Collects the mSEED stats
        """
        stats = self.data[0].stats
        self.meta['network'] = stats.network
        self.meta['station'] = stats.station
        self.meta['location'] = stats.location
        self.meta['channel'] = stats.channel
        self.meta['quality'] = stats.mseed.dataquality

    def _extract_mseed_stream_metadata(self):
        """
        Collect information from the MiniSEED headers.
        """

        self._extract_mseed_stream_stats()

        meta = self.meta

        # Add other parameters to the metadata object
        meta['mseed_id'] = self.data[0].id
        meta['files'] = self.files
        meta['start_time'] = self.starttime
        meta['end_time'] = self.endtime
        meta['num_records'] = self.number_of_records
        meta['num_samples'] = self.number_of_samples

        # The following are lists as it might contain multiple entries.
        meta['sample_rate'] = \
            sorted(list(set([tr.stats.sampling_rate for tr in self.data])))
        meta['record_length'] = \
            sorted(list(set([tr.stats.mseed.record_length
                             for tr in self.data])))
        meta['encoding'] = \
            sorted(list(set([tr.stats.mseed.encoding for tr in self.data])))

        # Setup counters for the MiniSEED header flags.
        data_quality_flags = collections.Counter(
                amplifier_saturation_detected=0,
                digitizer_clipping_detected=0,
                spikes_detected=0,
                glitches_detected=0,
                missing_data_present=0,
                telemetry_sync_error=0,
                digital_filter_charging=0,
                time_tag_uncertain=0)
        activity_flags = collections.Counter(
                calibration_signals_present=0,
                time_correction_applied=0,
                beginning_event=0,
                end_event=0,
                positive_leap=0,
                negative_leap=0,
                clock_locked=0,
                time_correction_required=0)
        io_and_clock_flags = collections.Counter(
                station_volume_parity_error=0,
                long_record_read=0,
                short_record_read=0,
                start_time_series=0,
                end_time_series=0,
                clock_locked=0)
        timing_quality = []

        # Setup counters for the MiniSEED header flags percentages.
        # Counters are supposed to work for integers, but
        # it also appears to work for floats too
        data_quality_flags_seconds = collections.Counter(
                amplifier_saturation_detected=0.0,
                digitizer_clipping_detected=0.0,
                spikes_detected=0.0,
                glitches_detected=0.0,
                missing_data_present=0.0,
                telemetry_sync_error=0.0,
                digital_filter_charging=0.0,
                time_tag_uncertain=0.0)
        activity_flags_seconds = collections.Counter(
                calibration_signals_present=0.0,
                time_correction_applied=0.0,
                beginning_event=0.0,
                end_event=0.0,
                positive_leap=0.0,
                negative_leap=0.0,
                clock_locked=0.0,
                time_correction_required=0.0)
        io_and_clock_flags_seconds = collections.Counter(
                station_volume_parity_error=0.0,
                long_record_read=0.0,
                short_record_read=0.0,
                start_time_series=0.0,
                end_time_series=0.0,
                clock_locked=0.0)

        for file in self.files:
            flags = get_flags(
                file, starttime=self.starttime, endtime=self.endtime)

            # Update the flag counters
            data_quality_flags.update(flags["data_quality_flags"])
            activity_flags.update(flags["activity_flags"])
            io_and_clock_flags.update(flags["io_and_clock_flags"])

            # Update the percentage counters
            data_quality_flags_seconds.update(
                flags["data_quality_flags_seconds"])
            activity_flags_seconds.update(
                flags["activity_flags_seconds"])
            io_and_clock_flags_seconds.update(
                flags["io_and_clock_flags_seconds"])

            if flags["timing_quality"]:
                timing_quality.append(flags["timing_quality"]["all_values"])

        # Convert second counts to percentages. The total time is the
        # difference between start & end in seconds. The percentage fields
        # are the sum of record lengths for which the respective bits are
        # set in seconds
        for key in data_quality_flags_seconds:
            data_quality_flags_seconds[key] /= self.total_time * 1e-2
        for key in activity_flags_seconds:
            activity_flags_seconds[key] /= self.total_time * 1e-2
        for key in io_and_clock_flags_seconds:
            io_and_clock_flags_seconds[key] /= self.total_time * 1e-2

        # Only calculate the timing quality statistics if each files has the
        # timing quality set. This should usually be the case. Otherwise we
        # would created tinted statistics. There is still a chance that some
        # records in a file have timing qualities set and others not but
        # that should be small.
        if len(timing_quality) == len(self.files):
            timing_quality = np.concatenate(timing_quality)
            timing_quality_mean = timing_quality.mean()
            timing_quality_min = timing_quality.min()
            timing_quality_max = timing_quality.max()
            timing_quality_median = np.median(timing_quality)
            timing_quality_lower_quartile = np.percentile(timing_quality, 25)
            timing_quality_upper_quartile = np.percentile(timing_quality, 75)
        else:
            timing_quality_mean = None
            timing_quality_min = None
            timing_quality_max = None
            timing_quality_median = None
            timing_quality_lower_quartile = None
            timing_quality_upper_quartile = None

        # Set miniseed header counts
        meta['timing_quality_mean'] = timing_quality_mean
        meta['timing_quality_min'] = timing_quality_min
        meta['timing_quality_max'] = timing_quality_max
        meta['timing_quality_median'] = timing_quality_median
        meta['timing_quality_lower_quartile'] = timing_quality_lower_quartile
        meta['timing_quality_upper_quartile'] = timing_quality_upper_quartile

        # According to schema @ maybe refactor this to less verbose names
        # Set miniseed header flag percentages
        meta['miniseed_header_flag_percentages'] = {}
        pointer = meta['miniseed_header_flag_percentages']
        pointer['activity_flags'] = activity_flags_seconds
        pointer['data_quality_flags'] = data_quality_flags_seconds
        pointer['io_and_clock_flags'] = io_and_clock_flags_seconds

        # Set miniseed header flag counts
        meta['miniseed_header_flag_counts'] = {}
        pointer = meta['miniseed_header_flag_counts']
        pointer['activity_flags'] = activity_flags
        pointer['data_quality_flags'] = data_quality_flags
        pointer['io_and_clock_flags'] = io_and_clock_flags

        # Small function to change flag names from the get_flags routine
        # to match the schema
        self._fix_flag_names()

    def _fix_flag_names(self):
        """
        Supplementary function to fix flag parameter names
        Parameters with a key in the name_ref will be changed to its value
        """
        name_reference = {
            'amplifier_saturation_detected': 'amplifier_saturation',
            'digitizer_clipping_detected': 'digitizer_clipping',
            'spikes_detected': 'spikes',
            'glitches_detected': 'glitches',
            'missing_data_present': 'missing_padded_data',
            'time_tag_uncertain': 'suspect_time_tag',
            'calibration_signals_present': 'calibration_signal',
            'time_correction_applied': 'timing_correction',
            'beginning_event': 'event_begin',
            'end_event': 'event_end',
            'station_volume_parity_error': 'station_volume',
        }

        # Loop over all keys and replace where required according to
        # the name_reference
        prefix = 'miniseed_header_flag'
        for flag_type in ['_percentages', '_counts']:
            for _, flags in self.meta[prefix + flag_type].iteritems():
                for param in flags:
                    if param in name_reference:
                        flags[name_reference[param]] = flags.pop(param)

    def _check_start_continuity(self):
        """
        Supplementary function to check whether a gap exists at the start
        of the stream in a user specified time-window. The parameter
        self.start_offset is equal to the first sample BEFORE the starttime
        plus delta. Account for time tolerance. If start_offset is None,
        implicitly assume there is a gap between starttime and first sample
        in the time-window.
        """
        stats = self.data[0].stats
        if self.start_offset is not None:
            # Is there a gap at the start
            if stats.starttime > self.start_offset + self.start_tolerance:
                self.gap_count += 1
                self.gap_length += stats.starttime - self.starttime
            # Maybe an overlap
            if stats.starttime < self.start_offset - self.start_tolerance:
                self.overlap_count += 1
                self.overlap_length += self.start_offset - stats.starttime
        else:
            # Implicitly assume a gap at the start
            if stats.starttime > self.starttime:
                self.gap_count += 1
                self.gap_length += stats.starttime - self.starttime

    def _check_end_continuity(self):
        """
        We define the endtime as the time of the last sample but the next
        sample would only start at endtime + delta. Thus the following
        scenario would not count as a gap at the end:
        x -- x -- x -- x -- x -- x -- <= self.endtime
        """
        end_stats = self.data[-1].stats
        next_offset = end_stats.endtime + end_stats.delta
        next_tolerance = 0.5*end_stats.delta
        if(next_offset + next_tolerance < self.endtime):
            self.gap_count += 1
            self.gap_length += self.endtime - next_offset

    def _compute_sample_metrics(self):
        """
        Computes metrics on samples contained in the specified time window
        """
        if not self.data:
            return

        # Make sure there is no integer division by chance.
        npts = float(self.number_of_samples)

        self.meta['sample_min'] = min([tr.data.min() for tr in self.data])
        self.meta['sample_max'] = max([tr.data.max() for tr in self.data])

        # Manually implement these as they have to work across a list of
        # arrays.
        self.meta['sample_mean'] = \
            sum(tr.data.sum() for tr in self.data) / npts

        # Might overflow np.int64 so make Python obj. (.astype(object))
        # allows conversion to long int when required
        self.meta['sample_rms'] = \
            np.sqrt(sum((tr.data.astype(object) ** 2).sum()
                        for tr in self.data) / npts)

        self.meta['sample_stdev'] = np.sqrt(sum(
            ((tr.data - self.meta["sample_mean"]) ** 2).sum()
            for tr in self.data) / npts)

        # Get gaps at beginning and end and the stream
        self.gap_count = 0
        self.overlap_count = 0
        self.gap_length = 0.0
        self.overlap_length = 0.0

        # Check continuity at the start and end of the stream for user window
        if self.window_start is not None:
            self._check_start_continuity()
        if self.window_end is not None:
            self._check_end_continuity()

        # Get the other gaps
        gaps = self.data.get_gaps()
        self.meta["num_gaps"] = \
            len([_i for _i in gaps if _i[-1] > 0]) + self.gap_count
        self.meta["num_overlaps"] = \
            len([_i for _i in gaps if _i[-1] < 0]) + self.overlap_count
        self.meta["gaps_len"] = \
            sum(abs(_i[-2]) for _i in gaps if _i[-1] > 0) + self.gap_length
        self.meta["overlaps_len"] = \
            sum(abs(_i[-2]) for _i in gaps if _i[-1] < 0) + self.overlap_length

        # Percentage based availability as total gap length over the trace
        # duration
        self.meta['percent_availability'] = 100 * (
            (self.total_time - self.meta['gaps_len']) /
            self.total_time)

    def _compute_continuous_seg_sample_metrics(self):
        """
        Computes metrics on the samples within each continuous segment.
        """
        if not self.data:
            return

        c_segments = []

        for tr in self.data:
            seg = {}
            seg['start_time'] = tr.stats.starttime
            seg['end_time'] = tr.stats.endtime
            seg['sample_min'] = tr.data.min()
            seg['sample_max'] = tr.data.max()
            seg['sample_mean'] = tr.data.mean()
            seg['sample_rms'] = np.sqrt((tr.data.astype(object) ** 2).sum() /
                                        tr.stats.npts)
            seg['sample_stdev'] = tr.data.std()
            seg['num_samples'] = tr.stats.npts
            seg['seg_len'] = tr.stats.endtime - tr.stats.starttime
            c_segments.append(seg)

        self.meta['c_segments'] = c_segments

    def get_json_meta(self):
        """
        Serialize the meta dictionary to JSON.

        :return: JSON containing the MSEED metadata
        """
        return json.dumps(self.meta, cls=DataQualityEncoder)


if __name__ == '__main__':
    import doctest
    doctest.testmod(exclude_empty=True)
