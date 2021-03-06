"""
Functions about trips.
"""
from collections import OrderedDict
import json

import pandas as pd
import numpy as np
import shapely.geometry as sg
import shapely.ops as so

from . import constants as cs
from . import helpers as hp


def is_active_trip(feed, trip_id, date):
    """
    Return ``True`` if the ``feed.calendar`` or ``feed.calendar_dates``
    says that the trip runs on the given date; return ``False``
    otherwise.

    Note that a trip that starts on date d, ends after 23:59:59, and
    does not start again on date d+1 is considered active on date d and
    not active on date d+1.
    This subtle point, which is a side effect of the GTFS, can
    lead to confusion.

    Parameters
    ----------
    feed : Feed
    trip_id : string
        ID of a trip in ``feed.trips``
    date : string
        YYYYMMDD date string

    Returns
    -------
    boolean
        ``True`` if and only if the given trip starts on the given
        date.

    Notes
    -----
    - This function is key for getting all trips, routes, etc. that are
      active on a given date, so the function needs to be fast
    - Assume the following feed attributes are not ``None``:

        * ``feed.trips``

    """
    service = feed._trips_i.at[trip_id, "service_id"]
    # Check feed._calendar_dates_g.
    caldg = feed._calendar_dates_g
    if caldg is not None:
        if (service, date) in caldg.groups:
            et = caldg.get_group((service, date))["exception_type"].iat[0]
            if et == 1:
                return True
            else:
                # Exception type is 2
                return False
    # Check feed._calendar_i
    cali = feed._calendar_i
    if cali is not None:
        if service in cali.index:
            weekday_str = hp.weekday_to_str(hp.datestr_to_date(date).weekday())
            if (
                cali.at[service, "start_date"]
                <= date
                <= cali.at[service, "end_date"]
                and cali.at[service, weekday_str] == 1
            ):
                return True
            else:
                return False
    # If you made it here, then something went wrong
    return False


def get_trips(feed, date=None, time=None):
    """
    Return a subset of ``feed.trips``.

    Parameters
    ----------
    feed : Feed
    date : string
        YYYYMMDD date string
    time : string
        HH:MM:SS time string, possibly with HH > 23

    Returns
    -------
    DataFrame
        The subset of ``feed.trips`` containing trips active (starting)
        on the given date at the given time.
        If no date or time are specified, then return the entire
        ``feed.trips``.

    """
    if feed.trips is None or date is None:
        return feed.trips

    f = feed.trips.copy()
    f["is_active"] = f["trip_id"].map(
        lambda trip_id: feed.is_active_trip(trip_id, date)
    )
    f = f[f["is_active"]].copy()
    del f["is_active"]

    if time is not None:
        # Get trips active during given time
        g = pd.merge(f, feed.stop_times[["trip_id", "departure_time"]])

        def F(group):
            d = {}
            start = group["departure_time"].dropna().min()
            end = group["departure_time"].dropna().max()
            try:
                result = start <= time <= end
            except TypeError:
                result = False
            d["is_active"] = result
            return pd.Series(d)

        h = g.groupby("trip_id").apply(F).reset_index()
        f = pd.merge(f, h[h["is_active"]])
        del f["is_active"]

    return f


def compute_trip_activity(feed, dates):
    """
    Mark trip as active or inactive on the given dates as computed
    by :func:`is_active_trip`.

    Parameters
    ----------
    feed : Feed
    dates : string or list
        A YYYYMMDD date string or list thereof indicating the date(s)
        for which to compute activity

    Returns
    -------
    DataFrame
        Columns are

        - ``'trip_id'``
        - ``dates[0]``: 1 if the trip is active on ``dates[0]``;
          0 otherwise
        - ``dates[1]``: 1 if the trip is active on ``dates[1]``;
          0 otherwise
        - etc.
        - ``dates[-1]``: 1 if the trip is active on ``dates[-1]``;
          0 otherwise

        If ``dates`` is ``None`` or the empty list, then return an
        empty DataFrame.

    Notes
    -----
    Assume the following feed attributes are not ``None``:

    - ``feed.trips``
    - Those used in :func:`is_active_trip`

    """
    dates = feed.restrict_dates(dates)
    if not dates:
        return pd.DataFrame()

    f = feed.trips.copy()
    for date in dates:
        f[date] = f["trip_id"].map(
            lambda trip_id: int(feed.is_active_trip(trip_id, date))
        )
    return f[["trip_id"] + list(dates)]


