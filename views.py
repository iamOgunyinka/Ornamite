#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  views.py


from flask import Blueprint, request, jsonify
from models import db, TvSeason, TvSeries, TvEpisode, DownloadLink
import json

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

@main_api.route('/special')
def special_route():
    reader = open(os.environ.get('FILE_LOC'), 'r')
    result = json.load(reader)
    for tv_series in result:
        show_title = tv_series.get('name')
        seasons = tv_series.get('seasons')
        tv_series = TvSeries(title=show_title)
        for season in seasons:
            season_name = season.get('title')
            season_page_link = season.get('page_link')
            episodes = season.get('episodes')
            tv_season = TvSeason(title=season_name, page_link=season_page_link)
            for episode in episodes:
                episode_name = episode.get('title')
                page_link = episode.get('page_link')
                download_links = episode.get('dl_links')
                tv_episode = TvEpisode(title=episode_name, page_link=page_link)
                for dl_link in download_links:
                    download_type = dl_link.get('type')
                    download_link = dl_link.get('link')
                    tv_episode.download_links.append(DownloadLink(download_type=download_type, link=download_link))
                tv_season.episodes.append(tv_episode)
            tv_series.seasons.append(tv_season)
        db.session.add(tv_series)
    db.session.commit()
    reader.close()
    return success_response(result)
