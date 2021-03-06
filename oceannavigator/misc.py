import os
from oceannavigator import app
from pykml import parser
from shapely.geometry.polygon import LinearRing
from netCDF4 import Dataset, chartostring, netcdftime
import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.multipolygon import MultiPolygon
from thredds_crawler.crawl import Crawl
import datetime
import pyproj
from operator import itemgetter
from oceannavigator.util import (
    get_dataset_url, get_variable_name,
    get_variable_unit, get_dataset_climatology
)
import re
from data import open_dataset


def list_kml_files(subdir):
    DIR = os.path.join(app.config['OVERLAY_KML_DIR'], subdir)

    files = []
    for f in os.listdir(DIR):
        if not f.endswith(".kml"):
            continue

        doc = parser.parse(os.path.join(DIR, f)).getroot()
        folder = doc.Document.Folder

        entry = {
            'name': folder.name.text.encode("utf-8"),
            'id': f[:-4]
        }

        files.append(entry)

    return sorted(files, key=itemgetter('name'))


def _get_view(extent):
    extent = map(float, extent.split(","))
    view = LinearRing([
        (extent[1], extent[0]),
        (extent[3], extent[0]),
        (extent[3], extent[2]),
        (extent[1], extent[2])
    ])
    return view


def _get_kml(subdir, file_id):
    DIR = os.path.join(app.config['OVERLAY_KML_DIR'], subdir)
    f = os.path.join(DIR, "%s.kml" % file_id)
    doc = parser.parse(f).getroot()
    return doc.Document.Folder, {"k": doc.nsmap[None]}


def points(file_id, projection, resolution, extent):
    proj = pyproj.Proj(init=projection)
    view = _get_view(extent)
    folder, nsmap = _get_kml('point', file_id)
    points = []

    for place in folder.Placemark:
        c_txt = place.Point.coordinates.text
        lonlat = map(float, c_txt.split(','))

        x, y = proj(lonlat[0], lonlat[1])
        p = Point(y, x)

        if view.envelope.intersects(p):
            points.append({
                'type': "Feature",
                'geometry': {
                    'type': "Point",
                    'coordinates': lonlat,
                },
                'properties': {
                    'name': place.name.text.encode("utf-8"),
                    'type': 'point',
                    'resolution': 0,
                }
            })

    result = {
        'type': "FeatureCollection",
        'features': points,
    }
    return result


def lines(file_id, projection, resolution, extent):
    proj = pyproj.Proj(init=projection)
    view = _get_view(extent)
    folder, nsmap = _get_kml('line', file_id)

    lines = []

    for place in folder.Placemark:
        c_txt = place.LineString.coordinates.text
        coords = []
        for point_txt in c_txt.split():
            lonlat = point_txt.split(',')
            coords.append(map(float, lonlat))

        coords = np.array(coords)

        x, y = proj(coords[:, 0], coords[:, 1])
        ls = LineString(zip(y, x))

        if view.envelope.intersects(ls):
            lines.append({
                'type': "Feature",
                'geometry': {
                    'type': "LineString",
                    'coordinates': coords.astype(float).tolist()
                },
                'properties': {
                    'name': place.name.text.encode("utf-8"),
                    'type': 'line',
                    'resolution': 0,
                }
            })

    result = {
        'type': "FeatureCollection",
        'features': lines,
    }
    return result


def list_areas(file_id, simplify=True):
    AREA_DIR = os.path.join(app.config['OVERLAY_KML_DIR'], 'area')

    areas = []
    f = os.path.join(AREA_DIR, "%s.kml" % file_id)

    doc = parser.parse(f).getroot()
    folder = doc.Document.Folder
    nsmap = {"k": doc.nsmap[None]}

    def get_coords(path):
        result = []
        for c in place.iterfind(path, nsmap):
            tuples = c.coordinates.text.split(' ')
            coords = []
            for tup in tuples:
                tup = tup.strip()
                if not tup:
                    continue
                lonlat = tup.split(',')
                coords.append([float(lonlat[1]), float(lonlat[0])])

            if simplify:
                coords = list(LinearRing(coords).simplify(1.0 / 32).coords)

            result.append(coords)

        return result

    for place in folder.Placemark:
        outers = get_coords('.//k:outerBoundaryIs//k:LinearRing')
        inners = get_coords('.//k:innerBoundaryIs//k:LinearRing')

        centroids = [LinearRing(x).centroid for x in outers]
        areas.append({
            'name': place.name.text.encode("utf-8"),
            'polygons': outers,
            'innerrings': inners,
            'centroids': [(c.y, c.x) for c in centroids],
            'key': file_id + "/" + place.name.text.encode("utf-8"),
        })

    areas = sorted(areas, key=lambda k: k['name'])
    return areas