def compute_busiest_date(feed, dates):
    """
    Given a list of dates, return the first date that has the
    maximum number of active trips.

    Notes
    -----
    Assume the following feed attributes are not ``None``:

    - Those used in :func:`compute_trip_activity`

    """
    f = feed.compute_trip_activity(dates)
    s = [(f[c].sum(), c) for c in f.columns if c != "trip_id"]
    return max(s)[1]


def compute_trip_stats(
    feed, route_ids=None, *, compute_dist_from_shapes=False
):
    """
    Return a DataFrame with the following columns:

    - ``'trip_id'``
    - ``'route_id'``
    - ``'route_short_name'``
    - ``'route_type'``
    - ``'direction_id'``
    - ``'shape_id'``
    - ``'num_stops'``: number of stops on trip
    - ``'start_time'``: first departure time of the trip
    - ``'end_time'``: last departure time of the trip
    - ``'start_stop_id'``: stop ID of the first stop of the trip
    - ``'end_stop_id'``: stop ID of the last stop of the trip
    - ``'is_loop'``: 1 if the start and end stop are less than 400m apart and
      0 otherwise
    - ``'distance'``: distance of the trip in ``feed.dist_units``;
      contains all ``np.nan`` entries if ``feed.shapes is None``
    - ``'duration'``: duration of the trip in hours
    - ``'speed'``: distance/duration

    If ``feed.stop_times`` has a ``shape_dist_traveled`` column with at
    least one non-NaN value and ``compute_dist_from_shapes == False``,
    then use that column to compute the distance column.
    Else if ``feed.shapes is not None``, then compute the distance
    column using the shapes and Shapely.
    Otherwise, set the distances to NaN.

    If route IDs are given, then restrict to trips on those routes.

    Notes
    -----
    - Assume the following feed attributes are not ``None``:

        * ``feed.trips``
        * ``feed.routes``
        * ``feed.stop_times``
        * ``feed.shapes`` (optionally)
        * Those used in :func:`.stops.build_geometry_by_stop`

    - Calculating trip distances with ``compute_dist_from_shapes=True``
      seems pretty accurate.  For example, calculating trip distances on
      `this Portland feed
      <https://transitfeeds.com/p/trimet/43/1400947517>`_
      using ``compute_dist_from_shapes=False`` and
      ``compute_dist_from_shapes=True``,
      yields a difference of at most 0.83km from the original values.

    """
    f = feed.trips.copy()

    # Restrict to given route IDs
    if route_ids is not None:
        f = f[f["route_id"].isin(route_ids)].copy()

    # Merge with stop times and extra trip info.
    # Convert departure times to seconds past midnight to
    # compute trip durations later.
    f = (
        f[["route_id", "trip_id", "direction_id", "shape_id"]]
        .merge(feed.routes[["route_id", "route_short_name", "route_type"]])
        .merge(feed.stop_times)
        .sort_values(["trip_id", "stop_sequence"])
        .assign(
            departure_time=lambda x: x["departure_time"].map(
                hp.timestr_to_seconds
            )
        )
    )

    # Compute all trips stats except distance,
    # which is possibly more involved
    geometry_by_stop = feed.build_geometry_by_stop(use_utm=True)
    g = f.groupby("trip_id")

    def my_agg(group):
        d = OrderedDict()
        d["route_id"] = group["route_id"].iat[0]
        d["route_short_name"] = group["route_short_name"].iat[0]
        d["route_type"] = group["route_type"].iat[0]
        d["direction_id"] = group["direction_id"].iat[0]
        d["shape_id"] = group["shape_id"].iat[0]
        d["num_stops"] = group.shape[0]
        d["start_time"] = group["departure_time"].iat[0]
        d["end_time"] = group["departure_time"].iat[-1]
        d["start_stop_id"] = group["stop_id"].iat[0]
        d["end_stop_id"] = group["stop_id"].iat[-1]
        dist = geometry_by_stop[d["start_stop_id"]].distance(
            geometry_by_stop[d["end_stop_id"]]
        )
        d["is_loop"] = int(dist < 400)
        d["duration"] = (d["end_time"] - d["start_time"]) / 3600
        return pd.Series(d)

    # Apply my_agg, but don't reset index yet.
    # Need trip ID as index to line up the results of the
    # forthcoming distance calculation
    h = g.apply(my_agg)

    # Compute distance
    if (
        hp.is_not_null(f, "shape_dist_traveled")
        and not compute_dist_from_shapes
    ):
        # Compute distances using shape_dist_traveled column
        h["distance"] = g.apply(
            lambda group: group["shape_dist_traveled"].max()
        )
    elif feed.shapes is not None:
        # Compute distances using the shapes and Shapely
        geometry_by_shape = feed.build_geometry_by_shape(use_utm=True)
        geometry_by_stop = feed.build_geometry_by_stop(use_utm=True)
        m_to_dist = hp.get_convert_dist("m", feed.dist_units)

        def compute_dist(group):
            """
            Return the distance traveled along the trip between the
            first and last stops.
            If that distance is negative or if the trip's linestring
            intersects itfeed, then return the length of the trip's
            linestring instead.
            """
            shape = group["shape_id"].iat[0]
            try:
                # Get the linestring for this trip
                linestring = geometry_by_shape[shape]
            except KeyError:
                # Shape ID is NaN or doesn't exist in shapes.
                # No can do.
                return np.nan

            # If the linestring intersects itfeed, then that can cause
            # errors in the computation below, so just
            # return the length of the linestring as a good approximation
            D = linestring.length
            if not linestring.is_simple:
                return D

            # Otherwise, return the difference of the distances along
            # the linestring of the first and last stop
            start_stop = group["stop_id"].iat[0]
            end_stop = group["stop_id"].iat[-1]
            try:
                start_point = geometry_by_stop[start_stop]
                end_point = geometry_by_stop[end_stop]
            except KeyError:
                # One of the two stop IDs is NaN, so just
                # return the length of the linestring
                return D
            d1 = linestring.project(start_point)
            d2 = linestring.project(end_point)
            d = d2 - d1
            if 0 < d < D + 100:
                return d
            else:
                # Something is probably wrong, so just
                # return the length of the linestring
                return D

        h["distance"] = g.apply(compute_dist)
        # Convert from meters
        h["distance"] = h["distance"].map(m_to_dist)
    else:
        h["distance"] = np.nan

    # Reset index and compute final stats
    h = h.reset_index()
    h["speed"] = h["distance"] / h["duration"]
    h[["start_time", "end_time"]] = h[["start_time", "end_time"]].applymap(
        lambda x: hp.timestr_to_seconds(x, inverse=True)
    )

    return h.sort_values(["route_id", "direction_id", "start_time"])


