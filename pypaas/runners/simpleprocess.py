#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import os.path
import shutil
import subprocess
import sys
import time
import shlex

from .. import options, util
from .base import BaseRunner


runscript = options.main.get('runner_runscript_template', """#!/bin/sh
cd {checkout.path}
{before_cmds}
{env_cmds}
exec 2>&1
exec {cmd}
""")

logscript = options.main.get('runner_logscript_template', """#!/bin/sh
exec multilog t ./main
""")


def check_call(cmd, **kwargs):
    # This captures the output in sys.stderr even if you replace it
    try:
        print(
            subprocess.check_output(
                cmd,
                universal_newlines=True,
                stderr=subprocess.STDOUT,
                **kwargs
            ), file=sys.stderr, flush=True
        )
    except subprocess.CalledProcessError as e:
        print(e.output, file=sys.stderr, flush=True)
        raise


def svc_start(service):
    print('starting daemontools service {}'.format(service))
    check_call([
        'svc', '-u',
        os.path.expanduser('~/services/{}'.format(service))
    ])


def svc_stop(service):
    print('stopping daemontools service {}'.format(service))
    check_call([
        'svc', '-d',
        os.path.expanduser('~/services/{}'.format(service))
    ])


def svc_destroy(service):
    print('destorying daemontools service {}'.format(service))

    try:
        os.unlink(os.path.expanduser('~/services/{}'.format(service)))
    except FileNotFoundError:
        pass

    try:
        os.unlink(os.path.expanduser('~/services-real/{}/run'.format(service)))
    except FileNotFoundError:
        pass
    try:
        os.unlink(os.path.expanduser('~/services-real/{}/log/run'.format(service)))
    except FileNotFoundError:
        pass

    check_call([
        'svc', '-dx',
        os.path.expanduser('~/services-real/{}/log'.format(service))
    ])
    check_call([
        'svc', '-dx',
        os.path.expanduser('~/services-real/{}'.format(service))
    ])
    shutil.rmtree(os.path.expanduser('~/services-real/{}'.format(service)))


def svc_wait(service):
    print('waiting for daemontools service {} to appear'.format(service))
    out = None
    while (out is None) or (b"supervise not running" in out) or \
            (b"unable to control" in out):
        out = subprocess.check_output([
            'svstat',
            os.path.expanduser('~/services/{}'.format(service))
        ])
        time.sleep(0.05)


class SimpleProcess(BaseRunner):
    @property
    def service_names(self):
        return ['{}-{}'.format(self.name, i)
                for i in range(self.config.get('process_count', 1))]

    def get_process_env(self, **kwargs):
        return self.branch.current_checkout.cmd_env

    def configure(self):
        util.mkdir_p(os.path.expanduser('~/services/'))
        util.mkdir_p(os.path.expanduser('~/services-real/'))

        for idx, s in enumerate(self.service_names):
            util.mkdir_p(os.path.expanduser('~/services-real/{}/log'.format(s)))
            env = self.get_process_env(idx=idx)
            before_cmds = self.branch.config.get('before_cmds', '')
            if not isinstance(before_cmds, list):
                before_cmds = [before_cmds]
            args = dict(
                checkout=self.branch.current_checkout,
                branch=self.branch,
                repo=self.branch.repo,
                cmd=self.config['cmd'],
                env_cmds='\n'.join(
                    'export {}={}'.format(
                        k, shlex.quote(str(v))
                    ) for k, v in env.items()
                ),
                before_cmds='\n'.join(before_cmds)
            )
            util.replace_file(
                os.path.expanduser('~/services-real/{}/log/run'.format(s)),
                logscript.format(**args),
                chmod=0o755
            )
            util.replace_file(
                os.path.expanduser('~/services-real/{}/run'.format(s)),
                runscript.format(**args),
                chmod=0o755
            )
            try:
                os.symlink(
                    os.path.expanduser('~/services-real/{}'.format(s)),
                    os.path.expanduser('~/services/{}'.format(s))
                )
            except FileExistsError:
                pass
        for s in self.service_names:
            svc_wait(s)
            svc_start(s)

    def deconfigure(self):
        for s in self.service_names:
            path = os.path.expanduser('~/services/{}'.format(s))
            if os.path.isdir(path):
                svc_destroy(s)
                shutil.rmtree(path)

    def enable_maintenance(self):
        super().enable_maintenance()
        for s in self.service_names:
            svc_stop(s)

    def disable_maintenance(self):
        super().disable_maintenance()
        self.configure()

    @classmethod
    def cleanup(cls):
        # avoid circle
        from ..repo import Repo

        runner_configs = set()
        for r in Repo.all():
            for b in r.branches.values():
                for runner in b.runners.values():
                    if isinstance(runner, cls):
                        runner_configs.update(runner.service_names)

        processes_to_delete = []
        for f in os.listdir(os.path.expanduser('~/services-real')):
            if f not in runner_configs:
                processes_to_delete.append(f)
        for p in processes_to_delete:
            svc_destroy(p)
