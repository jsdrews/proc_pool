# proc_pool
Simple web service to run and manage linux processes remotely.

----------------------------------------

### quick start

```bash

git clone git@github.com:jsdrews/proc_pool.git

cd proc_pool && docker-compose up -d

```

---------------------------------------------

Add request(s)

```bash

> curl http://localhost/proc_pool/tasks/add -X POST -H "Content-Type: application/json" -d '{"requests": [{"cmd": ["env"]}]}' | python3 -m json.tool

{
    "inserted": [
        {
            "cmd": [
                "env"
            ],
            "exit_code": null,
            "id": "60dbd0e98e9a67575d3965bb",
            "notes": [
                {
                    "text": "task created",
                    "timestamp": "2021-06-30 02:03:21",
                    "user": "external_default"
                }
            ],
            "parent_url": "",
            "priority": 100,
            "status": "created",
            "url": "http://localhost/proc_pool/task/60dbd0e98e9a67575d3965bb",
            "user": "external_default"
        }
    ]
}
```

---------------------------------------------

Get a single request

```bash

> curl http://localhost/proc_pool/task/60dbd0e98e9a67575d3965bb

{
    "message": "Successful request",
    "method": "get_task",
    "output": {
        "cmd": [
            "env"
        ],
        "exit_code": 0,
        "id": "60dbd0e98e9a67575d3965bb",
        "notes": [
            {
                "text": "task created",
                "timestamp": "2021-06-30 02:03:21",
                "user": "external_default"
            },
            {
                "text": "task started",
                "timestamp": "2021-06-30 02:03:26",
                "user": "internal_default"
            },
            {
                "text": "task complete -- code: 0, status: finished",
                "timestamp": "2021-06-30 02:03:26",
                "user": "internal_default"
            }
        ],
        "parent_url": "",
        "priority": 100,
        "status": "finished",
        "url": "http://localhost/proc_pool/task/60dbd0e98e9a67575d3965bb",
        "user": "external_default"
    }
}
```

---------------------------------------------

Stdout and Stderr get written to the task's log

```bash

> curl http://localhost/proc_pool/task/60dbd0e98e9a67575d3965bb/log

PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
HOSTNAME=8ef00cf41574
LANG=C.UTF-8
GPG_KEY=E3FF2839C048B25C084DEBE9B26995E310250568
PYTHON_VERSION=3.9.6
PYTHON_PIP_VERSION=21.1.3
PYTHON_GET_PIP_URL=https://github.com/pypa/get-pip/raw/a1675ab6c2bd898ed82b1f58c486097f763c74a9/public/get-pip.py
PYTHON_GET_PIP_SHA256=6665659241292b2147b58922b9ffe11dda66b39d52d8a6f3aa310bc1d60ea6f7
HOME=/root

```

Change process concurrency via the *config > startup > concurrency*

```bash

> python3 -m json.tool proc_pool/python/app/proc_pool.json

{
    "startup": {
        "db": {
            "url": "mongodb://proc_pool_mongo:27017",
            "name": "proc_pool"
        },
        "concurrency": 10,
        "log": {
            "path": "/var/log/proc_pool/proc_pool.log",
            "level": "debug"
        }
    },
    "runtime": {
        "task": {
            "formattable_fields": [],
            "extra_fields": [],
            "log": "/var/log/proc_pool/{date}/{name}.log",
            "states": {
                "complete": [
                    "complete",
                    "killed",
                    "failed",
                    "finished",
                    "timed-out",
                    "errored"
                ],
                "in_progress": [
                    "processing",
                    "fetched",
                    "paused"
                ],
                "queued": [
                    "created",
                    "inserted"
                ],
                "errored": [
                    "killed",
                    "failed",
                    "finished",
                    "timed-out",
                    "errored"
                ],
                "running": [
                    "processing"
                ]
            },
            "actions": {
                "pause": [
                    -19,
                    "paused"
                ],
                "resume": [
                    -18,
                    "processing"
                ],
                "kill": [
                    -9,
                    "killed"
                ]
            },
            "finished_task_log": "/var/log/proc_pool/proc_pool.finished"
        },
        "app": {
            "endpoints": {
                "tasks": "/tasks",
                "tasks_add": "/tasks/add",
                "tasks_queued": "/tasks/queued",
                "tasks_running": "/tasks/in_progress",
                "task": "/task/<string:oid>",
                "task_log": "/task/<string:oid>/log",
                "task_update": "/task/<string:oid>/update",
                "task_interact": "/task/<string:oid>/interact",
                "tasks_query": "/tasks/query",
                "tasks_update": "/tasks/update",
                "help_statuses": "/help/states",
                "help_in_progress": "/help/states/in_progress",
                "help_complete": "/help/states/complete",
                "help_endpoints": "/help/endpoints",
                "config": "/config",
                "logs_app": "/logs/app",
                "logs_uwsgi": "/logs/uwsgi",
                "logs_emporer": "/logs/emporer"
            }
        }
    }
}

```