def locate_trips(feed, date, times):
    """
    Return the positions of all trips active on the
    given date and times

    Parameters
    ----------
    feed : Feed
    date : string
        YYYYMMDD date string
    times : list
        HH:MM:SS time strings, possibly with HH > 23

    Returns
    -------
    DataFrame
        Columns are:

        - ``'trip_id'``
        - ``'route_id'``
        - ``'direction_id'``
        - ``'time'``
        - ``'rel_dist'``: number between 0 (start) and 1 (end) indicating
          the relative distance of the trip along its path
        - ``'lon'``: longitude of trip at given time
        - ``'lat'``: latitude of trip at given time

        Assume ``feed.stop_times`` has an accurate
        ``shape_dist_traveled`` column.

    Notes
    -----
    Assume the following feed attributes are not ``None``:

    - ``feed.trips``
    - Those used in :func:`.stop_times.get_stop_times`
    - Those used in :func:`.shapes.build_geometry_by_shape`

    """
    if not hp.is_not_null(feed.stop_times, "shape_dist_traveled"):
        raise ValueError(
            "feed.stop_times needs to have a non-null shape_dist_traveled "
            "column. You can create it, possibly with some inaccuracies, "
            "via feed2 = feed.append_dist_to_stop_times()."
        )

    # Start with stop times active on date
    f = feed.get_stop_times(date)
    f["departure_time"] = f["departure_time"].map(hp.timestr_to_seconds)

    # Compute relative distance of each trip along its path
    # at the given time times.
    # Use linear interpolation based on stop departure times and
    # shape distance traveled.
    geometry_by_shape = feed.build_geometry_by_shape(use_utm=False)
    sample_times = np.array([hp.timestr_to_seconds(s) for s in times])

    def compute_rel_dist(group):
        dists = sorted(group["shape_dist_traveled"].values)
        times = sorted(group["departure_time"].values)
        ts = sample_times[
            (sample_times >= times[0]) & (sample_times <= times[-1])
        ]
        ds = np.interp(ts, times, dists)
        return pd.DataFrame({"time": ts, "rel_dist": ds / dists[-1]})

    # return f.groupby('trip_id', group_keys=False).\
    #   apply(compute_rel_dist).reset_index()
    g = f.groupby("trip_id").apply(compute_rel_dist).reset_index()

    # Delete extraneous multi-index column
    del g["level_1"]

    # Convert times back to time strings
    g["time"] = g["time"].map(lambda x: hp.timestr_to_seconds(x, inverse=True))

    # Merge in more trip info and
    # compute longitude and latitude of trip from relative distance
    h = pd.merge(
        g, feed.trips[["trip_id", "route_id", "direction_id", "shape_id"]]
    )
    if not h.shape[0]:
        # Return a DataFrame with the promised headers but no data.
        # Without this check, result below could be an empty DataFrame.
        h["lon"] = pd.Series()
        h["lat"] = pd.Series()
        return h

    def get_lonlat(group):
        shape = group["shape_id"].iat[0]
        linestring = geometry_by_shape[shape]
        lonlats = [
            linestring.interpolate(d, normalized=True).coords[0]
            for d in group["rel_dist"].values
        ]
        group["lon"], group["lat"] = zip(*lonlats)
        return group

    return h.groupby("shape_id").apply(get_lonlat)