def areas(area_id, projection, resolution, extent):
    folder, nsmap = _get_kml('area', area_id)

    proj = pyproj.Proj(init=projection)
    view = _get_view(extent)
    areas = []

    for place in folder.Placemark:
        polys = []

        for p in place.iterfind('.//k:Polygon', nsmap):
            lonlat = np.array(
                map(
                    lambda c: c.split(','),
                    p.outerBoundaryIs.LinearRing.coordinates.text.split()
                )
            ).astype(float)
            ox, oy = proj(lonlat[:, 0], lonlat[:, 1])

            holes = []
            for i in p.iterfind('.//k:innerBoundaryIs/k:LinearRing', nsmap):
                lonlat_inner = np.array(
                    map(
                        lambda c: c.split(','),
                        i.coordinates.text.split()
                    )
                ).astype(float)
                ix, iy = proj(lonlat_inner[:, 0], lonlat_inner[:, 1])
                holes.append(zip(iy, ix))

            polys.append(Polygon(zip(oy, ox), holes))

        mp = MultiPolygon(polys).simplify(resolution * 1.5)

        def get_coordinates(poly):
            out = np.array(poly.exterior.coords)
            out = np.array(proj(out[:, 1], out[:, 0],
                                inverse=True)).transpose().tolist()
            coords = [out]
            for i in poly.interiors:
                inn = np.array(i.coords)
                coords.append(
                    np.array(proj(inn[:, 0], inn[:, 1],
                             inverse=True)).transpose().tolist())
            return coords

        if view.envelope.intersects(mp):
            coordinates = []
            if isinstance(mp, MultiPolygon):
                for p in mp.geoms:
                    coordinates.append(get_coordinates(p))
            else:
                coordinates.append(get_coordinates(mp))

            areas.append({
                'type': "Feature",
                'geometry': {
                    'type': "MultiPolygon",
                    'coordinates': coordinates,
                },
                'properties': {
                    'name': place.name.text.encode("utf-8"),
                    'type': "area",
                    'resolution': resolution,
                    'key': "%s/%s" % (area_id,
                                      place.name.text.encode("utf-8")),
                    'centroid': proj(mp.centroid.y, mp.centroid.x,
                                     inverse=True),
                },
            })

    result = {
        'type': "FeatureCollection",
        'features': areas,
    }

    return result


def drifter_meta():
    imei = {}
    wmo = {}
    deployment = {}

    with Dataset(app.config['DRIFTER_AGG_URL'], 'r') as ds:
        for idx, b in enumerate(ds.variables['buoy'][:]):
            bid = str(chartostring(b))[:-3]

            for data, key in [
                [imei, 'imei'],
                [wmo, 'wmo'],
                [deployment, 'deployment']
            ]:
                d = str(chartostring(ds.variables[key][idx][0]))
                if data.get(d) is None:
                    data[d] = [bid]
                else:
                    data[d].append(bid)

    return {
        'imei': imei,
        'wmo': wmo,
        'deployment': deployment,
    }


def observation_vars():
    result = []
    with Dataset(app.config["OBSERVATION_AGG_URL"], 'r') as ds:
        for v in sorted(ds.variables):
            if v in ['z', 'lat', 'lon', 'profile', 'time']:
                continue
            var = ds[v]
            if var.datatype == '|S1':
                continue

            result.append(var.long_name)
    return result


def observation_meta():
    with Dataset(app.config["OBSERVATION_AGG_URL"], 'r') as ds:
        ship = chartostring(ds['ship'][:])
        trip = chartostring(ds['trip'][:])

        data = {
            'ship': sorted(np.unique(ship).tolist()),
            'trip': sorted(np.unique(trip).tolist()),
        }

        return data


def observations(observation_id, projection, resolution, extent):
    selected_ships = None
    selected_trips = None
    for i in observation_id.split(";"):
        k, v = i.split(":")
        if k == "ship":
            selected_ships = v.split(",")
        elif k == "trip":
            selected_trips = v.split(",")

    proj = pyproj.Proj(init=projection)
    view = _get_view(extent)

    points = []
    with Dataset(app.config["OBSERVATION_AGG_URL"], 'r') as ds:
        lat = ds['lat'][:].astype(float)
        lon = ds['lon'][:].astype(float)
        profile = chartostring(ds['profile'][:])
        ship = None
        if 'ship' in ds.variables:
            ship = chartostring(ds['ship'][:])
            trip = chartostring(ds['trip'][:])
            cast = chartostring(ds['cast'][:])
            profile = np.array(
                ["%s %s %s" % tuple(stc)
                 for stc in np.array([ship,
                                      trip,
                                      cast
                                      ]).transpose()
                 ])

    for idx, name in enumerate(profile):
        x, y = proj(lon[idx], lat[idx])
        p = Point(y, x)

        if ship is not None:
            if selected_ships is not None and ship[idx] not in selected_ships:
                continue
            if selected_trips is not None and trip[idx] not in selected_trips:
                continue

        if view.envelope.intersects(p):
            points.append({
                'type': "Feature",
                'geometry': {
                    'type': "Point",
                    'coordinates': [lon[idx], lat[idx]]
                },
                'properties': {
                    'name': str(profile[idx]),
                    'observation': idx,
                    'type': 'point',
                    'resolution': 0,
                }
            })

    result = {
        'type': "FeatureCollection",
        'features': points,
    }
    return result


