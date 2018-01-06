#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  views.py


from flask import Blueprint, request, jsonify, current_app
from models import db, TvSeason, TvSeries, TvEpisode, DownloadLink
import json, threading, os, redis
from datetime import date, timedelta


cache_pass, port_number = os.environ.get('redis_pass'), int(os.environ.get('redis_port'))
data_cache = redis.StrictRedis(password=cache_pass, port=port_number)


ERROR, SUCCESS = (0, 1)
main_api = Blueprint('main_api', __name__)

def respond_back(message_code, message_detail):
    return jsonify({'status': message_code, 'detail': message_detail})


def error_response(message):
    return respond_back(ERROR, message)


def success_response(message):
    return respond_back(SUCCESS, message)


@main_api.route('/get_series')
def get_series_handler():
    all_series = db.session.query(TvSeries).order_by(TvSeries.title.asc()).all()
    tv_series = [{'id': show.id, 'title': show.title } for show in all_series]
    return success_response(tv_series)


@main_api.route('/get_seasons')
def get_seasons_handler():
    show_id = request.args.get('show_id')
    try:
        if show_id is None or len(show_id) < 0:
            return error_response('Invalid Show ID')
        show_id = long(show_id)
    except ValueError as val_error:
        print val_error
        return error_response('Show ID isn\'t a valid integer number')
    show = db.session.query(TvSeries).filter_by(id=show_id).first()
    if show is None:
        return error_response('Show does not exist')
    seasons = [ {'id': season.id, 'name': season.title } for season in show.seasons ]
    return success_response(seasons)
    

@main_api.route('/get_episodes')
def get_episodes_handler():
    season_id = request.args.get('season_id')
    try:
        if season_id is None or len(season_id) < 0:
            return error_response('Invalid season ID')
        season_id = long(season_id)
    except ValueError as val_error:
        print val_error
        return error_response('Season ID isn\'t a valid integer number')
    season = db.session.query(TvSeason).filter_by(id=season_id).first()
    if season is None:
        return error_response('No result found')
    episodes = []
    for episode in season.episodes:
        download_links = [ { 'type': dl.download_type, 'link': dl.link } for dl in episode.download_links ]
        episodes.append({ 'name': episode.title, 'id': episode.id, 'links': download_links })
    return success_response(episodes)


def get_updates(the_date):
    table_key = 'orn:releases-' + str(the_date)
    todays_releases = data_cache.hkeys(table_key)
    results = []
    for release in todays_releases:
        data = json.loads(data_cache.hget(table_key, release))
        results.append(data)
    return success_response(results)


@main_api.route('/todays_updates')
def get_todays_updates_handler():
    return get_updates(date.today())


@main_api.route('/updates')
def get_updates_handler():
    days_ago = request.args.get('number')
    try:
        if days_ago is None or len(days_ago) < 0:
            return error_response('Invalid number of days')
        days_ago = long(days_ago)
    except ValueError as val_error:
        print val_error
        return error_response('Days isn\'t a valid integer number')
    the_date = date.today() - timedelta(days_ago)
    return get_updates(the_date)
