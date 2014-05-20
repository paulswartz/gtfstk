"""
Some tools for computing stats from GTFS feeds.

All time estimates below were produced on a 2013 MacBook Pro with a
2.8 GHz Intel Core i7 processor and 16GB of RAM running OS 10.9.2.
"""
from __future__ import print_function, division
import datetime as dt
from itertools import izip
import dateutil.relativedelta as rd
from collections import OrderedDict

import pandas as pd
import numpy as np
from shapely.geometry import Point, LineString, mapping
import utm

def date_to_str(date, format_str='%Y%m%d', inverse=False):
    """
    Given a datetime.date object, convert it to a string in the given format
    and return the result.
    If ``inverse == True``, then assume the given date is in the given
    string format and return its corresponding date object.
    """
    if date is None:
        return None
    if not inverse:
        result = date.strftime(format_str)
    else:
        result = dt.datetime.strptime(date, format_str).date()
    return result

def seconds_to_timestr(seconds, inverse=False):
    """
    Return the given number of integer seconds as the time string '%H:%M:%S'.
    If ``inverse == True``, then do the inverse operation.
    In keeping with GTFS standards, the hours entry may be greater than 23.
    """
    if not inverse:
        try:
            seconds = int(seconds)
            hours, remainder = divmod(seconds, 3600)
            mins, secs = divmod(remainder, 60)
            result = '{:02d}:{:02d}:{:02d}'.format(hours, mins, secs)
        except:
            result = None
    else:
        try:
            hours, mins, seconds = seconds.split(':')
            result = int(hours)*3600 + int(mins)*60 + int(seconds)
        except:
            result = None
    return result

def timestr_mod_24(timestr):
    """
    Given a GTFS time string in the format %H:%M:%S, return a timestring
    in the same format but with the hours taken modulo 24.
    """
    try:
        hours, mins, seconds = [int(x) for x in timestr.split(':')]
        hours %= 24
        result = '{:02d}:{:02d}:{:02d}'.format(hours, mins, seconds)
    except:
        result = None
    return result

def weekday_to_str(weekday, inverse=False):
    """
    Given a weekday, that is, an integer in ``range(7)``, return
    it's corresponding weekday name as a lowercase string.
    Here 0 -> 'monday', 1 -> 'tuesday', and so on.
    If ``inverse == True``, then perform the inverse operation.
    """
    s = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 
      'saturday', 'sunday']
    if not inverse:
        try:
            return s[weekday]
        except:
            return
    else:
        try:
            return s.index(weekday)
        except:
            return

def get_segment_length(linestring, p, q=None):
    """
    Given a Shapely linestring and two Shapely points or coordinate pairs,
    project the points onto the linestring, and return the distance along
    the linestring between the two points.
    If ``q is None``, then return the distance from the start of the linestring
    to the projection of ``p``.
    """
    # Get projected distances
    d_p = linestring.project(Point(p))
    if q is not None:
        d_q = linestring.project(Point(q))
        d = abs(d_p - d_q)
    else:
        d = d_p
    return d

def to_int(x):
    """
    Given a NumPy number type, convert it to an integer if it represents
    an integer, e.g. 1.0 -> 1. 
    Otherwise, return the input.
    """
    try:
        return x.astype(int)
    except:
        return x

def downsample_routes_time_series(routes_time_series, freq):
    """
    Resample the given routes time series, which is the output of 
    ``Feed.get_routes_time_series()``, to the given (Pandas style) frequency.
    Additionally, add a new 'mean_daily_speed' time series to the output 
    dictionary.
    """
    result = {name: None for name in routes_time_series}
    result.update({'mean_daily_speed': None})
    for name in result:
        if name == 'mean_daily_speed':
            numer = routes_time_series['mean_daily_distance'].resample(freq,
              how=np.sum)
            denom = routes_time_series['mean_daily_duration'].resample(freq,
              how=np.sum)
            g = numer.divide(denom)
        elif name == 'mean_daily_num_trip_starts':
            f = routes_time_series[name]
            g = f.resample(freq, how=np.sum)
        elif name == 'mean_daily_num_vehicles':
            f = routes_time_series[name]
            g = f.resample(freq, how=np.mean)
        elif name == 'mean_daily_duration':
            f = routes_time_series[name]
            g = f.resample(freq, how=np.sum)
        else:
            # name == 'distance'
            f = routes_time_series[name]
            g = f.resample(freq, how=np.sum)
        result[name] = g
    return result