def drifters(drifter_id, projection, resolution, extent):
    buoy_id = []
    lat = []
    lon = []
    status = []

    if drifter_id in ['all', 'active', 'inactive', 'not responding']:
        c = Crawl(app.config['DRIFTER_CATALOG_URL'], select=[".*.nc$"])
        drifters = [d.name[:-3] for d in c.datasets]
    else:
        drifters = drifter_id.split(",")

    for d in drifters:
        with Dataset(app.config["DRIFTER_URL"] % d, 'r') as ds:
            if drifter_id == 'active' and ds.status != 'normal':
                continue
            elif drifter_id == 'inactive' and ds.status != 'inactive':
                continue
            elif drifter_id == 'not responding' and \
                    ds.status != 'not responding':
                continue
            buoy_id.append(ds.buoyid)
            lat.append(ds['latitude'][:])
            lon.append(ds['longitude'][:])
            status.append(ds.status)

    proj = pyproj.Proj(init=projection)
    view = _get_view(extent)

    res = []
    for i, bid in enumerate(buoy_id):
        x, y = proj(lon[i], lat[i])

        ls = LineString(zip(y, x))
        if view.envelope.intersects(ls):
            path = np.array(ls.simplify(resolution * 1.5).coords)
            path = np.array(
                proj(path[:, 1], path[:, 0], inverse=True)).transpose()

            res.append({
                'type': "Feature",
                'geometry': {
                    'type': "LineString",
                    'coordinates': path.astype(float).tolist()
                },
                'properties': {
                    'name': bid,
                    'status': status[i],
                    'type': "drifter",
                    'resolution': resolution,
                }
            })

    result = {
        'type': "FeatureCollection",
        'features': res,
    }

    return result


def drifters_vars(drifter_id):
    drifters = drifter_id.split(",")

    res = []
    for d in drifters:
        with Dataset(app.config["DRIFTER_URL"] % d, 'r') as ds:
            a = []
            for name in ds.variables:
                if name in ["data_date", "sent_date", "received_date",
                            "latitude", "longitude"]:
                    continue

                if ds.variables[name].datatype == np.dtype("S1"):
                    continue

                var_info = {
                    'id': name,
                }
                if 'long_name' in ds.variables[name].ncattrs():
                    var_info['value'] = ds.variables[name].long_name
                else:
                    var_info['value'] = name

                a.append(var_info)

            res.append(a)

    if len(res) > 1:
        intersect = res[0]
        for i in range(1, len(res)):
            intersect = filter(lambda x: x in intersect, res[i])

        return sorted(intersect, key=lambda k: k['value'])
    elif len(res) == 1:
        return sorted(res[0], key=lambda k: k['value'])
    else:
        return []


def drifters_time(drifter_id):
    drifters = drifter_id.split(",")

    mins = []
    maxes = []
    for d in drifters:
        with Dataset(app.config["DRIFTER_URL"] % d, 'r') as ds:
            var = ds['data_date']
            ut = netcdftime.utime(var.units)
            mins.append(ut.num2date(var[:].min()))
            maxes.append(ut.num2date(var[:].max()))

    min_time = np.amin(mins)
    max_time = np.amax(maxes)

    return {
        'min': min_time.isoformat(),
        'max': max_time.isoformat(),
    }


def list_class4_files():
    c = Crawl(app.config["CLASS4_CATALOG_URL"], select=[".*_GIOPS_.*.nc$"])

    result = []
    for dataset in c.datasets:
        value = dataset.name[:-3]
        date = datetime.datetime.strptime(value.split("_")[1], "%Y%m%d")
        result.append({
            'name': date.strftime("%Y-%m-%d"),
            'id': value
        })

    return result


