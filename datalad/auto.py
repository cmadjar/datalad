# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Proxy basic file operations (such as open) to obtain files automagically upon I/O
"""

from mock import patch
from six import PY2
import six.moves.builtins as __builtin__

import logging

from os.path import dirname, abspath, pardir, join as opj, exists, basename

from .support.annexrepo import AnnexRepo
from .support.gitrepo import GitRepo
from .support.exceptions import CommandError
from .cmd import Runner

from .utils import swallow_outputs
lgr = logging.getLogger("datalad.auto")


# TODO: shouldn't be some classmethod of GitRepo?
_git_runner = Runner()
def _is_file_under_git(f):
    fpath = abspath(f)
    fdir = dirname(fpath)
    fname = basename(fpath)
    try:
        with swallow_outputs():
            _git_runner.run(["git", "ls-files", fname, "--error-unmatch"], cwd=fdir,
                            log_stdout=False, log_stderr=False, expect_fail=True,
                            expect_stderr=True)
        return True
    except CommandError:
        return False

class _EarlyExit(Exception):
    """Helper to early escape try/except logic in wrappde open"""
    pass

class AutomagicIO(object):

    def __init__(self, autoget=True, activate=False):
        self._active = False
        self._builtin_open = __builtin__.open
        self._autoget = autoget
        self._in_open = False
        if activate:
            self.activate()

    @property
    def autoget(self):
        return self._autoget

    @property
    def active(self):
        return self._active

    def _open(self, *args, **kwargs):
        """Proxy for open

        """
        # wrap it all for resilience to errors -- proxying must do no harm!
        try:
            if self._in_open:
                raise _EarlyExit
            self._in_open = True  # just in case someone kept alias/assignment
            # return stock open for the duration of handling so that
            # logging etc could workout correctly
            with patch('__builtin__.open', self._builtin_open):
                lgr.log(1, "Proxying open with %r %r", args, kwargs)

                # had to go with *args since in PY2 it is name, in PY3 file
                # deduce arguments
                if len(args) > 0:
                    # name/file was provided
                    file = args[0]
                else:
                    filearg = "name" if PY2 else "file"
                    if filearg not in kwargs:
                        # so the name was missing etc, just proxy into original open call and let it puke
                        lgr.debug("No name/file was given, avoiding proxying")
                        raise _EarlyExit
                    file = kwargs.get(filearg)

                if not _is_file_under_git(file):
                    raise _EarlyExit  # just to proceed to stock open

                mode = 'r'
                if len(args) > 1:
                    mode = args[1]
                elif 'mode' in kwargs:
                    mode = kwargs['mode']

                if 'r' in mode:
                    # deduce directory for file
                    filedir = dirname(file)
                    repotop = GitRepo.get_toppath(filedir)
                    # TODO: verify logic for create -- we shouldn't 'annexify' non-annexified
                    # see https://github.com/datalad/datalad/issues/204
                    annex = AnnexRepo(repotop, create=True) # if got there -- must be a git repo
                    # either it has content
                    if not annex.file_has_content(file):
                        lgr.info("File %s has no content -- retrieving", file)
                        annex.annex_get(file)
                else:
                    lgr.debug("Skipping operation on %s since mode=%r", file, mode)
        except _EarlyExit:
            pass
        except Exception as e:
            # If anything goes wrong -- we should complain and proceed
            with patch('__builtin__.open', self._builtin_open):
                lgr.warning("Failed proxying open with %r, %r: %s", args, kwargs, e)
        finally:
            self._in_open = False
        # finally give it back to stock open
        return self._builtin_open(*args, **kwargs)

    def activate(self):
        if self.active:
            lgr.warning("%s already active. No action taken" % self)
            return
        # overloads
        __builtin__.open = self._open
        self._active = True

    def deactivate(self):
        if not self.active:
            lgr.warning("%s is not active, can't deactivate" % self)
            return
        __builtin__.open = self._builtin_open
        self._active = False

    def __del__(self):
        if self._active:
            self.deactivate()
        try:
            super(self.__class__, self).__del__()
        except Exception:
            pass