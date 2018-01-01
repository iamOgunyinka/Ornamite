#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  config.py

from flask import Flask
from views import main_api, db
import os

def initialize_app():
    app = Flask(__name__)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get( 'DB_URL' )
    app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
    
    db.init_app(app)
    app.register_blueprint(main_api, url_prefix='/orn')
    return app


app = initialize_app()

@app.before_first_request
def before_any_request():
    db.configure_mappers()
    db.create_all()


if __name__ == '__main__':
    app.run(debug=True)