def trip_to_geojson(feed, trip_id, *, include_stops=False):
    """
    Return a GeoJSON representation of the given trip, optionally with
    its stops.

    Parameters
    ----------
    feed : Feed
    trip_id : string
        ID of trip in ``feed.trips``
    include_stops : boolean

    Returns
    -------
    dictionary
        A (decoded) GeoJSON FeatureCollection comprising a Linestring
        feature representing the trip's shape.
        If ``include_stops``, then also include one Point feature for
        each stop  visited by the trip.
        The Linestring feature will contain as properties all the
        columns in ``feed.trips`` pertaining to the given trip,
        and each Point feature will contain as properties all the
        columns in ``feed.stops`` pertaining to the stop,
        except the ``stop_lat`` and ``stop_lon`` properties.

        Return the empty dictionary if the trip has no shape.

    """
    # Get the relevant shapes
    t = feed.trips.copy()
    t = t[t["trip_id"] == trip_id].copy()
    shid = t["shape_id"].iat[0]
    geometry_by_shape = feed.build_geometry_by_shape(
        use_utm=False, shape_ids=[shid]
    )

    if not geometry_by_shape:
        return {}

    features = [
        {
            "type": "Feature",
            "properties": json.loads(t.to_json(orient="records"))[0],
            "geometry": sg.mapping(sg.LineString(geometry_by_shape[shid])),
        }
    ]

    if include_stops:
        # Get relevant stops and geometrys
        s = feed.get_stops(trip_id=trip_id)
        cols = set(s.columns) - set(["stop_lon", "stop_lat"])
        s = s[list(cols)].copy()
        stop_ids = s["stop_id"].tolist()
        geometry_by_stop = feed.build_geometry_by_stop(stop_ids=stop_ids)
        features.extend(
            [
                {
                    "type": "Feature",
                    "properties": json.loads(
                        s[s["stop_id"] == stop_id].to_json(orient="records")
                    )[0],
                    "geometry": sg.mapping(geometry_by_stop[stop_id]),
                }
                for stop_id in stop_ids
            ]
        )

    return {"type": "FeatureCollection", "features": features}


