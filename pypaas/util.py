#!/usr/bin/env python
# -*- coding: utf-8 -*-

import errno
import functools
import os
import os.path
import re


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def replace_file(filename, new_contents, chmod=None):
    """
    Leaves either the old file, the old file and a .new file or the new file.

    Writes to .new, calls fsync and then renames to the original filename.
    """
    with open(filename + '.new', 'w') as newf:
        newf.write(new_contents)
        newf.flush()
        if chmod is not None:
            os.chmod(filename + '.new', chmod)
        os.fsync(newf.fileno())
    os.rename(filename + '.new', filename)


_varprog = None


def expandvars(value, vars, max_matches=50):
    """
    Based on os.path.expandvars
    """
    global _varprog
    if '$' not in value:
        return value
    if not _varprog:
        _varprog = re.compile(r'\$(\w+|\{[^}]*\})', re.ASCII)
    
    i = 0
    matches = 0
    while True:
        m = _varprog.search(value, i)
        if not m:
            return value
        matches += 1
        if matches == max_matches:
            raise RuntimeError('exhausted max_matches')
        i, j = m.span(0)
        name = m.group(1)
        if name.startswith('{') and name.endswith('}'):
            name = name[1:-1]
        
        try:
            var_value = vars[name]
        except:
            i = j
        else:
            tail = value[j:]
            head = value[:i] + var_value
            i = len(head)
            value = head + tail
