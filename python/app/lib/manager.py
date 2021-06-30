from uuid import uuid4
from time import sleep
from datetime import datetime
from subprocess import Popen, PIPE  # TimeoutExpired -- not available in py2
from collections import namedtuple
from signal import SIGSTOP, SIGCONT
from heapq import heappush, heappop
from functools import partial
from threading import Thread, Condition
try:
    from Queue import Queue
except ImportError:
    from queue import Queue


TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def hexify(): return uuid4().hex


def timestamp(time_format=TIME_FORMAT):
    return datetime.now().strftime(time_format)


Event = namedtuple('Event', 'artifact')


Artifact = namedtuple('Artifact', 'status parent_url to_delete')


class Proc(object):

    FINISHED = 'finished'
    TIMEDOUT = 'timed-out'
    ERRORED = 'errored'
    PROCESSING = 'processing'
    FETCHED = 'fetched'

    __slots__ = (
        'task',
        'callback',
        'proc',
        'suspended',
    )

    def __init__(self, task):

        self.task = task
        self.callback = partial(Popen,
                                task.cmd,
                                stdin=PIPE,
                                stderr=PIPE,
                                cwd=task.cwd,
                                env=task.env,
                                close_fds=True)
        self.proc = None
        self.suspended = False

    def __repr__(self):
        return str(self.callback)

    def __str__(self):
        return str(self.callback)

    def run(self, log=True):
        log_handle = open(self.task.log, 'ab') if (log and self.task.log) else PIPE
        status = Proc.PROCESSING
        try:
            self.proc = self.callback(stdout=log_handle)

            self.task.pid = self.proc.pid
            self.task.start_time = timestamp()
            self.task.commit(status=status, note='task started')

            self.task.stdout, self.task.stderr = self.proc.communicate(input=self.task.stdin)
            status = Proc.FINISHED
        except (OSError, IOError) as e:
            self.task.stderr = str(e)
            status = Proc.ERRORED

        if self.task.stderr and log_handle != PIPE:
            log_handle.write(self.task.stderr)
        log_handle.close()

        if self.task.stderr and self.exit_code:
            status = Proc.ERRORED

        self.task.stderr = str(self.task.stderr)
        self.task.exit_code = self.exit_code
        self.task.end_time = timestamp()
        self.task.commit(status=status, note='task complete -- code: {}, status: {}'.format(self.task.exit_code,
                                                                                            status))

    @classmethod
    def statuses(cls):
        return [v for k, v in vars(cls).items() if k.isupper()]

    @classmethod
    def completed(cls):
        return [v for k, v in vars(cls).items() if k.isupper() and k != 'PROCESSING']

    @staticmethod
    def in_progress():
        return [Proc.PROCESSING, Proc.FETCHED]

    @property
    def name(self):
        return self.task.name

    @property
    def pid(self):
        if self.proc:
            return self.proc.pid

    @property
    def exit_code(self):
        if not self.proc:
            return -9999
        return self.proc.returncode

    @property
    def finished(self):
        return isinstance(self.exit_code, int)

    @property
    def cmd(self):
        return self.task.cmd

    def terminate(self):
        if self.proc:
            self.proc.terminate()
            self.suspended = False

    def kill(self):
        if self.proc:
            self.proc.kill()
            self.suspended = False

    def pause(self):
        if self.proc:
            self.proc.send_signal(SIGSTOP)
            self.suspended = True

    def resume(self):
        if self.proc:
            self.proc.send_signal(SIGCONT)
            self.suspended = False


class ProcPool(object):

    __slots__ = (
        'pool',
        'size',
        'output_stream',
        'event_stream',
        '__open_slot_stream',
    )

    def __init__(self, size):
        self.pool = {}
        self.size = size
        self.event_stream = Queue()
        self.__open_slot_stream = Queue()

        for i in range(size):
            self.__open_slot_stream.put(True)

    def __setitem__(self, key, value):
        self.pool[key] = value

    def __getitem__(self, item):
        try:
            return self.pool[item]
        except IndexError:
            return None

    @property
    def running(self):
        return self.pool.values()

    def __launch_proc(self, proc):

        def __add_run(this, proc):
            this[proc.name] = proc
            self.event_stream.put(Event(artifact=Artifact(status=Proc.PROCESSING,
                                                          parent_url=proc.task.parent_url,
                                                          to_delete=None)))
            proc.run()
            self.event_stream.put(Event(artifact=Artifact(status=proc.task.status,
                                                          parent_url=proc.task.parent_url,
                                                          to_delete=proc.task)))
            this.__open_slot_stream.put(True)
            del proc

        t = Thread(target=__add_run, args=(self, proc))
        t.start()
        del t

    def __remove_proc(self, proc):
        try:
            del self.pool[proc.name]
        except KeyError:
            pass

    def input_stream(self, tasks=None):

        def __poll_input(this, priority_pool):
            while True:
                _ = this.__open_slot_stream.get()
                this.__open_slot_stream.task_done()
                new_task = priority_pool.pop()
                new_proc = Proc(new_task)
                this.__launch_proc(new_proc)

        priority_pool = PriorityPool(pool=tasks)
        t = Thread(target=__poll_input, args=(self, priority_pool,))
        t.daemon = True
        t.start()
        del t

        return priority_pool

    def start(self, startup_callback, next_task_callback):

        assert callable(startup_callback) and callable(next_task_callback), 'to start the proc pool,' \
                                                                            'pass a startup function ' \
                                                                            'and a get next function'

        def __get_next(this, startup_callback, input_callback):

            for task in startup_callback():
                _ = this.__open_slot_stream.get()
                new_proc = Proc(task)
                this.__launch_proc(new_proc)

            while True:
                _ = this.__open_slot_stream.get()
                new_task = None
                while not new_task:
                    new_task = input_callback()
                    if new_task:
                        break
                    sleep(10)
                new_proc = Proc(new_task)
                this.__launch_proc(new_proc)

        t = Thread(target=__get_next, args=(self, startup_callback, next_task_callback))
        t.daemon = True
        t.start()
        del t


class PriorityPool(object):

    __slots__ = (
        'pool',
        'map',
        '__block'
    )

    def __init__(self, pool=None):

        self.map = {}
        self.pool = []
        self.__block = Condition()

        if pool:
            assert isinstance(pool, list), 'If instantiating a PriorityPool with the pool argument, the pool argument ' \
                                           'must be a list of items'
            for item in pool:
                self.put(item)

    def put(self, item, index=None):
        assert getattr(item, '_id') or index, 'Item must a id assigned to it for indexing'
        self.map[getattr(item, '_id') or index] = item
        with self.__block:
            self.__block.notify()
            heappush(self.pool, item)

    def get(self, index):
        return self.map.get(index)

    def pop(self):
        with self.__block:
            while self.empty:
                self.__block.wait()
        item = heappop(self.pool)
        return item

    @property
    def empty(self):
        return bool(not self.pool)

    @property
    def all(self):
        return self.pool
