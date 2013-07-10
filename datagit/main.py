#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
#------------------------- =+- Python script -+= -------------------------
"""Interfaces to git and git-annex

 COPYRIGHT: Yaroslav Halchenko 2013

 LICENSE: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
"""

__author__ = 'Yaroslav Halchenko'
__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

from urlparse import urlparse

from .repos import *
from .db import load_db, save_db
from .network import fetch_page, parse_urls, filter_urls, \
      urljoin, download_url


def pprint_indent(l, indent="", fmt='%s'):
    return indent + ('\n%s' % indent).join([fmt % x for x in l])

# TODO: here figure it out either it will be a
# directory or not and either it needs to be extracted,
# and what will be the extracted directory name
def strippath(f, p):
    """Helper to deal with our mess -- strip path from front of filename f"""
    assert(f.startswith(p))
    f = f[len(p):]
    if f.startswith(os.path.sep):
        f = f[1:]
    return f

# TODO : add "memo" to avoid possible circular websites
def collect_urls(url, recurse=None, pages_cache=None):
    """Collects urls starting from url
    """
    page = (pages_cache and pages_cache.get(url, None)) or fetch_page(url)
    if pages_cache is not None:
        pages_cache[url] = page

    url_rec = urlparse(url)
    #
    # Parse out all URLs, as a tuple (url, a(text))
    urls_all = parse_urls(page)

    # Now we need to dump or recurse into some of them, e.g. for
    # directories etc
    urls = []
    if recurse:
        recurse_re = re.compile(recurse)
    for url_ in urls_all:
        # separate tuple out
        u, a = url_
        if u.endswith('/'):             # must be a directory
            if u in ('../', './'):
                lgr.debug("Skipping %s -- we are not going to parents" % u)
                continue
            if not recurse:
                lgr.debug("Skipping %s since no recursion" % u)
                continue
            if recurse_re.search(u):
                # then we should fetch the one as well
                u_rec = urlparse(u)
                u_full = urljoin(url, u)
                if u_rec.scheme:
                    if not (url_rec.netloc == u_rec.netloc and u_rec.path.startswith(rl_rec.path)):
                        # so we are going to a new page?
                        lgr.debug("Skipping %s since it jumps to another site from original %s" % (u, url))
                        #raise NotImplementedError("Cannot jump to other websites yet")
                        continue
                    # so we are staying on current website -- let it go
                lgr.debug("Recursing into %s, full: %s" % (u, u_full))
                new_urls = collect_urls(
                    u_full, recurse=recurse, pages_cache=pages_cache)
                # and add to their "hrefs" appropriate prefix
                urls.extend([(os.path.join(u, url__[0]),) + url__[1:]
                             for url__ in new_urls])
            else:
                lgr.debug("Skipping %s since doesn't match recurse" % u)
        else:
            urls.append(url_)

    lgr.info("Considering %d out of %d urls from %s"
             % (len(urls), len(urls_all), url))

    return urls