def downsample_stops_time_series(stops_time_series, freq):
    """
    Resample the given stops time series, which is the output of 
    ``Feed.get_stops_time_series()``, to the given (Pandas style) frequency.
    """
    result = {name: None for name in stops_time_series}
    for name in result:
        if name == 'mean_daily_num_vehicles':
            f = stops_time_series[name]
            g = f.resample(freq, how=np.sum)
        result[name] = g
    return result

# TODO: test more
def plot_routes_time_series(routes_ts_dict, big_units=True):
    """
    Given a routes time series dictionary (possibly downsampled),
    sum each time series over all routes, plot each series using
    MatplotLib, and return the resulting figure of four subplots.
    """
    import matplotlib.pyplot as plt

    # Plot sum of routes stats at 30-minute frequency
    F = None
    for name, f in routes_ts_dict.iteritems():
        g = f.T.sum().T
        if name == 'mean_daily_distance':
            # Convert to km
            g /= 1000
        elif name == 'mean_daily_duration':
            # Convert to h
            g /= 3600
        if F is None:
            # Initialize F
            F = pd.DataFrame(g, columns=[name])
        else:
            F[name] = g
    # Fix speed
    F['mean_daily_speed'] = F['mean_daily_distance'].divide(
      F['mean_daily_duration'])
    # Reformat periods
    F.index = [t.time().strftime('%H:%M') for t in F.index.to_datetime()]
    colors = ['red', 'blue', 'yellow', 'purple', 'green'] 
    alpha = 0.7
    names = [
      'mean_daily_num_trip_starts', 
      'mean_daily_num_vehicles', 
      'mean_daily_distance',
      'mean_daily_duration', 
      'mean_daily_speed',
      ]
    titles = [name.capitalize().replace('_', ' ') for name in names]
    units = ['','','km','h', 'kph']
    fig, axes = plt.subplots(nrows=len(names), ncols=1)
    for (i, name) in enumerate(names):
        F[name].plot(ax=axes[i], color=colors[i], alpha=alpha, 
          kind='bar', figsize=(8, 10))
        axes[i].set_title(titles[i])
        axes[i].set_ylabel(units[i])

    #fig.tight_layout()
    return fig

