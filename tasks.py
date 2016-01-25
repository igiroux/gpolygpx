# -*- coding: utf-8 -*-
from __future__ import print_function
import requests
import random
from os.path import join, splitext, dirname, basename
import os
import sys
import logging
from bisect import bisect
from haversine import haversine
from collections import defaultdict
try:
    # python 3
    from urllib.parse import parse_qs
except ImportError:
    # python 2
    from urlparse import parse_qs, urlparse

from invoke import task
from glob import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from polyline.codec import PolylineCodec
import gpxpy.gpx

import fiona
from shapely.geometry import LineString, mapping


def split_url(url, param_filter=None):
    '''
    >>> url = http://server.domain.org/path/to/resource?a=x&b=y&c=z
    >>> h, p, q = split_url(url)
    >>> print(h)
    http://server.domain.org
    ...
    >>> print(p)
    /path/to/resource
    ...
    >>> print('&'.join('{k}={v}'.format(k=k, v=v) for k, v in q.items()))
    a=x&b=y&c=z
    '''

    param_filter = param_filter or (lambda _: True)

    url_object = urlparse(url)
    query_dict = {key: value[0] for key, value in parse_qs(url_object.query).items() if param_filter(key)}
    host = url_object._replace(query=None, path='').geturl()
    path = url_object.path
    return host, path, query_dict


@task(name='sample')
def create_sample_url(ifname, tag='sample', repartition="50,150,300,600", count=250, pattern=None):
    def predicate(url):
        return pattern in url if pattern else True

    def complete_url(url):
        keys = {'from', 'to', 'rb.veh', 'transport_mode'}
        _, path, query_dict = split_url(url, param_filter=lambda x: x in keys)
        query = '&'.join('{k}={v}'.format(k=key, v=value) for key, value in query_dict.items())

        return '{path}?{query}&wt=json&clientid=mappy'.format(path=path, query=query)

    Infinity = float('+Infinity')
    kms = [0, ] + sorted(map(int, repartition.split(','))) + [Infinity, ]
    kms_range = zip(kms[0:-1], kms[1:])

    def classify(url):
        _, _, query = split_url(url)
        start, end = [map(float, query[key].split(',')) for key in 'from', 'to']
        d = haversine(start, end)
        return kms_range[bisect(kms, d) - 1]

    def subsample_sz(population, cat, sample_sz):
        pop_sz = sum(map(len, population.values()))
        return max(round(float(len(population[cat])) / pop_sz * sample_sz), sample_sz/(len(kms)-2))

    urls = defaultdict(list)
    filtered_urls = map(complete_url, filter(predicate, open(ifname)))
    n_urls = len(filtered_urls)
    for url in filtered_urls:
        key = classify(url)
        urls[key].append(url)

    fname, extension = splitext(ifname)
    for r, r_url in urls.items():
        n = int(subsample_sz(urls, r, count))
        ofname = '{fname}-{tag}-{}_{}-{n}{extension}'.format(*r, **locals())

        with open(ofname, 'wb') as ofile:
            ofile.write('\n'.join(random.sample(r_url, n)))
        print(ofname)


def get_item(json_response, item_path):
    '''
    >>> d = {
    ...     'a': {
    ...         'b': [
    ...             {'c': 'value_ab0c', 'd': 'value_ab0d'},
    ...             {'c': 'value_ab1c', , 'd': 'value_ab1d'},
    ...         ],
    ...     },
    ... }
    >>> assert get_item(d, 'a/b/1/d') == 'value_ab1d'
    >>> assert get_item(d, 'a/b/0/d') == 'value_ab0d'
    '''
    try:
        value = reduce(lambda d, k: d[k], item_path.split('/'), json_response)
    except KeyError:
        value = None

    return value


def format_coord(xy_str, isep=',', osep='_'):
    """Formats coordinates
    """
    x, y = map(float, xy_str.split(isep))
    xy_dict = {'x': x, 'y': y}

    def fmt(value, kind='x'):
        assert kind in xy_dict.keys()
        return {
            'x': ['W{}', 'E{}'],
            'y': ['S{}', 'N{}']
        }[kind][value >= 0].format(abs(value))

    return osep.join(fmt(xy_dict[k], kind=k) for k in sorted(xy_dict.keys()))


def parse_coords(coords_str, sep='_'):
    '''
    >>> coords_str = N14.604398_W61.066889
    >>> assert from_formatted_coords(coords_str) == (-61.066889, 14.604398)
    '''
    def x_xs(seq):
        return seq[0], seq[1:]

    def sign(identity):
        return [-1, +1][identity in ('N', 'E')]

    def kind(identity):
        return ['x', 'y'][identity in ('N', 'S')]

    coords = {kind(identity): sign(identity) * value for identity, value in map(x_xs, coords_str.split(sep))}

    return coords['x'], coords['y']