def list_class4(d):
    dataset_url = app.config["CLASS4_URL"] % d

    with Dataset(dataset_url, 'r') as ds:
        lat = ds['latitude'][:]
        lon = ds['longitude'][:]
        ids = map(str.strip, chartostring(ds['id'][:]))
        rmse = []

        for i in range(0, lat.shape[0]):
            best = ds['best_estimate'][i, 0, :]
            obsv = ds['observation'][i, 0, :]
            rmse.append(np.ma.sqrt(((best - obsv) ** 2).mean()))

    rmse = np.ma.hstack(rmse)
    maxval = rmse.mean() + 2 * rmse.std()
    rmse_norm = rmse / maxval

    loc = zip(lat, lon)

    points = []
    for idx, ll in enumerate(loc):
        if np.ma.is_masked(rmse[idx]):
            continue
        points.append({
            'name': "%s" % ids[idx],
            'loc': "%f,%f" % ll,
            'id': "%s/%d" % (d, idx),
            'rmse': float(rmse[idx]),
            'rmse_norm': float(rmse_norm[idx]),
        })
        points = sorted(points, key=lambda k: k['id'])

    return points


def class4(class4_id, projection, resolution, extent):
    dataset_url = app.config["CLASS4_URL"] % class4_id

    proj = pyproj.Proj(init=projection)
    view = _get_view(extent)

    rmse = []
    lat = []
    lon = []
    point_id = []
    identifiers = []
    with Dataset(dataset_url, 'r') as ds:
        lat_in = ds['latitude'][:]
        lon_in = ds['longitude'][:]
        ids = map(str.strip, chartostring(ds['id'][:]))

        for i in range(0, lat_in.shape[0]):
            x, y = proj(lon_in[i], lat_in[i])
            p = Point(y, x)
            if view.envelope.intersects(p):
                lat.append(float(lat_in[i]))
                lon.append(float(lon_in[i]))
                identifiers.append(ids[i])
                best = ds['best_estimate'][i, 0, :]
                obsv = ds['observation'][i, 0, :]
                point_id.append(i)
                rmse.append(np.ma.sqrt(((best - obsv) ** 2).mean()))

    rmse = np.ma.hstack(rmse)
    rmse_norm = np.clip(rmse / 1.5, 0, 1)

    loc = zip(lon, lat)

    points = []

    for idx, ll in enumerate(loc):
        if np.ma.is_masked(rmse[idx]):
            continue
        points.append({
            'type': "Feature",
            'geometry': {
                'type': "Point",
                'coordinates': ll,
            },
            'properties': {
                'name': "%s" % identifiers[idx],
                'id': "%s/%d" % (class4_id, point_id[idx]),
                'error': float(rmse[idx]),
                'error_norm': float(rmse_norm[idx]),
                'type': 'class4',
                'resolution': 0,
            },
        })

    result = {
        'type': "FeatureCollection",
        'features': points,
    }

    return result


def list_class4_forecasts(class4_id):
    dataset_url = app.config["CLASS4_URL"] % class4_id
    with Dataset(dataset_url, 'r') as ds:
        var = ds['modeljuld']
        forecast_date = [d.strftime("%d %B %Y") for d in
                         netcdftime.utime(var.units).num2date(var[:])]

    res = [{
        'id': 'best',
        'name': 'Best Estimate',
    }]

    if len(set(forecast_date)) > 1:
        for idx, date in enumerate(forecast_date):
            if res[-1]['name'] == date:
                continue
            res.append({
                'id': idx,
                'name': date
            })

    return res


def list_class4_models(class4_id):
    select = ["(.*/)?%s.*_profile.nc$" % class4_id[:16]]
    c = Crawl(app.config["CLASS4_CATALOG_URL"], select=select)

    result = []
    for dataset in c.datasets:
        value = dataset.name[:-3]
        model = value.split("_")[2]
        if model != "GIOPS":
            result.append({
                'value': value.split("_")[2],
                'id': value
            })

    return result


def get_point_data(dataset, variable, time, depth, location):
    variables_anom = variable.split(",")
    variables = [re.sub('_anom$', '', v) for v in variables_anom]

    data = []
    names = []
    units = []
    with open_dataset(get_dataset_url(dataset)) as ds:
        timestamp = ds.timestamps[time]

        for v in variables:
            d = ds.get_point(
                location[0],
                location[1],
                depth,
                time,
                v
            )
            variable_name = get_variable_name(dataset, ds.variables[v])
            variable_unit = get_variable_unit(dataset, ds.variables[v])

            if variable_unit.startswith("Kelvin"):
                variable_unit = "Celsius"
                d = np.add(d, -273.15)

            data.append(d)
            names.append(variable_name)
            units.append(variable_unit)

    if variables != variables_anom:
        with open_dataset(get_dataset_climatology(dataset)) as ds:
            for idx, v in enumerate(variables):
                d = ds.get_point(
                    location[0],
                    location[1],
                    depth,
                    timestamp.month,
                    v
                )

                data[idx] = data[idx] - d
                names[idx] = names[idx] + " Anomaly"

    result = {
        'value': map(lambda f: '%s' % float('%.4g' % f), data),
        'location': map(lambda f: round(f, 4), location),
        'name': names,
        'units': units,
    }
    return result
