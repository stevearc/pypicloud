""" Backend that uses a remote json file as remote database """

from .base import IMutableAccessBackend

"""
Secret should look like this on AWS:

{
  "users": {
    "user1": "hashed_password1",
    "user2": "hashed_password2",
    "user3": "hashed_password3",
    "user4": "hashed_password4",
    "user5": "hashed_password5",
  },
  "groups": {
    "admins": [
      "user1",
      "user2"
    ],
    "group1": [
      "user3"
    ]
  },
  "admins": [
       "user1"
  ]
  "packages": {
      "mypackage": {
          "groups": {
              "group1": ["read', "write"],
              "group2": ["read"],
              "group3": [],
          },
          "users": {
              "user1": ["read", "write"],
              "user2": ["read"],
              "user3": [],
              "user5": ["read"],
          }
      }
  },
  "pending_users": ["user5"],
  "allow_registration": true
}
"""


class IMutableJsonAccessDB(dict):
    def _fetch(self):
        """ Hit a server endpoint and return the json response as a dict"""
        raise NotImplementedError

    def save(self):
        """Save the json to the endpoint"""
        raise NotImplementedError


class IMutableJsonAccessBackend(IMutableAccessBackend):
    """
    This backend allows you to store all user and package permissions in
    a backend that is able to store a json file
    """

    def __init__(self, request=None, region=None, secret_id=None,
                 credentials=None, **kwargs):
        super(IMutableJsonAccessBackend, self).__init__(request, **kwargs)

    @property
    def db(self):
        if not hasattr(self, '_db'):
            self._db = self._get_db()
            self._add_missing_sections()
        return self._db

    def _add_missing_sections(self):
        if 'users' not in self._db:
            self.db['users'] = {}
        if 'admins' not in self._db:
            self.db['admins'] = []
        if 'groups' not in self._db:
            self.db['groups'] = {}
        if 'packages' not in self._db:
            self.db['packages'] = {}
        if 'pending_users' not in self._db:
            self.db['pending_users'] = {}

    def _get_db(self):
        raise NotImplementedError

    def _get_password_hash(self, username):
        return self.db['users'][username]

    def _set_password_hash(self, username, password_hash):
        self.db['users'][username] = password_hash
        self.db.save()

    def groups(self, username=None):
        if not username:
            return list(self.db['groups'].keys())
        ret_groups = []
        groups = self.db['groups']
        for group_name, users in groups.items():
            if username in users:
                ret_groups.append(group_name)
        return ret_groups

    def group_members(self, group):
        return list(self.db['groups'].get(group, []))

    def is_admin(self, username):
        return username in self.db['admins']

    def group_permissions(self, package):
        result = {}
        package_data = self.db['packages'].get(package, {})
        package_groups = package_data.get('groups', {})
        for group, permissions in package_groups.items():
            result[group] = permissions
        return result

    def user_permissions(self, package):
        result = {}
        package_data = self.db['packages'].get(package, {})
        package_users = package_data.get('users', {})
        for user, permissions in package_users.items():
            result[user] = permissions
        return result

    def user_package_permissions(self, username):
        packages = []
        for package_name, value in self.db['packages'].items():
            package_users = value.get('users', {})
            has_perms = username in package_users.keys()
            if has_perms:
                packages.append({
                    'package': package_name,
                    'permissions': package_users[username]
                })
        return packages

    def group_package_permissions(self, group):
        packages = []
        for package_name, value in self.db['packages'].items():
            package_groups = value.get('groups', {})
            has_perms = group in package_groups.keys()
            if has_perms:
                packages.append({
                    'package': package_name,
                    'permissions': package_groups.get(group, [])
                })
        return packages

    def _build_user(self, username, add_groups=False):
        admins = self.db['admins']
        is_pending = username in self.db['pending_users']
        if username not in self.db['users'] or is_pending:
            return None
        data = {
            'username': username,
            'admin': username in admins
        }
        if add_groups:
            data['groups'] = self.groups(username=username)
        return data

    def user_data(self, username=None):
        ret_users = []
        if username:
            return self._build_user(username, add_groups=True)
        for user in self.db['users']:
            user_data = self._build_user(user)
            if user_data is not None:
                ret_users.append(user_data)
        return ret_users

    def allow_register(self):
        return self.db.get('allow_registration', False)

    def _register(self, username, password):
        self.db['users'][username] = password
        self.db['pending_users'][username] = True
        self.db.save()

    def approve_user(self, username):
        self.db['pending_users'].pop(username, None)
        self.db.save()

    def delete_user(self, username):
        self.db['pending_users'].pop(username, None)
        self.db['users'].pop(username, None)

        for package in self.user_package_permissions(username):
            package = self.db['packages'][package['package']]
            package['users'].pop(username, None)
        for group in self.groups(username=username):
            self.db['groups'][group].remove(username)
        self.db.save()

    def pending_users(self):
        return list(self.db['pending_users'].keys())

    def create_group(self, group):
        self.db['groups'][group] = []
        self.db.save()

    def delete_group(self, group):
        self.db['groups'].pop(group, None)
        self.db.save()

    def edit_user_group(self, username, group, add):
        if add:
            self.db['groups'][group].append(username)
        else:
            self.db['groups'][group].remove(username)
        self.db.save()

    def _init_package(self, package):
        if package not in self.db['packages']:
            self.db['packages'][package] = {}
        if 'groups' not in self.db['packages'][package]:
            self.db['packages'][package]['groups'] = {}
        if 'users' not in self.db['packages'][package]:
            self.db['packages'][package]['users'] = {}

    def edit_group_permission(self, package, group, perm, add):
        self._init_package(package)
        if group not in self.db['packages'][package]['groups']:
            self.db['packages'][package]['groups'][group] = []
        if add:
            group_perms = (
                self.db['packages'][package]['groups'][group]
            )
            if perm not in group_perms:
                group_perms.append(perm)
            self.db['packages'][package]['groups'][group] = (
                group_perms
            )
        else:
            self.db['packages'][package]['groups'][group].remove(
                perm
            )
            if self.db['packages'][package]['groups'][group] == []:
                self.db['packages'][package]['groups'].pop(group)
        self.db.save()

    def edit_user_permission(self, package, username, perm, add):
        self._init_package(package)
        if username not in self.db['packages'][package]['users']:
            self.db['packages'][package]['users'][username] = []
        if add:
            user_perms = (
                self.db['packages'][package]['users'][username]
            )
            if perm not in user_perms:
                user_perms.append(perm)
            self.db['packages'][package]['users'][username] = (
                user_perms
            )
        else:
            self.db['packages'][package]['users'][username].remove(
                perm
            )
            user_perms = (
                self.db['packages'][package]['users'][username]
            )
            if user_perms == []:
                self.db['packages'][package]['users'].pop(
                    username
                )
        self.db.save()

    def set_user_admin(self, username, admin):
        if admin:
            self.db['admins'].append(username)
        else:
            self.db['admins'].remove(username)
        self.db.save()

    def set_allow_register(self, allow):
        self.db['allow_registration'] = allow
        self.db.save()