#
# Main loop
#
# TODO: formalize existing argument into option (+cmdline option?)
def rock_and_roll(cfg, existing='skip', dry_run=False, db_name = '.page2annex'):
    """Given a configuration fetch/update git-annex "clone"
    """

    # Let's output summary stats at the end
    stats = dict([(k, 0) for k in
                  ['sections', 'urls', 'allurls', 'downloads', 'annex_updates', 'size']])
    pages_cache = {}

    dry_str = "DRY: " if dry_run else ""

    incoming = cfg.get('DEFAULT', 'incoming')
    public = cfg.get('DEFAULT', 'public')

    #
    # Initializing file structure
    #
    if not (os.path.exists(incoming) and os.path.exists(public)):
        lgr.debug("%sCreating directories for incoming (%s) and public (%s) annexes"
                  % (dry_str, incoming, public))

        if not dry_run:
            if not os.path.exists(incoming):
                os.makedirs(incoming)
            if not os.path.exists(public):
                os.makedirs(public)           #TODO might be the same

    public_annex = AnnexRepo(public, dry_run=dry_run)
    description = cfg.get('DEFAULT', 'description')
    if not os.path.exists(os.path.join(public, '.git', 'annex')):
        public_annex.init(description)

    if public != incoming:
        incoming_annex = AnnexRepo(incoming, dry_run=dry_run)
        incoming_annex.init(description + ' (incoming)')
    else:
        incoming_annex = public_annex

    # TODO: load previous status info
    """We need

    incoming -- to track their mtime/size and urls.
      URLs might or might not provide Last-Modified,
      so if not provided, would correspond to None and only look by url change pretty much
      keeping urls would allow for a 'quick' check mode where we would only check
      if file is known

    public_incoming -- to have clear correspondence between annex_filename and incoming (which in turn with url).
                   annex_filename might correspond to a directory where we would
                   extract things, so we can't just geturl on it
    """

    db_path = os.path.join(incoming, db_name)
    if os.path.exists(db_path):
        db = load_db(db_path)
    else:
        # create fresh
        db = dict(incoming={},   # incoming_filename -> (url, mtime, size (AKA Content-Length, os.stat().st_size ))
                  public_incoming={}) # annex_filename -> incoming_filename

    db_incoming = db['incoming']
    # reverse map: url -> incoming
    db_incoming_urls = dict([(v['url'], i) for i,v in db_incoming.iteritems()])
    db_public_incoming = db['public_incoming']

    # TODO: look what is in incoming for this "repository", so if
    # some urls are gone or changed so previous file is not there
    # we would clean-up upon exit

    # each section defines a separate download setup
    for section in cfg.sections():
        lgr.info("Section: %s" % section)
        stats['sections'] += 1

        # some checks
        add_mode = cfg.get(section, 'mode')
        assert(add_mode in ['download', 'fast', 'relaxed'])

        repo_sectiondir = cfg.get(section, 'directory')

        full_incoming_sectiondir = os.path.join(incoming, repo_sectiondir)
        full_public_sectiondir = os.path.join(public, repo_sectiondir)

        if not (os.path.exists(incoming) and os.path.exists(public)):
            lgr.debug("%sCreating directories for section's incoming (%s) and public (%s) annexes"
                      % (dry_str, full_incoming_sectiondir, full_public_sectiondir))
            if not dry_run:
                os.makedirs(full_incoming_sectiondir)
                os.makedirs(full_public_sectiondir)           #TODO might be the same

        scfg = dict(cfg.items(section))

        archives_destiny = scfg.get('archives_destiny')
        if archives_destiny == 'auto':
            archives_destiny = 'rm' if incoming == public else 'annex'

        # Fetching the page (possibly again! thus a dummy pages_cache)
        top_url = scfg['url'].replace('/./', '/')
        if '..' in top_url:
            raise ValueError("Some logic would fail with relative paths in urls, "
                             "please adjust %s" % scfg['url'])
        urls_all = collect_urls(top_url, recurse=scfg['recurse'], pages_cache=pages_cache)


        #lgr.debug("%d urls:\n%s" % (len(urls_all), pprint_indent(urls_all, "    ", "[%s](%s)")))

        # Filter them out
        urls = filter_urls(urls_all, **dict(
            [(k,scfg[k]) for k in
             ('include_href', 'exclude_href',
              'include_href_a', 'exclude_href_a')]))
        lgr.info("%d out of %d urls survived filtering"
                 % (len(urls), len(urls_all)))
        if len(set(urls)) < len(urls):
            urls = sorted(set(urls))
            lgr.info("%d unique urls" % (len(urls),))
        lgr.debug("%d urls:\n%s"
                  % (len(urls), pprint_indent(urls, "    ", "[%s](%s)")))
        if scfg.get('check_url_limit', None):
            limit = int(scfg['check_url_limit'])
            if limit and len(urls) > limit:
                raise RuntimeError(
                    "Cannot process section since we expected only %d urls"
                    % limit)

        #
        # Process urls
        stats['allurls'] += len(urls)
        for href, href_a in urls:
            # bring them into the full urls, href might have been a full url on its own
            href_full = urljoin(top_url, href)
            lgr.debug("Working on [%s](%s)" % (href_full, href_a))

            if href_full in db_incoming_urls:
                # might need to go around download_url, so we might
                # still add it to annex happen download was done but annexing not
                if existing == 'skip':
                    lgr.debug("Skipping since known to db already and existing='skip'")
                    continue

            # We need to decide either some portion of href path
            # should be "maintained", e.g. in cases where we recurse
            # TODO: make stripping/directories optional/configurable
            # so we are simply deeper on the same site
            href_dir = os.path.dirname(href_full[len(top_url):].lstrip(os.path.sep)) \
                if href_full.startswith(top_url) else ''

            # It will adjust db_incoming in-place
            repo_filename, href_updated = \
              download_url(href_full, incoming,
                           os.path.join(repo_sectiondir, href_dir),
                           db_incoming=db_incoming, dry_run=dry_run,
                           fast_mode=add_mode in ['fast', 'relaxed'])

            full_filename = os.path.join(incoming, repo_filename)
            if href_updated:
                stats['downloads'] += 1
                stats['size'] += os.stat(full_filename).st_size
                if not dry_run:
                    save_db(db, db_path)

            # TODO: should _filename become _incoming_filename and
            # annex_filename -> public_filename?
            #
            try:
                repo_annex_filename = eval(scfg['filename'], {},
                                           dict(filename=repo_filename,
                                                ))
            except:
                raise ValueError("Failed to evaluate %r" % scfg['filename'])

            annex_updated = False
            if href_updated or (not repo_annex_filename in db_public_incoming):

                # Place them under git-annex, if they do not exist already
                #if href.endswith('gz'):
                #    import pydb; pydb.debugger()

                repo_public_filename = annex_file(
                    href_full,
                    incoming_filename=repo_filename,
                    annex_filename=repo_annex_filename, # full_annex_filename,
                    incoming_annex=incoming_annex,
                    public_annex=public_annex,
                    archives_destiny=archives_destiny,
                    archives_re=scfg.get('archives_re'),
                    add_mode=add_mode,
                    addurl_opts=scfg.get('addurl_opts', None),
                    dry_run=dry_run,
                    )

                db_public_incoming[repo_annex_filename] = repo_public_filename
                annex_updated = True
                stats['annex_updates'] += 1
            else:
                # TODO: shouldn't we actually check???
                lgr.debug("Skipping annexing %s since it must be there already"
                          % repo_annex_filename)

            if not dry_run and (annex_updated or href_updated):
                save_db(db, db_path)

            stats['urls'] += 1

    stats_str = "Processed %(sections)d sections, %(urls)d (out of %(allurls)d) urls, " \
                "%(downloads)d downloads with %(size)d bytes. " \
                "Made %(annex_updates)s git/annex additions/updates" % stats

    git_commit(incoming, files=[db_name], dry_run=dry_run,
               msg="page2annex(incoming): " + stats_str)
    if incoming != public:
        git_commit(public, dry_run=dry_run, msg="page2annex(public): " + stats_str)

    lgr.info(stats_str)

    if dry_run:
        # print all accumulated commands
        for cmd in getstatusoutput.commands:
            lgr.info("DRY: %s" % cmd)
    else:
        # Once again save the DB -- db might have been changed anyways
        save_db(db, db_path)

    return stats
