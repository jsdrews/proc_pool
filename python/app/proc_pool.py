#!/usr/bin/env python

import json
import inspect
from flask_pymongo import PyMongo
from flask_cors import CORS
from collections import namedtuple
from flask import jsonify, Flask, request, make_response
from flask.json import JSONEncoder
from subprocess import PIPE, Popen


from lib import build_task, query, from_id, config, endpoints, states, Client, UserFault, stream_logger


class CustomEncoder(JSONEncoder):

    def default(self, obj):
        return obj.dict


app = Flask(__name__)
app.config["MONGO_URI"] = '{}/{}?authSource=admin'.format(config.startup.db.url, config.startup.db.name)


FLASK_MONGO_CONNECTION = PyMongo(app)
FLASK_MONGO_DB = FLASK_MONGO_CONNECTION.db


Client.override_client(FLASK_MONGO_DB)


app.json_encoder = CustomEncoder


CORS(app)


LOGGER = stream_logger('proc_pool')


ResponseValidation = namedtuple('ResponseValidation', 'response, post_data, status_code')


# VALIDATION ----------------------------------------------------
def validate_post(request, post_key):

    response = {
        'method': inspect.currentframe().f_code.co_name,
        'input': '',
        'output': [],
        'message': ''
    }
    # Check if post data was sent
    if not request.data:
        LOGGER.error('NO POST DATA SENT')
        response['message'] = 'No Post JSON sent - required'
        return ResponseValidation(response=response,
                                  post_data=None,
                                  status_code=406)

    # Decode post data from json -> dict
    try:
        request_data = json.loads(request.data)
    except ValueError as e:
        LOGGER.error('UNABLE TO DECODE POST DATA')
        response['message'] = str(e)
        response['input'] = request.data
        return ResponseValidation(response=response,
                                  post_data=None,
                                  status_code=500)

    LOGGER.info('RECEIVED -- {}'.format(request_data))

    # Check if the post data json is empty
    if not request_data:
        response['message'] = 'No posted data received'
        return ResponseValidation(response=response,
                                  post_data=None,
                                  status_code=500)

    post_data = request_data.get(post_key)
    # Check for the post key of the post data
    if post_data is None:
        response['message'] = '{0} key not found in post data or {0} has an empty value'.format(post_key)
        return ResponseValidation(response=response,
                                  post_data=None,
                                  status_code=500)

    return ResponseValidation(response=response,
                              post_data=post_data,
                              status_code=200)


# ENDPOINTS -----------------------------------------------------

@app.route('/')
def hello():
    return jsonify(dict(output=[rule.rule for rule in app.url_map.iter_rules()])), 200


# /tasks ########################################
@app.route(endpoints.tasks_add, methods=['POST'])
def add_task():

    default_response, post_data, status_code = validate_post(request, 'requests')

    if status_code != 200:
        return jsonify(default_response), status_code

    inserted = []
    for req in post_data:

        try:
            assert isinstance(req, dict), "Each request must be a dict -- " \
                                          "this was what was received: req = '{}', type = '{}'".format(req, type(req))
            req.update({'host': request.host_url})
            task = build_task(**req)
            inserted.append(task.slim)
        except (UserFault, AssertionError) as e:
            default_response['message'] = str(e)
            default_response['inserted'] = inserted
            return jsonify(default_response), 500

    return jsonify({"inserted": inserted}), 200


@app.route(endpoints.tasks_running, methods=['GET'])
def get_running():

    response = {
        'method': inspect.currentframe().f_code.co_name,
        'output': [],
        'message': 'Successful request'
    }

    full = request.args.get('full') is not None

    for task in query({'status': {'$in': states.running}}):
        if full:
            response['output'].append(task.full)
        else:
            response['output'].append(task.slim)

    return jsonify(response), 200


@app.route(endpoints.tasks_queued, methods=['GET'])
def get_queued():

    response = {
        'method': inspect.currentframe().f_code.co_name,
        'output': [],
        'message': 'Successful request'
    }

    full = request.args.get('full') is not None

    for queued in query({'status': {'$in': states.queued}}):
        if full:
            response['output'].append(queued.full)
        else:
            response['output'].append(queued.slim)

    return jsonify(response), 200


@app.route(endpoints.tasks, methods=['GET'])
def query_task_states():

    response = {
        'method': inspect.currentframe().f_code.co_name,
        'output': [],
        'message': 'Successful request'
    }

    full = request.args.get('full') is not None

    try:
        state = request.args.get('state')
        assert state
    except AssertionError:
        response['message'] = 'Add a "state=<state>" argument to the url'
        return jsonify(response), 500

    try:
        state_query = getattr(states, state)
        assert state_query
    except AssertionError:
        response['message'] = 'State "{}" not found -- available states: {}'.format(state, ', '.join(states.keys))
        return jsonify(response), 404

    for queued in query({'status': {'$in': state_query}}):
        if full:
            response['output'].append(queued.full)
        else:
            response['output'].append(queued.slim)

    return jsonify(response), 200


@app.route(endpoints.tasks_query, methods=['POST'])
def tasks_query():

    default_response, post_data, status_code = validate_post(request, 'query')

    if status_code != 200:
        return jsonify(default_response), status_code

    full = request.args.get('full') is not None

    if full:
        default_response['output'] = [x.full for x in query(post_data)]
    else:
        default_response['output'] = [x.slim for x in query(post_data)]
    default_response['method'] = inspect.currentframe().f_code.co_name

    return jsonify(default_response), 200


