""" Render views for logging in and out of the web interface """
from pyramid.httpexceptions import HTTPForbidden, HTTPFound
from pyramid.security import NO_PERMISSION_REQUIRED, forget, remember
from pyramid.view import view_config
from pyramid_duh import argify

from pypicloud.route import Root


@view_config(
    context=Root,
    name="login",
    request_method="GET",
    permission=NO_PERMISSION_REQUIRED,
    subpath=(),
    renderer="login.jinja2",
)
def get_login_page(request):
    """ Catch login and redirect to login wall """
    if request.userid is not None:
        # User is logged in and fetching /login, so redirect to /
        return HTTPFound(location=request.app_url())
    return {}


@view_config(
    context=HTTPForbidden, permission=NO_PERMISSION_REQUIRED, renderer="login.jinja2"
)
def do_forbidden(request):
    """ Intercept 403's and return 401's when necessary """
    return request.forbid()


@view_config(
    context=Root,
    name="login",
    request_method="POST",
    subpath=(),
    renderer="json",
    permission=NO_PERMISSION_REQUIRED,
)
@argify
def do_login(request, username, password):
    """ Check credentials and log in """
    if request.access.verify_user(username, password):
        request.response.headers.extend(remember(request, username))
        return {"next": request.app_url()}
    else:
        return HTTPForbidden()


def register_new_user(access, username, password):
    """ Register a new user & handle duplicate detection """
    if access.user_data(username) is not None:
        raise ValueError("User '%s' already exists!" % username)
    if username in access.pending_users():
        raise ValueError("User '%s' has already registered!" % username)
    access.register(username, password)
    if access.need_admin():
        access.approve_user(username)
        access.set_user_admin(username, True)
        return True
    return False


def handle_register_request(request, username, password):
    """ Process a request to register a new user """
    if not request.access.allow_register() and not request.access.need_admin():
        return HTTPForbidden()
    username = username.strip()
    try:
        if len(username) > 100 or len(username) < 1:
            raise ValueError("Username must be between 1 and 100 characters")
        if len(password) > 100:
            raise ValueError("Password cannot exceed 100 characters")
        if register_new_user(request.access, username, password):
            request.response.headers.extend(remember(request, username))
    except ValueError as e:
        request.response.status_code = 400
        return {"code": 400, "message": e.args[0]}
    return request.response


@view_config(
    context=Root,
    name="tokenRegister",
    request_method="PUT",
    subpath=(),
    renderer="json",
    permission=NO_PERMISSION_REQUIRED,
)
@argify
def do_token_register(request, token, password):
    """ Consume a signed token and create a new user """
    username = request.access.validate_signup_token(token)
    if username is None:
        raise ValueError("Invalid token")
    if request.access.user_data(username) is not None:
        raise ValueError("User %s already exists" % username)
    request.access.register(username, password)
    request.access.approve_user(username)
    request.response.headers.extend(remember(request, username))
    return {"next": request.app_url()}


@view_config(
    context=Root,
    name="login",
    request_method="PUT",
    subpath=(),
    renderer="json",
    permission=NO_PERMISSION_REQUIRED,
)
@argify
def register(request, username, password):
    """ Check credentials and log in """
    return handle_register_request(request, username, password)


@view_config(context=Root, name="logout", subpath=())
def logout(request):
    """ Delete the user session """
    request.response.headers.extend(forget(request))
    return HTTPFound(location=request.app_url())
