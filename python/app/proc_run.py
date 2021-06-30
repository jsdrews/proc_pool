#!/usr/bin/env python


from time import sleep
from lib import concurrency, get_next_queued, startup_callback, config, ProcPool, Thread, app_logger, stream_logger
# from web_service_handler import RequestHandler


PROC_POOL = ProcPool(concurrency)
EVENT_STREAM = PROC_POOL.event_stream
PROC_DUMP = stream_logger('finished_procs') #path=config.runtime.task.finished_task_log)
LOGGER = stream_logger('proc_run')


def process_event_stream():
    while True:
        event = EVENT_STREAM.get()
        artifact = event.artifact
        LOGGER.debug('Artifact fetched: {}'.format(artifact))
        if artifact.parent_url:
            continue
            # url = '{}/update'.format(artifact.parent_url)
            # try:
            #     resp = RequestHandler.request(url=url, method='post',
            #                                   data={'update_data': {'status': artifact.status}},
            #                                   raise_error=True, logger=LOGGER)
            #     LOGGER.debug('response: {}'.format(resp))
            # except Exception as e:
            #     LOGGER.debug('response error: {}'.format(e))
        if artifact.to_delete:
            task = artifact.to_delete
            PROC_DUMP.info('{status}: {id} -- {pid} -- {priority} -- {cmd} -- {exit_code}'
                           .format(**task.full))
            del task


t = Thread(target=process_event_stream)
t.daemon = True
t.start()
del t


def run():
    PROC_POOL.start(startup_callback, get_next_queued)


t = Thread(target=run)
t.daemon = True
t.start()
del t


while True:
    sleep(1000)