def map_trips(
    feed, trip_ids, color_palette=cs.COLORS_SET2, *, include_stops=True
):
    """
    Return a Folium map showing the given trips and (optionally)
    their stops.

    Parameters
    ----------
    feed : Feed
    trip_ids : list
        IDs of trips in ``feed.trips``
    color_palette : list
        Palette to use to color the routes. If more routes than colors,
        then colors will be recycled.
    include_stops : boolean
        If ``True``, then include stops in the map

    Returns
    -------
    dictionary
        A Folium Map depicting the shapes of the trips.
        If ``include_stops``, then include the stops for each trip.

    Notes
    ------
    - Requires Folium

    """
    import folium as fl
    import folium.plugins as fp

    # Get routes slice and convert to dictionary
    trips = (
        feed.trips.loc[lambda x: x["trip_id"].isin(trip_ids)]
        .fillna("n/a")
        .to_dict(orient="records")
    )

    # Create colors
    n = len(trips)
    colors = [color_palette[i % len(color_palette)] for i in range(n)]

    # Initialize map
    my_map = fl.Map(tiles="cartodbpositron")

    # Collect route bounding boxes to set map zoom later
    bboxes = []

    # Create a feature group for each route and add it to the map
    for i, trip in enumerate(trips):
        collection = feed.trip_to_geojson(
            trip_id=trip["trip_id"], include_stops=include_stops
        )
        group = fl.FeatureGroup(name="Trip " + trip["trip_id"])
        color = colors[i]

        for f in collection["features"]:
            prop = f["properties"]

            # Add stop
            if f["geometry"]["type"] == "Point":
                lon, lat = f["geometry"]["coordinates"]
                fl.CircleMarker(
                    location=[lat, lon],
                    radius=8,
                    fill=True,
                    color=color,
                    weight=1,
                    popup=fl.Popup(hp.make_html(prop)),
                ).add_to(group)

            # Add path
            else:
                # Path
                prop["color"] = color
                path = fl.GeoJson(
                    f,
                    name=trip,
                    style_function=lambda x: {
                        "color": x["properties"]["color"]
                    },
                )
                path.add_child(fl.Popup(hp.make_html(prop)))
                path.add_to(group)

                # Direction arrows, assuming, as GTFS does, that
                # trip direction equals LineString direction
                fp.PolyLineTextPath(
                    path,
                    "        \u27A4        ",
                    repeat=True,
                    offset=5.5,
                    attributes={"fill": color, "font-size": "18"},
                ).add_to(group)

                bboxes.append(sg.box(*sg.shape(f["geometry"]).bounds))

        group.add_to(my_map)

    fl.LayerControl().add_to(my_map)

    # Fit map to bounds
    bounds = so.unary_union(bboxes).bounds
    bounds2 = [bounds[1::-1], bounds[3:1:-1]]  # Folium expects this ordering
    my_map.fit_bounds(bounds2)

    return my_map
