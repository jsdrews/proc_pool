import os
from .mongo import Document, UserFault, ApplicationFault, Client, InvalidId
from .config import Config, KeyNotAvailableError
from .manager import ProcPool, Thread, hexify, TIME_FORMAT, timestamp, Proc
from .logger import get_logger as __get_logger, stream_logger


__FILE_DIR = os.path.dirname(__file__)
__CONFIG_PATH = os.getenv('PROC_POOL_CONFIG') or os.path.join(__FILE_DIR, '../proc_pool.json')


config = Config.load(__CONFIG_PATH)
assert config.startup.db.url, "Please set config > startup > db > url in the in {}".format(__CONFIG_PATH)
assert config.startup.db.name, "Please set config > startup > db > name in the in {}".format(__CONFIG_PATH)
assert config.startup.log, "Please set config > startup > log in the in {}".format(__CONFIG_PATH)
assert config.runtime.task.finished_task_log, "Please set config > runtime > task > finished_task_log in the in " \
                                              "{}".format(__CONFIG_PATH)
assert config.runtime.task.states, "Please set config > runtime > task > states in the in {}".format(__CONFIG_PATH)
assert config.runtime.app.endpoints, "Please set config > runtime > app > endpoints in the in {}".format(__CONFIG_PATH)


concurrency = config.startup.concurrency or 1
task_extra_fields = tuple(config.runtime.task.extra_fields or [])
task_formattable_fields = tuple(config.runtime.task.formattable_fields or [])
endpoints = config.runtime.app.endpoints
states = config.runtime.task.states
logpath = config.startup.log.path or '/tmp/proc_pool.log'
log_level = config.startup.log.level or 'debug'


def app_logger(x, path=logpath, level=log_level): return __get_logger(x, logpath=path, level=level)


Client.set(config.startup.db.url, config.startup.db.name)


def build_task(cmd, **kwargs): return Task.build(cmd, **kwargs)


def query(query_data):
    return Task.query(query_data)


def from_id(_id):
    try:
        return Task.from_id(_id)
    except InvalidId:
        return None


def get_next_queued():
    doc = Client.next('task',
                      query={'status': {'$in': config.runtime.task.states.queued}},
                      sort_by='priority')
    if doc:
        t = Task(doc)
        t.commit(status=Proc.FETCHED)
        return t

    return None


def startup_callback():
    return [Task(x) for x in Client.find('task', {'status': {'$in': config.runtime.task.states.in_progress}})]


_DEFUALT_FIELDS = (
    'cmd',
    'env',
    'cwd',
    'pid',
    'init_time',
    'start_time',
    'end_time',
    'exit_code',
    'stdin',
    'stdout',
    'stderr',
    'log',
    'priority',
    'status',
    'timeout',
    'host',
    'user',
    'notes',
    'updated_at',
    'parent_url'
)


_DEFAULT_FORMATTABLE_FIELDS = (
    'cmd',
    'log',
)


class Task(Document):

    _FORMATTABLE_FIELDS = _DEFAULT_FORMATTABLE_FIELDS + task_formattable_fields

    __slots__ = _DEFUALT_FIELDS + task_extra_fields

    @staticmethod
    def build(cmd, priority=100, log=config.runtime.task.log or '',
              env=None, cwd=None, timeout=None, host=None, user='external_default', parent_url=''):

        assert isinstance(cmd, list), "The command argument must be a list"
        assert isinstance(priority, int), 'The priority argument should be an int'
        if timeout:
            assert isinstance(timeout, int), 'The timeout argument should be an integer'
        if env:
            assert isinstance(env, dict), 'The env argument should be a dict'
        if cwd:
            assert isinstance(cwd, str), 'The cwd argument should be a string'

        cmd = [str(x) for x in cmd]

        task = Task({
            'cmd': cmd,
            'log': log,
            'init_time': timestamp(),
            'priority': priority,
            'env': env,
            'cwd': cwd,
            'timeout': timeout,
            'host': host,
            'user': user,
            'parent_url': parent_url,
            'notes': [
                {
                    'text': 'task created',
                    'timestamp': timestamp(),
                    'user': user
                }
            ]
        })

        task.format_fields()
        if task.log and not os.path.exists(os.path.dirname(task.log)):
            os.makedirs(os.path.dirname(task.log))

        task.commit()

        return task

    @staticmethod
    def str_convert(s, codec='utf-8'):
        try:
            return str(s, codec)
        except LookupError:
            return s

    def __repr__(self):
        return ' '.join(self.cmd) if self.cmd else '[]'

    def __str__(self):
        return ' '.join(self.cmd) if self.cmd else '[]'

    def __ge__(self, other):
        return self.priority <= other.priority

    def __lt__(self, other):
        return self.priority >= other.priority

    def __le__(self, other):
        return self.priority > other.priority

    def __ne__(self, other):
        return self.priority != other.priority

    def __eq__(self, other):
        return self.priority == other.priority

    def format_fields(self):

        format_dict = {
            'name': self.name or hexify(),
            'date': timestamp('%Y-%m-%d')
        }

        format_dict.update(self.dict)

        for att in Task._FORMATTABLE_FIELDS:

            tmp = getattr(self, att)

            if isinstance(tmp, list):
                a = []
                for arg in tmp:
                    a.append(arg.format(**format_dict))
                tmp = a

            else:
                tmp = tmp.format(**format_dict)

            setattr(self, att, tmp)

    def add_note(self, note, user='internal_default'):
        assert isinstance(note, str), "A note must be a string"
        note = {
            'text': note,
            'timestamp': timestamp(),
            'user': user
        }
        if not self.notes:
            self.notes = []
        self.notes.append(note)

    @property
    def full(self):
        tmp = super(Task, self).full
        tmp.update({
            'url': self.url,
            'parent_url': self.parent_url
        })
        return tmp

    @property
    def url(self):
        return '{}proc_pool/task/{}'.format(self.host, self.name)

    @property
    def slim(self):
        return {
            'id': self.name,
            'cmd': self.cmd,
            'priority': self.priority,
            'status': self.status,
            'url': self.url,
            'parent_url': self.parent_url,
            'notes': self.notes,
            'user': self.user,
            'exit_code': self.exit_code
        }

    def commit(self, status=None, note=None, user='internal_default'):
        self.updated_at = timestamp()
        if note:
            self.add_note(note=note, user=user)
        super(Task, self).commit(status=status)
