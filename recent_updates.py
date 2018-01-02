#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  recent_updates.py

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os, requests, redis, json, time
from BeautifulSoup import BeautifulSoup
from datetime import date, datetime, timedelta
from models import TvSeries, TvEpisode, DownloadLink
import threading


cache_pass, port_number = os.environ.get('redis_pass'), int(os.environ.get('redis_port'))
data_cache = redis.StrictRedis(password=cache_pass, port=port_number)

def get_data_or_none(link, callback_on_failure=None):
    try:
        rsp = requests.get(link)
    except Exception as e:
        print 'An exception occurred: {}'.format(e)
        if callback_on_failure:
            callback_on_failure()
        return None
    if not rsp.ok:
        print 'Invalid response gotten from main page, code: {}'.format(rsp.status_code)
        if callback_on_failure:
            callback_on_failure()
        return None
    return rsp

visited_sites = {}


def list_series(link):
    if visited_sites.get(link) is not None:
        return None
    visited_sites[link] = True
    network_response = get_data_or_none(link)
    if network_response is None:
        return None
    parsed_data = BeautifulSoup(network_response.content)
    data_list = parsed_data.findAll('div', attrs={'class': 'data main'})
    today = date.today()
    today_releases = []
    for data_item in data_list:
        bold = data_item.b.string + data_item.b.nextSibling.string
        tv_info = [tv.strip() for tv in bold.split('-')]
        if len(tv_info) < 4:
            continue
        series_name, season_name, episode_name, release_date = (tv_info[0], tv_info[1], tv_info[2], tv_info[-1])
        if release_date.startswith('['):
            release_date = release_date[1:]
        if release_date.endswith(']'):
            release_date = release_date[:-1] + '/' + str(today.year)
        release_date = release_date.split('/')
        try:
            is_todays_release = date(int(release_date[-1]), int(release_date[1]), int(release_date[0])) == today
            if is_todays_release:
                today_releases.append({ 'name': series_name, 'season': season_name, 'episode': episode_name })
        except ValueError:
            continue
    return today_releases

db = SQLAlchemy()

def initialize_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get( 'DB_URL' )
    app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
    db.init_app(app)
    
    return app

app = initialize_app()


@app.before_first_request
def before_any_request():
    db.configure_mappers()
    db.create_all()


def list_link_series(link, post_data_callback, *callback_args, **callback_kw ):
    if visited_sites.get(link) is not None:
        return
    visited_sites[link] = True
    network_response = get_data_or_none(link)
    if network_response is None:
        return
    parsed_data = BeautifulSoup(network_response.content)
    data_list = parsed_data.findAll('div', attrs={'class': 'data'})

    for data_item in data_list:
        ahrefs = data_item.findAll('a')
        for ahref in ahrefs:
            post_data_callback(ahref, *callback_args, **callback_kw)


def dl_link_extractor(ahref_object, *args, **kwargs):
    download_link = ahref_object.attrs[0][1]
    if download_link == '#':
        return
    download_type = ahref_object.string.strip()
    try:
        if kwargs['data'].get('download_links') is None:
            kwargs['data']['download_links'] = []
        kwargs['data']['download_links'].append({'download_type': download_type, 'link': download_link})
        kwargs['episode'].download_links.append(DownloadLink(download_type=download_type, link=download_link))
    except:
        print 'Error'

def add_episode_dlinks(episode_link, current_episode, data):
    list_link_series(episode_link, dl_link_extractor, episode=current_episode, data=data)


def append_episode(ahref, *args, **kwargs):
    expected_episode_name = kwargs['episode'].strip()
    episode_link = ahref.attrs[0][1]
    episode_name = ahref.string.strip()
    if expected_episode_name.lower() == episode_name.lower():
        try:
            new_episode = TvEpisode(title=episode_name, page_link=episode_link)
            add_episode_dlinks(episode_link, new_episode, kwargs['data_info'])
            season = kwargs['season']
            season.episodes.append(new_episode)
            db.session.add(season)
        except:
            return


def find_save_episode(todays_release_info):
    with app.app_context():
        tv_series = db.session.query(TvSeries).filter_by(title=todays_release_info.get('name')).first()
        if tv_series is None:
            return None
        season_title = todays_release_info.get('season')
        episode_name = todays_release_info.get('episode')
        for season in tv_series.seasons:
            if season.title == season_title:
                list_link_series(season.page_link, append_episode, season=season,episode=episode_name,
                                 data_info=todays_release_info)
                return


def background_data_handler():
    updates_url = os.environ.get('UPDATE_URL')
    an_hour = 60 * 60
    twenty_four_hours = an_hour * 24
    while True:
        today = date.today()
        today_releases = list_series(updates_url)
        table_key = 'orn:releases-' + str(today)

        if today_releases is None or len(today_releases) == 0:
            time.sleep(an_hour)
            continue
        # noinspection PyTypeChecker
        for release in today_releases:
            key = release.get('name') + '@@' + release.get('episode')
            try:
                find_save_episode(release)
            except Exception as e:
                db.session.rollback()
                print e
            value = json.dumps(release)
            print value
            if not data_cache.hexists(table_key, key):
                data_cache.hset(table_key, key, value)
        time.sleep(twenty_four_hours)
# orn:releases-2018-01-01

new_thread = threading.Thread(target=background_data_handler, args=[])
new_thread.setDaemon(True)
new_thread.start()

if __name__ == '__main__':
    app.run()
