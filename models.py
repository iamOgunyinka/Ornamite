#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  models.py

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class TvSeries(db.Model):
    __tablename__ = 'tv_series'
    
    id = db.Column(db.Integer, primary_key=True, index=True, nullable=False)
    title = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=True)
    seasons = db.relationship('TvSeason', backref='series_name')
    
    
class TvSeason(db.Model):
    __tablename__ = 'tv_seasons'
    
    id = db.Column(db.Integer, primary_key=True, index=True, nullable=False)
    title = db.Column(db.Text, nullable=False)
    page_link = db.Column(db.String(256), nullable=False, unique=True)
    series_id = db.Column( db.Integer, db.ForeignKey( 'tv_series.id' ) )
    episodes = db.relationship('TvEpisode', backref='episode_name')


class TvEpisode(db.Model):
    __tablename__ = 'tv_episodes'
    
    id = db.Column(db.Integer, primary_key=True, index=True, nullable=False)
    seasons_id = db.Column( db.Integer, db.ForeignKey( 'tv_seasons.id' ) )
    title = db.Column(db.Text, nullable=False)
    page_link = db.Column(db.String(256), nullable=False, unique=True)
    download_links = db.relationship('DownloadLink', backref='download_link')


class DownloadLink(db.Model):
    __tablename__ = 'download_links'
    
    id = db.Column(db.Integer, primary_key=True, index=True, nullable=False)
    episode_id = db.Column( db.Integer, db.ForeignKey( 'tv_episodes.id' ) )
    download_type = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(256), nullable=False, unique=True)
