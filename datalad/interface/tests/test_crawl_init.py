# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##


from nose.tools import eq_, assert_raises
from mock import patch
from ...api import crawl_init
from collections import OrderedDict
from os import remove
from os.path import exists
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import with_tempfile, chpwd
from datalad.consts import CRAWLER_META_CONFIG_PATH, CRAWLER_META_DIR


@with_tempfile(mkdir=True)
def _test_crawl_init(args, template, template_func, target_value, tmpdir):
    ar = AnnexRepo(tmpdir, create=True)
    with chpwd(tmpdir):
        crawl_init(args=args, template=template, template_func=template_func)
        eq_(exists(CRAWLER_META_DIR), True)
        eq_(exists(CRAWLER_META_CONFIG_PATH), True)
        f = open(CRAWLER_META_CONFIG_PATH, 'r')
        contents = f.read()
        eq_(contents, target_value)


def test_crawl_init():
    yield _test_crawl_init, None, 'openfmri', 'superdataset_pipeline', \
          '[crawl:pipeline]\ntemplate = openfmri\nfunc = superdataset_pipeline\n\n'
    yield _test_crawl_init, {'dataset': 'ds000001'}, 'openfmri', None, \
          '[crawl:pipeline]\ntemplate = openfmri\n_dataset = ds000001\n\n'
    yield _test_crawl_init, ['dataset=ds000001', 'versioned_urls=True'], 'openfmri', None, \
          '[crawl:pipeline]\ntemplate = openfmri\n_dataset = ds000001\n_versioned_urls = True\n\n'


@with_tempfile(mkdir=True)
def _test_crawl_init_error(args, template, template_func, target_value, tmpdir):
        ar = AnnexRepo(tmpdir)
        with chpwd(tmpdir):
            assert_raises(target_value, crawl_init, args=args, template=template, template_func=template_func)


def test_crawl_init_error():
    yield _test_crawl_init_error, 'tmpdir', None, None, ValueError
    yield _test_crawl_init_error, ['dataset=Baltimore', 'pie=True'], 'openfmri', None, RuntimeError


@with_tempfile(mkdir=True)
def _test_crawl_init_error_patch(return_value, exc, exc_msg, d):

    ar = AnnexRepo(d, create=True)
    with patch('datalad.interface.crawl_init.load_pipeline_from_template',
               return_value=lambda dataset: return_value) as cm:
        with chpwd(d):
            try:
                crawl_init(args=['dataset=Baltimore'], template='openfmri')
            except Exception as e:
                eq_(type(e), exc)
                eq_(str(e), exc_msg)

            cm.assert_called_with('openfmri', None, return_only=True, kwargs=OrderedDict([('dataset', 'Baltimore')]))


def test_crawl_init_error_patch():
    yield _test_crawl_init_error_patch, [], ValueError, "returned pipeline is empty"
    yield _test_crawl_init_error_patch, {1: 2}, ValueError, "pipeline should be represented as a list. Got: {1: 2}"
