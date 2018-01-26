#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  recent_updates.py

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from BeautifulSoup import BeautifulSoup
from datetime import date, timedelta
from multiprocessing import Queue
from models import TvSeries, TvEpisode, DownloadLink, TvSeason
import threading
import os
import requests
import redis
import json

cache_pass, port_number = os.environ.get('redis_pass'), int(os.environ.get('redis_port'))
data_cache = redis.StrictRedis(password=cache_pass, port=port_number)
visited_sites = {}
unregistered_series = []


def get_page_data(link, callback_on_failure=None):
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


def today_date():
    return date.today() - timedelta(1)


def list_all_series(link):
    if visited_sites.get(link) is not None:
        return None
    visited_sites[link] = True
    network_response = get_page_data(link)
    if network_response is None:
        return None
    parsed_data = BeautifulSoup(network_response.content)
    data_list = parsed_data.findAll('div', attrs={'class': 'data main'})
    today = today_date()
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
            is_released_today = date(int(release_date[-1]), int(release_date[1]), int(release_date[0])) == today
            if is_released_today:
                today_releases.append({'name': series_name, 'season': season_name, 'episode': episode_name})
        except ValueError:
            continue
    return today_releases


db = SQLAlchemy()


def initialize_app():
    application = Flask(__name__)
    application.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DB_URL')
    application.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
    db.init_app(application)
    
    return application


app = initialize_app()


@app.before_first_request
def before_any_request():
    # noinspection PyUnresolvedReferences
    db.configure_mappers()
    db.create_all()


def list_series_from_link(link, post_data_callback, *callback_args, **callback_kw):
    if visited_sites.get(link) is not None:
        return
    visited_sites[link] = True
    network_response = get_page_data(link)
    if network_response is None:
        return
    parsed_data = BeautifulSoup(network_response.content)
    data_list = parsed_data.findAll('div', attrs={'class': 'data'})

    for data_item in data_list:
        hrefs = data_item.findAll('a')
        for href in hrefs:
            post_data_callback(href, *callback_args, **callback_kw)


def download_link_extractor(ah_ref_object, **kwargs):
    download_link = ah_ref_object.attrs[0][1]
    if download_link == '#':
        return
    download_type = ah_ref_object.string.strip()
    try:
        if kwargs['data'].get('download_links') is None:
            kwargs['data']['download_links'] = []
        kwargs['data']['download_links'].append({'download_type': download_type, 'link': download_link})
        kwargs['episode'].download_links.append(DownloadLink(download_type=download_type, link=download_link))
    except:
        print 'Error'


def add_episode_dlinks(episode_link, current_episode, data):
    list_series_from_link(episode_link, download_link_extractor, episode=current_episode, data=data)


def add_episode_to_season(ah_ref, **kwargs):
    expected_episode_name = kwargs['episode'].strip()
    episode_link = ah_ref.attrs[0][1]
    episode_name = ah_ref.string.strip()
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
            print '{} not found'.format(todays_release_info.get('name'))
            unregistered_series.append(todays_release_info)
            return None
        season_title = todays_release_info.get('season')
        episode_name = todays_release_info.get('episode')
        for season in tv_series.seasons:
            if season.title == season_title:
                list_series_from_link(season.page_link, add_episode_to_season, season=season, episode=episode_name,
                                      data_info=todays_release_info)
                return


def process_episodes_for(today_releases, table_key):
    for release in today_releases:
        key = release.get('name') + '@@' + release.get('episode')
        try:
            find_save_episode(release)
        except Exception as e:
            db.session.rollback()
            print e
        value = json.dumps(release)
        if not data_cache.hexists(table_key, key):
            data_cache.hset(table_key, key, value)


def run_data_handler():
    updates_url = os.environ.get('UPDATE_URL')
    today = today_date()
    table_key = 'orn:releases-' + str(today)
    if data_cache.hlen(table_key) > 0:
        print 'Nothing to do'
        return
    
    if updates_url in visited_sites:
        visited_sites.pop(updates_url)
    today_releases = list_all_series(updates_url)

    if today_releases is None or len(today_releases) == 0:
        print 'No releases for today'
        return
    # noinspection PyTypeChecker
    process_episodes_for(today_releases, table_key)


def database_updater(database_handler, reader):
    my_log_file = open('./log.txt', 'w')
    result = json.loads(reader.get_buffer())
    for tv_series in result:
        my_log_file.write('Doing one TV series\n')
        show_title = tv_series.get('name')
        seasons = tv_series.get('seasons')
        tv_series = TvSeries(title=show_title)
        for season in seasons:
            my_log_file.write('Doing one TV season\n')
            season_name = season.get('title')
            season_page_link = season.get('page_link')
            episodes = season.get('episodes')
            tv_season = TvSeason(title=season_name, page_link=season_page_link)
            for episode in episodes:
                my_log_file.write('Doing one TV episode\n')
                episode_name = episode.get('title')
                page_link = episode.get('page_link')
                download_links = episode.get('dl_links')
                tv_episode = TvEpisode(title=episode_name, page_link=page_link)
                for dl_link in download_links:
                    download_type = dl_link.get('type')
                    download_link = dl_link.get('link')
                    tv_episode.download_links.append(DownloadLink(download_type=download_type, link=download_link))
                tv_season.episodes.append(tv_episode)
                my_log_file.flush()
            tv_series.seasons.append(tv_season)
        with app.app_context():
            try:
                database_handler.session.add(tv_series)
            except Exception as e:
                database_handler.session.rollback()
                print e

    with app.app_context():
        database_handler.session.commit()
        my_log_file.write('Done\n')


def fetch_tv_seasons(callback, arguments, number_of_threads):
    thread_list = []
    for i in range(number_of_threads):
        new_thread = threading.Thread(target=callback, args=[arguments])
        thread_list.append(new_thread)
        new_thread.start()
    for my_thread in thread_list:
        if my_thread.is_alive():
            my_thread.join()


def find_register_new_series(series):
    from scrapper import direct_page_links, main_page_scrapper, store_tv_series, list_link_series
    from scrapper import visiting_links, list_tv_seasons, tv_series, JsonObjectIO

    main_page_scrapper()  # extracts all TV series into `visiting_links`
    for links in visiting_links:
        list_link_series(links, store_tv_series)

    all_unregistered_series = [series_name.get('name') for series_name in series]
    print all_unregistered_series
    new_series_list = Queue()
    while direct_page_links.qsize() > 0:
        series_object = direct_page_links.get()
        tv_title, tv_page_link = (series_object[0], series_object[1])
        if tv_title in all_unregistered_series:
            new_series_list.put([tv_title, tv_page_link])

    direct_page_links.close()
    if new_series_list.empty():
        return

    fetch_tv_seasons(callback=list_tv_seasons, arguments=new_series_list, number_of_threads=3)
    new_series_list.close()

    json_io = JsonObjectIO()
    s = []
    for series in tv_series:
        s.append(tv_series[series].to_object())
    json_io.write(json.dumps(s, indent=2, separators=(',', ': ')))

    thr = threading.Thread(target=database_updater, args=[db, json_io])
    thr.start()
    thr.join()



if __name__ == '__main__':
    new_task = threading.Thread(target=run_data_handler, args=[])
    new_task.start()
    new_task.join()
    
    print len(unregistered_series)
    if len(unregistered_series) > 0:
        # we'll find this series, scan the seasons and add each episodes
        find_register_new_series(unregistered_series)
        today = today_date()
        table_key = 'orn:releases-' + str(today)
        new_series = [ series for series in unregistered_series ]
        print new_series == unregistered_series
        process_episodes_for(new_series, table_key)
