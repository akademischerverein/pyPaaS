#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import copy
import shutil
import os.path
import datetime
import subprocess

from . import options
from . import util


class Checkout(object):
    def __init__(self, branch, commit, name):
        self.branch, self.commit, self.name = branch, commit, name

    @property
    def path(self):
        return os.path.join(
            options.BASEPATH, 'checkouts',
            self.branch.repo.name, self.branch.name,
            '{0}-{1}'.format(self.name, self.commit[:11])
        )

    @classmethod
    def create(cls, branch, commit):
        name = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self = cls(branch, commit, name)
        self.run_in(
            ['git', 'clone', '-q', self.branch.repo.path, self.path],
            env={},
            cwd=os.path.expanduser('~deploy')
        )
        self.run_in(
            ['git', 'config', 'advice.detachedHead', 'false'],
            env={}
        )
        self.run_in(
            ['git', 'checkout', self.commit],
            env={}
        )
        self.run_in(
            ['git', 'submodule', 'update', '--init', '--recursive'],
            env={}
        )
        to_delete = []
        for root, dirs, files in os.walk(self.path):
            for d in dirs:
                if d == '.git':
                    to_delete.append(os.path.join(root, d))
        for d in to_delete:
            shutil.rmtree(d)
        return self

    @property
    def cmd_env(self):
        env = dict()
        env.update(os.environ)
        if 'env' in self.branch.config:
            for k, v in self.branch.config['env'].items():
                env[k] = util.expandvars(v, env)
        env['GIT_COMMIT'] = self.commit
        return env

    @classmethod
    def all_for_branch(cls, branch):
        try:
            files = os.listdir(os.path.join(
                options.BASEPATH, 'checkouts', branch.repo.name, branch.name
            ))
        except FileNotFoundError:
            return
        for basename in files:
            f = os.path.join(
                options.BASEPATH, 'checkouts',
                branch.repo.name, branch.name, basename
            )
            if not os.path.isdir(f):
                continue
            name, commit = basename.split('-')
            yield cls(branch, commit, name)

    def run_hook_cmd(self, name, default=None):
        hook = self.branch.config.get('hooks', {}).get(name, default)
        if hook is None:
            return
        if not isinstance(hook, list):
            hook = [hook]
        for c in hook:
            self.run_in(c, shell=True)

    @property
    def custom_cmds(self):
        try:
            return self.branch.config['custom_cmds']
        except KeyError:
            return dict()

    def run_in(self, cmd, cwd=None, env=None, **kwargs):
        cwd = self.path if cwd is None else cwd
        env = self.cmd_env if env is None else env
        # necessary for capturing of the output by replacing sys.stderr
        subprocess.check_call(
            cmd,
            cwd=cwd,
            env=env,
            stderr=subprocess.STDOUT,
            **kwargs
        )

    def run_custom_cmd(self, name):
        self.run_in(self.custom_cmds[name], shell=True)

    def build(self):
        self.run_hook_cmd(
            name='build',
            default='if [ -f ./.build.sh ]; then ./.build.sh; fi'
        )

    def remove(self):
        shutil.rmtree(self.path)