@task(name='gpoly')
def get_route_gpolyline(url, output_dir=None, host='http://routemm.mappyrecette.net'):
    """
    """

    output_dir = output_dir or os.getcwd()
    abs_url = host + url

    try:
        response = requests.get(abs_url).json()
    except Exception, e:
        logging.error(
            '\n`--> url {abs_url}'
            '`\n`--> response {response}'
            .format(**locals()))
        sys.exit(1)

    _, _, query = split_url(abs_url)
    start, end = [format_coord(query[key]) for key in 'from', 'to']
    # ofname = join(output_dir, 'from__{start}__to__{end}.gpoly'.format(**locals()))  # FIXME
    ofname = join(output_dir, 'from__{start}__to__{end}.json'.format(**locals()))
    with open(ofname, 'wb') as ofile:
        # ofile.write(poly)  # FIXME
        json.dump(response, ofile, indent=4)

    print(ofname)


def GpxRoute(author='Ismaila Giroux', email='ismaila.giroux@gmail.com'):
    '''
    '''

    gpx = gpxpy.gpx.GPX()
    gpx.author_email = email
    gpx.author_name = author
    return gpx


def new_gpx_route(xy_list, **kwargs):

    # Create first track in our GPX:
    gpx_route = gpxpy.gpx.GPXRoute(**kwargs)

    # Create points:
    add_point = gpx_route.points.append
    GPXRoutePoint = gpxpy.gpx.GPXRoutePoint
    for x, y in xy_list:
        add_point(GPXRoutePoint(x, y))

    return gpx_route


def get_content(fname):
    return json.load(open(fname))


@task(name='gpx')
def gpoly2gpx(ifname, output_dir=None, json_path='routes/route/polyline-definition/polyline'):
    response = get_content(ifname)
    pcodec = PolylineCodec()
    item = get_item(response, json_path)
    if item is None:

        logging.error(
            'Bad input from file {ifname}'
            '`\n`--> response {response}'
            .format(**locals()))
        sys.exit(1)

    polyxy = pcodec.decode(item)
    gpx = GpxRoute()
    gpx_route = new_gpx_route(polyxy)
    gpx.routes.append(gpx_route)

    fname, extension = splitext(ifname)
    output_dir = output_dir or dirname(fname)
    ofname = join(output_dir, '{}.gpx'.format(basename(fname)))
    with open(ofname, 'wb') as ofile:
        ofile.write(gpx.to_xml())

    print(ofname)


@task(name='shp')
def gpoly2shp(
    ifname, ofname=None,
    geom_path='routes/route/polyline-definition/polyline',
    time_path='routes/route/summary/time',
    length_path='routes/route/summary/length',
):
    response = get_content(ifname)
    pcodec = PolylineCodec()
    polyxy = pcodec.decode(get_item(response, geom_path))
    length = int(get_item(response, length_path))
    time = int(get_item(response, time_path))

    schema = {
        'geometry': 'LineString',
        'properties': {
            'seconds': 'int',
            'meters': 'int',
            'x_start': 'float',
            'y_start': 'float',
            'x_end': 'float',
            'y_end': 'float',
            'cat': 'str',
        },
    }

    fname, extension = splitext(ifname)
    ofname = ofname or join(dirname(fname), '{}.shp'.format(basename(fname)))

    with fiona.open(ofname, mode='w', driver='ESRI Shapefile', schema=schema) as lyr:
        lyr.write({
            'geometry': mapping(LineString(polyxy)),
            'properties': {
                'seconds': time,
                'meters': length,
            }
        })

    print(ofname)


@task(name='gpoly2gpx')
def gpolyfiles2gpx(pattern, ofname=None):
    files = glob(pattern)
    gpx = GpxRoute()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures2poly = {pool.submit(get_content, fname): fname for fname in files}
        for future in as_completed(futures2poly):
            fname = futures2poly[future]
            print('Handling %r' % fname)
            if future.exception() is not None:
                print('%r generated an exception: %s' % (fname, future.exception()))
                continue

            pcodec = PolylineCodec()

            polyxy = pcodec.decode(future.result())
            gpx_route = new_gpx_route(polyxy, name=fname)
            gpx.routes.append(gpx_route)

    with open(ofname, 'wb') as ofile:
        ofile.write(gpx.to_xml())

    print(ofname)


@task(name='gpoly2gpx')
def gpolyfiles2shp(pattern, ofname=None):
    files = glob(pattern)
    gpx = GpxRoute()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures2poly = {pool.submit(get_content, fname): fname for fname in files}
        for future in as_completed(futures2poly):
            fname = futures2poly[future]
            print('Handling %r' % fname)
            if future.exception() is not None:
                print('%r generated an exception: %s' % (fname, future.exception()))
                continue

            pcodec = PolylineCodec()

            polyxy = pcodec.decode(future.result())
            gpx_route = new_gpx_route(polyxy, name=fname)
            gpx.routes.append(gpx_route)

    with open(ofname, 'wb') as ofile:
        ofile.write(gpx.to_xml())

    print(ofname)
