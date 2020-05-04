"""
Add github roles to sphinx docs.

Copied shamelessly from boto
(https://github.com/boto/boto)

"""
try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin

from docutils import nodes, utils
from docutils.parsers.rst.roles import set_classes


def make_node(rawtext, app, type_, slug, options):
    """ Create a github link """
    if app.config.github_user is None:
        raise ValueError("Configuration value for 'github_user' is not set.")
    base_url = "https://github.com/%s/%s/" % (
        app.config.github_user,
        app.config.project,
    )
    relative = "%s/%s" % (type_, slug)
    full_ref = urljoin(base_url, relative)
    set_classes(options)
    if type_ == "issues":
        type_ = "issue"
    node = nodes.reference(
        rawtext, type_ + " " + utils.unescape(slug), refuri=full_ref, **options
    )
    return node


def github_sha(name, rawtext, text, lineno, inliner, options=None, content=None):
    """ Link to a github commit """
    options = options or {}
    content = content or []
    app = inliner.document.settings.env.app
    node = make_node(rawtext, app, "commit", text, options)
    return [node], []


def github_issue(name, rawtext, text, lineno, inliner, options=None, content=None):
    """ Link to a github issue """
    options = options or {}
    content = content or []
    try:
        issue = int(text)
    except ValueError:
        msg = inliner.reporter.error(
            "Invalid Github Issue '%s', must be an integer" % text, line=lineno
        )
        problem = inliner.problematic(rawtext, rawtext, msg)
        return [problem], [msg]
    app = inliner.document.settings.env.app
    node = make_node(rawtext, app, "issues", str(issue), options)
    return [node], []


def github_pull_request(
    name, rawtext, text, lineno, inliner, options=None, content=None
):
    """ Link to a github pull request """
    options = options or {}
    content = content or []
    app = inliner.document.settings.env.app
    node = make_node(rawtext, app, "pull", text, options)
    return [node], []


def setup(app):
    """ Add github roles to sphinx """
    app.add_role("sha", github_sha)
    app.add_role("issue", github_issue)
    app.add_role("pr", github_pull_request)
    app.add_config_value("github_user", None, "env")