@app.route(endpoints.tasks_update, methods=['POST'])
def update_tasks():

    default_response, post_data, status_code = validate_post(request, 'ids')

    if status_code != 200:
        return jsonify(default_response), status_code

    updated = []
    for _id, update_dict in post_data.items():

        try:
            task = from_id(str(_id))
        except UserFault:
            default_response['message'] = 'Invalid ID received: "{}"'.format(_id)
            return jsonify(default_response), 500

        if not task:
            continue

        for k, v in update_dict.items():
            try:
                setattr(task, k, v)
            except (UserFault, AttributeError, AssertionError):
                pass

        updated.append(task.slim)

        task.commit()

    default_response['output'] = updated
    return jsonify(default_response), 200


# /task ##########################################
@app.route(endpoints.task, methods=['GET'])
def get_task(oid):

    response = {
        'method': inspect.currentframe().f_code.co_name,
        'output': None,
        'message': 'Successful request'
    }

    t = from_id(str(oid))
    full = request.args.get('full') is not None

    if t:
        if full:
            response['output'] = t.full
        else:
            response['output'] = t.slim

    return jsonify(response), 200


@app.route(endpoints.task_log, methods=['GET'])
def get_log(oid):

    t = from_id(str(oid))

    if not t:
        resp = make_response('Task {} not found at this service -- '
                             'try another service or double check the id'.format(oid), 404)
        resp.headers['Content-Type'] = 'text/plain'
        return resp

    try:
        with open(t.log, 'rb') as f:
            content = f.read()
        resp = make_response(content, 200)
    except (IOError, OSError) as e:
        resp = make_response('Unable to read from log file -- {}'.format(str(e)), 500)

    resp.headers['Content-Type'] = 'text/plain'
    return resp


@app.route(endpoints.task_update, methods=['POST'])
def update_task(oid):

    default_response, post_data, status_code = validate_post(request, 'update_data')

    if status_code != 200:
        return jsonify(default_response), status_code

    try:
        task = from_id(str(oid))
    except UserFault:
        default_response['message'] = 'Invalid ID received: "{}"'.format(oid)
        return jsonify(default_response), 500

    if not task:
        default_response['message'] = "Task '{}' does not exist at {}".format(oid, request.host)

    for k, v in post_data.items():
        try:
            setattr(task, k, v)
        except (UserFault, AttributeError, AssertionError):
            pass

    task.commit()

    default_response['output'] = task.slim
    return jsonify(default_response), 200
    

@app.route(endpoints.task_interact, methods=['POST'])
def task_interact(oid):

    default_response, post_data, status_code = validate_post(request, 'action')

    if status_code != 200:
        return jsonify(default_response), status_code

    try:
        task = from_id(str(oid))
    except UserFault:
        default_response['message'] = 'Invalid ID received: "{}"'.format(oid)
        return jsonify(default_response), 500

    if not task:
        default_response['message'] = "Task '{}' does not exist at {}".format(oid, request.host)

    actions = config.runtime.task.actions
    action = getattr(actions, post_data)

    if not action:
        default_response['message'] = "Action not permitted: {} -- allowed actions: {}".format(post_data,
                                                                                              ', '.join(actions.keys()))
        return jsonify(default_response), 500

    action_name = post_data
    action_signal = action[0]
    action_update_status = action[1]

    if task.status in states.complete:
        default_response['message'] = "The task is {} -- nothing to do here".format(task.status)
        return jsonify(default_response), 500

    if not task.pid:
        default_response['message'] = "You can only interact with a running task"
        return jsonify(default_response), 500

    p = Popen(['kill', str(action_signal), str(int(task.pid))], stdout=PIPE, stderr=PIPE)
    _, stderr = p.communicate()

    if p.returncode:
        default_response['message'] = 'Unable to {} the task'.format(action_name)
        default_response['message'] += str(stderr)
        return jsonify(default_response), 500

    # TODO: should keep the task manipulation from API to a minimum as it will cause conflicts with the process daemon
    task.status = action_update_status
    task.commit(note='Action sent to process: "{}"'.format(post_data))
    default_response['message'] = 'Action success: {}'.format(action_name)

    default_response['output'] = task.slim
    return jsonify(default_response), 200


# /help ###########################################
@app.route(endpoints.help_statuses, methods=['GET'])
def help_statuses():

    response = {
        'method': inspect.currentframe().f_code.co_name,
        'output': states,
        'message': 'Successful request'
    }

    return jsonify(response), 200


@app.route(endpoints.help_complete, methods=['GET'])
def help_statuses_complete():

    response = {
        'method': inspect.currentframe().f_code.co_name,
        'output': states.complete,
        'message': 'Successful request'
    }

    return jsonify(response), 200


@app.route(endpoints.help_in_progress, methods=['GET'])
def help_statuses_in_progress():

    response = {
        'method': inspect.currentframe().f_code.co_name,
        'output': states.in_progress,
        'message': 'Successful request'
    }

    return jsonify(response), 200


@app.route(endpoints.help_endpoints, methods=['GET'])
def get_endpoints():

    response = {
        'method': inspect.currentframe().f_code.co_name,
        'output': sorted(endpoints.values),
        'message': 'Successful request'
    }

    return jsonify(response), 200


@app.route(endpoints.config, methods=['GET'])
def get_config():

    response = {
        'method': inspect.currentframe().f_code.co_name,
        'output': config,
        'message': 'Successful request'
    }

    return jsonify(response), 200


if __name__ == '__main__':
    app.run(port=9998, debug=True, host='0.0.0.0')
