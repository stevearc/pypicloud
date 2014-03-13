""" Backend that reads access control rules from config file """
import logging
from collections import defaultdict
from pyramid.security import Everyone, Authenticated
from pyramid.settings import aslist, asbool

from .base import IAccessBackend


LOG = logging.getLogger(__name__)


class ConfigAccessBackend(IAccessBackend):

    """ Access Backend that uses values set in the config file """

    def __init__(self, request=None, settings=None, admins=None,
                 group_map=None, user_groups=None, **kwargs):
        super(ConfigAccessBackend, self).__init__(request, **kwargs)
        self._settings = settings
        self.admins = admins
        self.group_map = group_map
        self.user_groups = user_groups

    @classmethod
    def configure(cls, settings):
        kwargs = super(ConfigAccessBackend, cls).configure(settings)
        if asbool(settings.get('auth.zero_security_mode', False)):
            LOG.warn("Using deprecated option 'auth.zero_security_mode' "
                     "(replaced by 'pypi.default_read' and "
                     "'pypi.default_write'")
            kwargs['default_read'] = [Everyone]
            kwargs['default_write'] = [Authenticated]
        kwargs['settings'] = settings
        kwargs['admins'] = aslist(settings.get('auth.admins', []))
        user_groups = defaultdict(list)
        group_map = {}

        # Build dict that maps users to list of groups
        for key, value in settings.iteritems():
            if not key.startswith('group.'):
                continue
            group_name = key[len('group.'):]
            members = aslist(value)
            group_map[group_name] = members
            for member in members:
                user_groups[member].append(group_name)
        kwargs['group_map'] = group_map
        kwargs['user_groups'] = user_groups
        return kwargs

    def _get_password_hash(self, username):
        key = "user.%s" % username
        return self._settings.get(key)

    def groups(self, username=None):
        if username is None:
            return self.group_map.keys()
        else:
            return self.user_groups[username]

    def group_members(self, group):
        return self.group_map.get(group, [])

    def is_admin(self, username):
        return username in self.admins

    @staticmethod
    def _perms_from_short(value):
        """ Convert a 'r' or 'rw' specification to a list of permissions """
        value = value or ''
        perms = []
        if 'r' in value:
            perms.append('read')
        if 'w' in value:
            perms.append('write')
        return perms

    def group_permissions(self, package, group=None):
        if group is not None:
            key = 'package.%s.group.%s' % (package, group)
            return self._perms_from_short(self._settings.get(key))
        perms = {}
        group_prefix = 'package.%s.group.' % package
        for key, value in self._settings.iteritems():
            if not key.startswith(group_prefix):
                continue
            group = key[len(group_prefix):]
            perms[group] = self._perms_from_short(value)
        return perms

    def user_permissions(self, package, username=None):
        if username is not None:
            key = 'package.%s.user.%s' % (package, username)
            return self._perms_from_short(self._settings.get(key))
        perms = {}
        user_prefix = 'package.%s.user.' % package
        for key, value in self._settings.iteritems():
            if not key.startswith(user_prefix):
                continue
            user = key[len(user_prefix):]
            perms[user] = self._perms_from_short(value)
        return perms

    def user_data(self, username=None):
        if username is not None:
            return {
                'username': username,
                'admin': self.is_admin(username),
                'groups': self.groups(username),
            }
        users = []
        user_prefix = 'user.'
        for key in self._settings:
            if not key.startswith(user_prefix):
                continue
            username = key[len(user_prefix):]
            users.append({
                'username': username,
                'admin': self.is_admin(username)
            })
        return users

    def user_package_permissions(self, username):
        perms = []
        for key, value in self._settings.iteritems():
            pieces = key.split('.')
            if (len(pieces) != 4 or pieces[0] != 'package' or
                    pieces[2] != 'user'):
                continue
            package, user = pieces[1], pieces[3]
            if user == username:
                perms.append({
                    'package': package,
                    'permissions': self._perms_from_short(value),

                })
        return perms

    def group_package_permissions(self, group):
        perms = []
        for key, value in self._settings.iteritems():
            pieces = key.split('.')
            if (len(pieces) != 4 or pieces[0] != 'package' or
                    pieces[2] != 'group'):
                continue
            package, groupname = pieces[1], pieces[3]
            if group == groupname:
                perms.append({
                    'package': package,
                    'permissions': self._perms_from_short(value),

                })
        return perms

    def load(self, data):
        lines = []
        admins = []
        for user in data['users']:
            lines.append('user.{username} = {password}'.format(**user))
            if user.get('admin'):
                admins.append(user['username'])

        if admins:
            lines.append('auth.admins =')
            for admin in admins:
                lines.append('    {0}'.format(admin))

        for group, members in data['groups'].iteritems():
            lines.append('group.{0} ='.format(group))
            for member in members:
                lines.append('    {0}'.format(member))

        def encode_permissions(perms):
            """ Encode a permissions list as the r/rw specification """
            ret = ''
            if 'read' in perms:
                ret += 'r'
            if 'write' in perms:
                ret += 'w'
            return ret

        for package, groups in data['packages']['groups'].iteritems():
            for group, permissions in groups.iteritems():
                lines.append('package.{0}.group.{1} = {2}'
                             .format(package, group,
                                     encode_permissions(permissions)))

        for package, users in data['packages']['users'].iteritems():
            for user, permissions in users.iteritems():
                lines.append('package.{0}.user.{1} = {2}'
                             .format(package, user,
                                     encode_permissions(permissions)))

        return '\n'.join(lines)
