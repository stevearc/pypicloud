""" Abstract backends that are backed by simple JSON """

from .base import IAccessBackend, IMutableAccessBackend


class IJsonAccessBackend(IAccessBackend):
    """
    This backend reads the permissions from anything that can provide JSON data

    Notes
    -----
    JSON should look like this::

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
            }
        }
    """

    _db = None

    @property
    def db(self):
        """ Fetch JSON and cache it for future calls """
        if self._db is None:
            self._db = self._get_db()
            for key in ["users", "groups", "packages", "pending_users"]:
                self._db.setdefault(key, {})
            self._db.setdefault("admins", [])
        return self._db

    def _get_db(self):
        """
        Actually fetch the remote json. This method should return an instance
        of a child class of IMutableJsonAccessDB.
        """
        raise NotImplementedError

    def _get_password_hash(self, username):
        return self.db["users"].get(username)

    def groups(self, username=None):
        if not username:
            return list(self.db["groups"].keys())
        ret_groups = []
        groups = self.db["groups"]
        for group_name, users in groups.items():
            if username in users:
                ret_groups.append(group_name)
        return ret_groups

    def group_members(self, group):
        return list(self.db["groups"].get(group, []))

    def is_admin(self, username):
        return username in self.db["admins"]

    def group_permissions(self, package):
        result = {}
        package_data = self.db["packages"].get(package, {})
        package_groups = package_data.get("groups", {})
        for group, permissions in package_groups.items():
            result[group] = permissions
        return result

    def user_permissions(self, package):
        result = {}
        package_data = self.db["packages"].get(package, {})
        package_users = package_data.get("users", {})
        for user, permissions in package_users.items():
            result[user] = permissions
        return result

    def user_package_permissions(self, username):
        packages = []
        for package_name, value in self.db["packages"].items():
            package_users = value.get("users", {})
            has_perms = username in package_users
            if has_perms:
                packages.append(
                    {"package": package_name, "permissions": package_users[username]}
                )
        return packages

    def group_package_permissions(self, group):
        packages = []
        for package_name, value in self.db["packages"].items():
            package_groups = value.get("groups", {})
            has_perms = group in package_groups.keys()
            if has_perms:
                packages.append(
                    {
                        "package": package_name,
                        "permissions": package_groups.get(group, []),
                    }
                )
        return packages

    def user_data(self, username=None):
        admins = self.db["admins"]
        if username:
            if username not in self.db["users"]:
                return None
            return {
                "username": username,
                "admin": username in admins,
                "groups": self.groups(username),
            }
        return [
            {"username": username, "admin": username in admins}
            for username in self.db["users"]
        ]


class IMutableJsonAccessBackend(IJsonAccessBackend, IMutableAccessBackend):
    """
    This backend allows you to store all user and package permissions in
    a backend that is able to store a json file

    Notes
    -----
    The format is the same as
    :class:`~pypicloud.access.base_json.IJsonAccessBackend`, but with the
    additional fields::

        {
            "pending_users": {
                "user1": "hashed_password1",
                "user2": "hashed_password2"
            },
            "allow_registration": true
        }

    """

    mutable = True

    def _save(self):
        """ Save the JSON to the backend """
        raise NotImplementedError

    def _set_password_hash(self, username, password_hash):
        self.db["users"][username] = password_hash
        self._save()

    def allow_register(self):
        return self.db.get("allow_registration", False)

    def _register(self, username, password):
        self.db["pending_users"][username] = password
        self._save()

    def approve_user(self, username):
        password = self.db["pending_users"].pop(username, None)
        if password is not None:
            self.db["users"][username] = password
        self._save()

    def delete_user(self, username):
        self.db["pending_users"].pop(username, None)
        self.db["users"].pop(username, None)

        for package_name, value in self.db["packages"].items():
            if "users" in value:
                value["users"].pop(username, None)
        for group_name, users in self.db["groups"].items():
            try:
                users.remove(username)
            except ValueError:
                pass
        self._save()

    def pending_users(self):
        return list(self.db["pending_users"].keys())

    def create_group(self, group):
        self.db["groups"][group] = []
        self._save()

    def delete_group(self, group):
        self.db["groups"].pop(group, None)
        self._save()

    def edit_user_group(self, username, group, add):
        if add:
            self.db["groups"][group].append(username)
        else:
            self.db["groups"][group].remove(username)
        self._save()

    def _init_package(self, package):
        """
        Make sure the root requested package and its child nodes exist in
        the database.
        """
        self.db["packages"].setdefault(package, {})
        self.db["packages"][package].setdefault("groups", {})
        self.db["packages"][package].setdefault("users", {})

    def edit_group_permission(self, package_name, group, perm, add):
        if perm != "read" and perm != "write":
            raise ValueError("Unrecognized permission '%s'" % perm)
        self._init_package(package_name)
        package = self.db["packages"][package_name]
        if group not in package["groups"]:
            package["groups"][group] = []
        if add:
            group_perms = package["groups"][group]
            if perm not in group_perms:
                group_perms.append(perm)
            package["groups"][group] = group_perms
        else:
            package["groups"][group].remove(perm)
            if package["groups"][group] == []:
                package["groups"].pop(group)
        self._save()

    def edit_user_permission(self, package_name, username, perm, add):
        if perm != "read" and perm != "write":
            raise ValueError("Unrecognized permission '%s'" % perm)
        self._init_package(package_name)
        package = self.db["packages"][package_name]
        if username not in package["users"]:
            package["users"][username] = []
        if add:
            user_perms = package["users"][username]
            if perm not in user_perms:
                user_perms.append(perm)
            package["users"][username] = user_perms
        else:
            try:
                package["users"][username].remove(perm)
            except ValueError:
                pass
            user_perms = package["users"][username]
            if user_perms == []:
                package["users"].pop(username)
        self._save()

    def set_user_admin(self, username, admin):
        if admin:
            self.db["admins"].append(username)
        else:
            self.db["admins"].remove(username)
        self._save()

    def set_allow_register(self, allow):
        self.db["allow_registration"] = allow
        self._save()