class Feed(object):
    """
    A class to gather all the GTFS files for a feed and store them as 
    Pandas data frames.
    """
    def __init__(self, path):
        self.path = path 
        self.routes = pd.read_csv(path + 'routes.txt')
        self.stops = pd.read_csv(path + 'stops.txt', dtype={'stop_id': str})
        self.shapes = pd.read_csv(path + 'shapes.txt', dtype={'shape_id': str})
        self.trips = pd.read_csv(path + 'trips.txt', dtype={'shape_id': str,
          'stop_id': str, 'direction_id': str})
        self.calendar = pd.read_csv(path + 'calendar.txt', 
          dtype={'service_id': str}, 
          date_parser=lambda x: date_to_str(x, inverse=True), 
          parse_dates=['start_date', 'end_date'])
        try:
            self.calendar_dates = pd.read_csv(path + 'calendar_dates.txt', 
              dtype={'service_id': str}, 
              date_parser=lambda x: date_to_str(x, inverse=True), 
              parse_dates=['date'])
        except IOError:
            # Doesn't exist, so create an empty data frame
            self.calendar_dates = pd.DataFrame()
        # Merge trips and calendar
        self.calendar_m = pd.merge(self.trips[['trip_id', 'service_id']],
          self.calendar).set_index('trip_id')
        
    def get_stop_times(self):
        """
        Return ``stop_times.txt`` as a Pandas data frame.
        This frame can be big.
        For example the one for the SEQ feed has roughly 2 million rows.
        So i'll only import it when i need it for now, instead of storing
        it as an attribute.
        """
        st = pd.read_csv(self.path + 'stop_times.txt', dtype={'stop_id': str})
    
        # Prefix a 0 to arrival and departure times if necessary.
        # This makes sorting by time work as expected.
        def reformat(timestr):
            result = timestr
            if len(result) == 7:
                result = '0' + result
            return result

        st[['arrival_time', 'departure_time']] =\
          st[['arrival_time', 'departure_time']].applymap(reformat)
        return st

    def get_dates(self):
        """
        Return a chronologically ordered list of dates 
        (``datetime.date`` objects) for which this feed is valid. 
        """
        start_date = self.calendar['start_date'].min()
        end_date = self.calendar['end_date'].max()
        days =  (end_date - start_date).days
        return [start_date + rd.relativedelta(days=+d) 
          for d in range(days + 1)]

    def get_first_week(self):
        """
        Return a list of dates (``datetime.date`` objects) 
        of the first Monday--Sunday week for which this feed is valid.
        In the unlikely event that this feed does not cover a full 
        Monday--Sunday week, then return whatever initial segment of the 
        week it does cover. 
        """
        dates = self.get_dates()
        # Get first Monday
        monday_index = None
        for (i, date) in enumerate(dates):
            if date.weekday() == 0:
                monday_index = i
                break
        week = []
        for j in range(7):
            try:
                week.append(dates[monday_index + j])
            except:
                break
        return week

    def is_active_trip(self, trip, date):
        """
        If the given trip (trip_id) is active on the given date 
        (date object), then return ``True``.
        Otherwise, return ``False``.
        """
        cal = self.calendar_m
        row = cal.ix[trip]
        # Check exceptional scenario given by calendar_dates
        cald = self.calendar_dates
        service = row['service_id']
        if not cald.empty:
            if not cald[(cald['service_id'] == service) &\
              (cald['date'] == date) &\
              (cald['exception_type'] == 1)].empty:
                return True
            if not cald[(cald['service_id'] == service) &\
              (cald['date'] == date) &\
              (cald['exception_type'] == 2)].empty:
                return False
        # Check regular scenario
        start_date = row['start_date']
        end_date = row['end_date']
        weekday_str = weekday_to_str(date.weekday())
        if start_date <= date <= end_date and row[weekday_str] == 1:
            return True
        else:
            return False

    def get_linestring_by_shape(self):
        """
        Return a dictionary with structure
        shape_id -> Shapely linestring of shape in UTM coordinates.
        """
        # Note the output for conversion to UTM with the utm package:
        # >>> u = utm.from_latlon(47.9941214, 7.8509671)
        # >>> print u
        # (414278, 5316285, 32, 'T')
        linestring_by_shape = {}
        for shape, group in self.shapes.groupby('shape_id'):
            lons = group['shape_pt_lon'].values
            lats = group['shape_pt_lat'].values
            xys = [utm.from_latlon(lat, lon)[:2] 
              for lat, lon in izip(lats, lons)]
            linestring_by_shape[shape] = LineString(xys)
        return linestring_by_shape

    def get_xy_by_stop(self):
        """
        Return a dictionary with structure
        stop_id -> stop location as a UTM coordinate pair
        """
        xy_by_stop = {}
        for stop, group in self.stops.groupby('stop_id'):
            lat, lon = group[['stop_lat', 'stop_lon']].values[0]
            xy_by_stop[stop] = utm.from_latlon(lat, lon)[:2] 
        return xy_by_stop

    # TODO: Redo with groupby and apply
    def get_stop_times_with_shape_dist_traveled(self):
        """
        Compute the optional ``shape_dist_traveled`` GTFS field for
        ``self.get_stop_times()`` and return the resulting Pandas data frame.  

        NOTES:

        This takes a *long* time, so probably needs improving.
        On the SEQ feed, i stopped it after 2 hours.
        """
        trips = self.trips
        stop_times = self.get_stop_times()

        t1 = dt.datetime.now()
        print(t1, 'Adding shape_dist_traveled field to %s stop times...' %\
          stop_times['trip_id'].count())

        linestring_by_shape = self.get_linestring_by_shape()
        xy_by_stop = self.get_xy_by_stop()

        failures = []

        # Initialize data frame
        merged = pd.merge(trips[['trip_id', 'shape_id']], stop_times)
        merged['shape_dist_traveled'] = pd.Series()

        # Compute shape_dist_traveled column entries
        dist_by_stop_by_shape = {shape: {} for shape in linestring_by_shape}
        for shape, group in merged.groupby('shape_id'):
            linestring = linestring_by_shape[shape]
            for trip, subgroup in group.groupby('trip_id'):
                # Compute the distances of the stops along this trip
                subgroup.sort('stop_sequence')
                stops = subgroup['stop_id'].values
                distances = []
                for stop in stops:
                    if stop in dist_by_stop_by_shape[shape]:
                        d = dist_by_stop_by_shape[shape][stop]
                    else:
                        d = round(
                          get_segment_length(linestring, xy_by_stop[stop]), 2)
                        dist_by_stop_by_shape[shape][stop] = d
                    distances.append(d)
                if distances[0] > distances[1]:
                    # This happens when the shape linestring direction is the
                    # opposite of the trip direction. Reverse the distances.
                    distances = distances[::-1]
                if distances != sorted(distances):
                    # Uh oh
                    failures.append(trip)
                # Insert stop distances
                index = subgroup.index[0]
                for (i, d) in enumerate(distances):
                    merged.ix[index + i, 'shape_dist_traveled'] = d

        del merged['shape_id']

        t2 = dt.datetime.now()
        minutes = (t2 - t1).seconds/60
        print(t2, 'Finished in %.2f min' % minutes)
        print('%s failures on these trips: %s' % (len(failures), failures))  

        return merged

    def get_trips_stats(self):
        """
        Return a Pandas data frame with the following columns:

        - trip_id
        - direction_id
        - route_id
        - start_time: first departure time of the trip
        - end_time: last departure time of the trip
        - start_stop_id: stop ID of the first stop of the trip 
        - end_stop_id: stop ID of the last stop of the trip
        - duration: duration of the trip (seconds)
        - distance: distance of the trip (meters)

        NOTES:

        Takes about 2.8 minutes on the SEQ feed.
        """
        trips = self.trips
        stop_times = self.get_stop_times()

        t1 = dt.datetime.now()
        num_trips = trips.shape[0]
        print(t1, 'Creating trip stats for %s trips...' % num_trips)

        # Initialize data frame. Base it on trips.txt.
        stats = trips[['route_id', 'trip_id', 'direction_id']]

        # Convert departure times to seconds past midnight, 
        # to compute durations below
        stop_times['departure_time'] = stop_times['departure_time'].map(
          lambda x: seconds_to_timestr(x, inverse=True))

        # Compute start time, end time, duration
        f = pd.merge(trips, stop_times).groupby('trip_id')
        g = f['departure_time'].agg({'start_time': np.min, 'end_time': np.max})
        g['duration'] = g['end_time'] - g['start_time']

        # Compute start stop and end stop
        def start_stop(group):
            i = group['departure_time'].argmin()
            return group['stop_id'].at[i]

        def end_stop(group):
            i = group['departure_time'].argmax()
            return group['stop_id'].at[i]

        g['start_stop'] = f.apply(start_stop)
        g['end_stop'] = f.apply(end_stop)

        # Convert times back to time strings
        g[['start_time', 'end_time']] = g[['start_time', 'end_time']].\
          applymap(lambda x: seconds_to_timestr(int(x)))

        # Compute trip distance, which is more involved
        g['shape_id'] = f['shape_id'].first()
        linestring_by_shape = self.get_linestring_by_shape()
        xy_by_stop = self.get_xy_by_stop()
        dist_by_stop_pair_by_shape = {shape: {} 
          for shape in linestring_by_shape}

        for trip, row in g.iterrows():
            start_stop = row.at['start_stop'] 
            end_stop = row.at['end_stop'] 
            shape = row.at['shape_id']
            stop_pair = frozenset([start_stop, end_stop])
            if stop_pair in dist_by_stop_pair_by_shape[shape]:
                d = dist_by_stop_pair_by_shape[shape][stop_pair]
            else:
                # Compute distance afresh and store
                linestring = linestring_by_shape[shape]
                p = xy_by_stop[start_stop]
                q = xy_by_stop[end_stop]
                d = get_segment_length(linestring, p, q) 
                if d == 0:
                    # Trip is a circuit. 
                    # This can even happen when start_stop != end_stop 
                    # if the two stops are very close together
                    d = linestring.length
                d = int(round(d))        
                dist_by_stop_pair_by_shape[shape][stop_pair] = d               
            g.ix[trip, 'distance'] = d

        stats = pd.merge(stats, g.reset_index())
        stats.sort('route_id')

        t2 = dt.datetime.now()
        minutes = (t2 - t1).seconds/60
        print(t2, 'Finished trips stats in %.2f min' % minutes)    
    
        return stats

    def get_trips_activity(self, dates):
        """
        Return a Pandas data frame with the columns

        - trip_id
        - route_id
        - dates[0]: a series of ones and zeros indicating if a 
        trip is active (1) on the given date or inactive (0)
        ...
        - dates[-1]: ditto

        NOTES:

        Takes about 1 minute on the SEQ feed.
        """
        if not dates:
            return

        f = self.trips
        for date in dates:
            f[date] = f['trip_id'].map(lambda trip: 
              int(self.is_active_trip(trip, date)))
        return f[['trip_id', 'route_id'] + dates]

    def get_routes_stats(self, trips_stats, dates):
        """
        Take ``trips_stats``, which is the output of 
        ``self.get_trips_stats()``, and use it to calculate stats for 
        all the routs in this feed averaged over the given dates 
        (list of ``datetime.date`` objects). 
        
        Return a Pandas data frame with the following columns

        - route_id: route ID
        - mean_daily_num_trips
        - min_start_time: start time of the earliest active trip on 
          the route
        - max_end_time: end time of latest active trip on the route
        - max_headway: maximum of the durations (in seconds) between 
          trip starts on the route between 07:00 and 19:00 
          on the given dates
        - mean_headway: mean of the durations (in seconds) between 
          vehicle departures at the stop between 07:00 and 19:00 
          on the given dates
        - mean_daily_duration: in seconds
        - mean_daily_distance: in meters

        NOTES:

        Takes about 1 minute on the SEQ feed.
        """
        if not dates:
            return 

        # Time the function call
        t1 = dt.datetime.now()
        print(t1, 'Creating routes stats for {!s} trips...'.format(
          trips_stats.shape[0]))

        # Merge trips stats with trips activity, 
        # assign a weight to each trip equal to the fraction of days in 
        # dates for which it is active, and and drop 0-weight trips
        trips_stats = pd.merge(trips_stats, self.get_trips_activity(dates))
        trips_stats['weight'] = trips_stats[dates].sum(axis=1)/len(dates)
        trips_stats = trips_stats[trips_stats['weight'] > 0]
        
        # Convert trip start times to seconds to ease headway calculations
        trips_stats['start_time'] = trips_stats['start_time'].map(lambda x: 
          seconds_to_timestr(x, inverse=True))

        def get_route_stats(group):
            # Take this group of all trips stats for a single route
            # and compute route-level stats.
            headways = []
            for date in dates:
                stimes = sorted(group[group[date] > 0]['start_time'].\
                  values)
                stimes = [stime for stime in stimes 
                  if 7*3600 <= stime <= 19*3600]
                headways.extend([stimes[i + 1] - stimes[i] 
                  for i in range(len(stimes) - 1)])
            if headways:
                max_headway = np.max(headways)
                mean_headway = round(np.mean(headways))
            else:
                max_headway = np.nan
                mean_headway = np.nan
            mean_daily_num_trips = group['weight'].sum()
            min_start_time = group['start_time'].min()
            max_end_time = group['end_time'].max()
            mean_daily_duration = (group['duration']*group['weight']).sum()
            mean_daily_distance = (group['distance']*group['weight']).sum()
            df = pd.DataFrame([[min_start_time, max_end_time, 
              mean_daily_num_trips, max_headway, mean_headway, 
              mean_daily_duration, mean_daily_distance]], columns=[
              'min_start_time', 'max_end_time', 
              'mean_daily_num_trips', 'max_headway', 'mean_headway', 
              'mean_daily_duration', 'mean_daily_distance'])
            df.index.name = 'foo'
            return df

        result = trips_stats.groupby('route_id').apply(get_route_stats).\
          reset_index()
        del result['foo']

        # Convert route start times to time strings
        result['min_start_time'] = result['min_start_time'].map(lambda x: 
          seconds_to_timestr(x))

        t2 = dt.datetime.now()
        minutes = (t2 - t1).seconds/60
        print(t2, 'Finished routes stats in %.2f min' % minutes)    

        return result

    def get_routes_time_series(self, trips_stats, dates):
        """
        Given ``trips_stats``, which is the output of 
        ``self.get_trips_stats()``, use it to calculate the following 
        four time series of routes stats:
        
        - mean daily number of vehicles in service by route ID
        - mean daily number of trip starts by route ID
        - mean daily service duration (seconds) by route ID
        - mean daily service distance (meters) by route ID

        Each time series is a Pandas data frame over a 24-hour 
        period with minute (period index) frequency (00:00 to 23:59).
        
        Return the time series as values of a dictionary with keys
        'mean_daily_num_vehicles', 'mean_daily_num_trip_starts', 
        'mean_daily_duration', 'mean_daily_distance'.

        NOTES:

        - To resample the resulting time series use the following methods:
            - for 'mean_daily_num_vehicles' series, use ``how=np.mean``
            - for the other series, use ``how=np.sum`` 
        - To remove the placeholder date (2001-1-1) and seconds from any 
          of the time series f, do ``f.index = [t.time().strftime('%H:%M') 
          for t in f.index.to_datetime()]``
        - Takes about 2 minutes on the SEQ feed.
        """  
        if not dates:
            return 

        t1 = dt.datetime.now()
        stats = trips_stats
        routes = sorted(self.routes['route_id'].values)
        num_trips = stats.shape[0]
        print(t1, 'Creating routes time series for %s trips...' % num_trips)

        # Merge trips_stas with trips activity, get trip weights,
        # and drop 0-weight trips
        n = len(dates)
        stats = pd.merge(stats, self.get_trips_activity(dates))
        stats['weight'] = stats[dates].sum(axis=1)/n
        stats = stats[stats.weight > 0]
        
        # Initialize time series
        if n > 1:
            # Assign a uniform generic date for the index
            date_str = '2000-1-1'
        else:
            # Use the given date for the index
            date_str = date_to_str(dates[0]) 
        day_start = pd.to_datetime(date_str + ' 00:00:00')
        day_end = pd.to_datetime(date_str + ' 23:59:00')
        rng = pd.period_range(day_start, day_end, freq='Min')
        names = ['mean_daily_num_vehicles', 
          'mean_daily_num_trip_starts', 'mean_daily_duration', 
          'mean_daily_distance']
        series_by_name = {}
        for name in names:
            series_by_name[name] = pd.DataFrame(np.nan, index=rng, 
              columns=routes)
        
        # Bin each trip according to its start and end time and weight
        i = 0
        for index, row in stats.iterrows():
            i += 1
            print("Progress {:2.1%}".format(i/num_trips), end="\r")
            trip = row['trip_id']
            route = row['route_id']
            weight = row['weight']
            start_time = row['start_time']
            end_time = row['end_time']
            start = pd.to_datetime(date_str + ' ' +\
              timestr_mod_24(start_time))
            end = pd.to_datetime(date_str + ' ' +\
              timestr_mod_24(end_time))

            for name, f in series_by_name.iteritems():
                if start == end:
                    criterion = f.index == start
                    num_bins = 1
                elif start < end:
                    criterion = (f.index >= start) & (f.index < end)
                    num_bins = (end - start).seconds/60
                else:
                    criterion = (f.index >= start) | (f.index < end)
                    # Need to add 1 because day_end is 23:59 not 24:00
                    num_bins = (day_end - start).seconds/60 + 1 +\
                      (end - day_start).seconds/60
                # Bin route
                g = f.loc[criterion, route] 
                # Use fill_value=0 to overwrite NaNs with numbers.
                # Need to use pd.Series() to get fill_value to work.
                if name == 'mean_daily_num_trip_starts':
                    f.loc[f.index == start, route] = g.add(pd.Series(
                      weight, index=g.index), fill_value=0)
                elif name == 'mean_daily_num_vehicles':
                    f.loc[criterion, route] = g.add(pd.Series(
                      weight, index=g.index), fill_value=0)
                elif name == 'mean_daily_duration':
                    f.loc[criterion, route] = g.add(pd.Series(
                      weight*60, index=g.index), fill_value=0)
                else:
                    # name == 'distance'
                    f.loc[criterion, route] = g.add(pd.Series(
                      weight*row['distance']/num_bins, index=g.index),
                      fill_value=0)

        t2 = dt.datetime.now()
        minutes = (t2 - t1).seconds/60
        print(t2, 'Finished routes time series in %.2f min' % minutes)    

        return series_by_name

    # def get_route_timetable(self, route, date):
    #     """
    #     Given a route (route_id) and a date (datetime.date object),
    #     return a Pandas data frame describing the time table for the
    #     given stop on the given date with the columns

    #     - arrival_time
    #     - departure_time
    #     - trip_id

    #     and ordered by arrival time.
    #     """
    #     # Get active trips and merge with stop times
    #     trips_activity = self.get_trips_activity([date])
    #     ta = trips_activity[trips_activity[date] > 0]
    #     stop_times = self.get_stop_times()
    #     f = pd.merge(ta, stop_times)
        
    #     def get_first_trip(group):
    #         g = group.sort('departure_time')
    #         return g[['arrival_time', 'departure_time']].iloc[0]

    #     return f[f['route_id'] == route].groupby('trip_id').apply(
    #       get_first_trip).reset_index()

    def get_stops_stats(self, dates):
        """
        Return a Pandas data frame with the following columns:

        - stop_id
        - mean_daily_num_vehicles: mean daily number of vehicles visiting stop 
        - max_headway: maximum of the durations (in seconds) between 
          vehicle departures at the stop between 07:00 and 19:00 
          on the given dates
        - mean_headway: mean of the durations (in seconds) between 
          vehicle departures at the stop between 07:00 and 19:00 
          on the given dates
        - min_start_time: earliest departure time of a vehicle from this stop
          over the given date range
        - max_end_time: latest departure time of a vehicle from this stop
          over the given date range

        NOTES:

        Takes about 1.8 minutes for the SEQ feed.
        """
        t1 = dt.datetime.now()
        print(t1, 'Calculating stops stats...')

        # Get active trips and merge with stop times
        trips_activity = self.get_trips_activity(dates)
        ta = trips_activity[trips_activity[dates].sum(axis=1) > 0]
        stop_times = self.get_stop_times()
        f = pd.merge(ta, stop_times)

        # Convert departure times to seconds to ease headway calculations
        f['departure_time'] = f['departure_time'].map(lambda x: 
          seconds_to_timestr(x, inverse=True))

        # Compute stats for each stop
        def get_stop_stats(group):
            # Operate on the group of all stop times for an individual stop
            headways = []
            num_vehicles = 0
            for date in dates:
                dtimes = sorted(group[group[date] > 0]['departure_time'].\
                  values)
                num_vehicles += len(dtimes)
                dtimes = [dtime for dtime in dtimes 
                  if 7*3600 <= dtime <= 19*3600]
                headways.extend([dtimes[i + 1] - dtimes[i] 
                  for i in range(len(dtimes) - 1)])
            if headways:
                max_headway = np.max(headways)
                mean_headway = round(np.mean(headways))
            else:
                max_headway = np.nan
                mean_headway = np.nan
            mean_daily_num_vehicles = num_vehicles/len(dates)
            min_start_time = group['departure_time'].min()
            max_end_time = group['departure_time'].max()
            df = pd.DataFrame([[min_start_time, max_end_time, 
              mean_daily_num_vehicles, max_headway, mean_headway]], 
              columns=['min_start_time', 'max_end_time', 
              'mean_daily_num_vehicles', 'max_headway', 'mean_headway'])
            df.index.name = 'foo'
            return df

        result = f.groupby('stop_id').apply(get_stop_stats).reset_index()
        del result['foo']

        # Convert start and end times to time strings
        result[['min_start_time', 'max_end_time']] =\
          result[['min_start_time', 'max_end_time']].applymap(
          lambda x: seconds_to_timestr(x))

        t2 = dt.datetime.now()
        minutes = (t2 - t1).seconds/60
        print(t2, 'Finished stops stats in %.2f min' % minutes)    

        return result

    def get_stops_time_series(self, dates):
        """
        Return the following time series of routes stats:
        
        - mean daily number of vehicles by stop ID

        The time series is a Pandas data frame over a 24-hour 
        period with minute (period index) frequency (00:00 to 23:59).
        
        Return the time series as a value in a dictionary with key
        'mean_daily_num_vehicles'. 
        (Outputing a dictionary of a time series instead of simply a 
        time series matches the structure of ``get_routes_time_series()``
        and allows for the possibility of adding other stops time series
        at a later stage of development.)

        NOTES:

        - To resample the resulting time series use the following methods:
          for 'mean_daily_num_vehicles' series, use ``how=np.sum``
        - To remove the placeholder date (2001-1-1) and seconds from any 
          of the time series f, do ``f.index = [t.time().strftime('%H:%M') 
          for t in f.index.to_datetime()]``
        - Takes about 2 minutes on the SEQ feed.
        """  
        if not dates:
            return 

        t1 = dt.datetime.now()
        stops = sorted(self.stops['stop_id'].values)
        num_stops = len(stops)
        print(t1, 'Creating stops time series for %s stops...' % num_stops)

        # Get active trips and merge with stop times
        trips_activity = self.get_trips_activity(dates)
        ta = trips_activity[trips_activity[dates].sum(axis=1) > 0]
        stop_times = self.get_stop_times()
        stats = pd.merge(ta, stop_times)
        n = len(dates)
        stats['weight'] = stats[dates].sum(axis=1)/n

        # Initialize time series
        if n > 1:
            # Assign a uniform generic date for the index
            date_str = '2000-1-1'
        else:
            # Use the given date for the index
            date_str = date_to_str(dates[0]) 
        day_start = pd.to_datetime(date_str + ' 00:00:00')
        day_end = pd.to_datetime(date_str + ' 23:59:00')
        rng = pd.period_range(day_start, day_end, freq='Min')
        names = ['mean_daily_num_vehicles']
        series_by_name = {}
        for name in names:
            series_by_name[name] = pd.DataFrame(np.nan, index=rng, 
              columns=stops)
        
        # Convert departure time string to datetime
        stats['departure_time'] = stats['departure_time'].map(lambda x: 
          pd.to_datetime(date_str + ' ' + timestr_mod_24(x)))

        # Bin each trip according to its departure time at the stop
        i = 0
        f = series_by_name['mean_daily_num_vehicles']
        for stop, group in stats.groupby('stop_id'):
            i += 1
            print("Progress {:2.1%}".format(i/num_stops), end="\r")
            for index, row in group.iterrows():
                weight = row['weight']
                dtime = row['departure_time']
                # Bin stop time
                criterion = f.index == dtime
                g = f.loc[criterion, stop] 
                # Use fill_value=0 to overwrite NaNs with numbers.
                # Need to use pd.Series() to get fill_value to work.
                f.loc[criterion, stop] = g.add(pd.Series(
                  weight, index=g.index), fill_value=0)
      
        t2 = dt.datetime.now()
        minutes = (t2 - t1).seconds/60
        print(t2, 'Finished routes time series in %.2f min' % minutes)    

        return series_by_name

    # def get_stop_timetable(self, stop, date):
    #     """
    #     Given a stop (stop_id) and a date (datetime.date object),
    #     return a Pandas data frame describing the time table for the
    #     given stop on the given date with the columns

    #     - arrival_time
    #     - departure_time
    #     - trip_id
    #     - route_id

    #     and ordered by arrival time.
    #     """
    #     # Get active trips and merge with stop times
    #     trips_activity = self.get_trips_activity([date])
    #     ta = trips_activity[trips_activity[date] > 0]
    #     stop_times = self.get_stop_times()
    #     f = pd.merge(ta, stop_times)
    #     return f[f['stop_id'] == stop][['arrival_time', 'departure_time', 
    #       'trip_id', 'route_id']].sort('arrival_time').reset_index(drop=True)

    # TODO: test more and improve readme
    def dump_all_stats(self, dates=None, freq='1H', directory=None):
        """
        Into the given directory, dump to separate CSV files the outputs of
        
        - ``self.get_trips_stats()``
        - ``self.get_routes_stats(dates)``
        - ``self.get_routes_time_series(dates)``
        - ``self.get_stops_stats(dates)``
        - ``self.get_stops_time_series(dates)``

        where each time series is resampled to the given frequency.
        Also include a ``README.txt`` file that contains a few notes
        on units and include some useful charts.

        If no dates are given, then use ``self.get_first_week()[:5]``.
        If no directory is given, then use ``self.path + 'stats/'``. 

        NOTES:

        Takes about 17 minutes on the SEQ feed.
        """
        import os
        import textwrap

        # Time function call
        t1 = dt.datetime.now()
        print(t1, 'Beginning process...')

        if dates is None:
            dates = self.get_first_week()[:5]
        if directory is None:
            directory = self.path + 'stats/'
        if not os.path.exists(directory):
            os.makedirs(directory)
        dates_str = ' to '.join(
          [date_to_str(d) for d in [dates[0], dates[-1]]])

        # Write README.txt, which contains notes on units and date range
        readme = """
        Notes 
        =====

        - Distances are measured in meters and durations are measured in
        seconds
        - Stats were calculated for the period {!s}
        """.format(dates_str)
        
        with open(directory + 'notes.rst', 'w') as f:
            f.write(textwrap.dedent(readme))

        # Trips stats
        trips_stats = self.get_trips_stats()
        trips_stats.to_csv(directory + 'trips_stats.csv', index=False)

        # Routes stats
        routes_stats = self.get_routes_stats(trips_stats, dates)
        routes_stats.to_csv(directory + 'routes_stats.csv', index=False)

        # Routes time series
        rts = self.get_routes_time_series(trips_stats, dates)
        rts = downsample_routes_time_series(rts, freq=freq)
        for name, f in rts.iteritems():
            # Remove date from timestamps
            g = f.copy()
            g.index = [d.time() for d in g.index.to_datetime()]
            g.T.to_csv(directory + 'routes_time_series_%s_%s.csv' %\
              (name, freq), index_label='route_id')

        # Stops time series
        sts = self.get_stops_time_series(dates)
        sts = downsample_stops_time_series(sts, freq=freq)
        for name, f in sts.iteritems():
            # Remove date from timestamps
            g = f.copy()
            g.index = [d.time() for d in g.index.to_datetime()]
            g.T.to_csv(directory + 'stops_time_series_%s_%s.csv' %\
              (name, freq), index_label='stop_id')

        # Plot sum of routes stats 
        fig = plot_routes_time_series(rts)
        fig.tight_layout()
        fig.savefig(directory + 'routes_time_series_agg.pdf', dpi=200)
        
        t2 = dt.datetime.now()
        minutes = (t2 - t1).seconds/60
        print(t2, 'Finished process in %.2f min' % minutes)    

