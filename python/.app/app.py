#!/usr/bin/env python

from flask import Flask, jsonify
from flask_cors import CORS
from flask_pymongo import PyMongo


app = Flask('proc_pool')
CORS(app)
# app.config["MONGO_URI"] = '{}/{}'.format(config.app.db.url, config.app.db.name)
# app.json_encoder = DocumentEncoder
# FLASK_MONGO_CONNECTION = PyMongo(app)
# FLASK_MONGO_DB = FLASK_MONGO_CONNECTION.db
# Client.override_cursor(FLASK_MONGO_DB)


@app.route('/')
def hello():
    return jsonify(dict(output=[rule.rule for rule in app.url_map.iter_rules()])), 200


if __name__ == '__main__':
    app.run(port=9999, debug=True, host='0.0.0.0')
