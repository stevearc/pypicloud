""" Backend that reads access control rules from config file """
from collections import defaultdict
from pyramid.security import (Authenticated, Everyone, Allow, Deny,
                              ALL_PERMISSIONS)
from pyramid.settings import asbool, aslist

from .base import IAccessBackend


class ConfigAccessBackend(IAccessBackend):

    """ Access Backend that uses values set in the config file """

    @classmethod
    def configure(cls, settings):
        super(ConfigAccessBackend, cls).configure(settings)
        cls._settings = settings
        cls.zero_security_mode = asbool(settings.get('auth.zero_security_mode',
                                                     False))
        cls.admins = aslist(settings.get('auth.admins', []))
        cls.user_groups = defaultdict(list)
        cls.group_map = {}

        if cls.zero_security_mode:
            cls.ROOT_ACL = [
                (Allow, Everyone, 'login'),
                (Allow, Everyone, 'read'),
                (Allow, Authenticated, 'write'),
                (Allow, 'admin', ALL_PERMISSIONS),
                (Deny, Everyone, ALL_PERMISSIONS),
            ]
        else:
            cls.ROOT_ACL = IAccessBackend.ROOT_ACL

        # Build dict that maps users to list of groups
        for key, value in settings.iteritems():
            if not key.startswith('group.'):
                continue
            group_name = key[len('group.'):]
            members = aslist(value)
            cls.group_map[group_name] = members
            for member in members:
                cls.user_groups[member].append(group_name)

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
            perms = self._perms_from_short(self._settings.get(key))
            if (self.zero_security_mode and group == 'everyone' and
                    'read' not in perms):
                perms.append('read')
            return perms
        perms = {}
        group_prefix = 'package.%s.group.' % package
        for key, value in self._settings.iteritems():
            if not key.startswith(group_prefix):
                continue
            group = key[len(group_prefix):]
            perms[group] = self._perms_from_short(value)
        if self.zero_security_mode:
            perms.setdefault('everyone', [])
            if 'read' not in perms['everyone']:
                perms['everyone'].append('read')
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

    def get_acl(self, package):
        if self.zero_security_mode:
            return []
        return super(ConfigAccessBackend, self).get_acl(package)

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
