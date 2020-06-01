""" Backend that reads access control rules from config file """
import logging

from pyramid.settings import aslist

from .base_json import IJsonAccessBackend

LOG = logging.getLogger(__name__)


class ConfigAccessBackend(IJsonAccessBackend):

    """ Access Backend that uses values set in the config file """

    def __init__(self, request=None, data=None, **kwargs):
        super(ConfigAccessBackend, self).__init__(request, **kwargs)
        self._data = data

    @classmethod
    def configure(cls, settings):
        kwargs = super(ConfigAccessBackend, cls).configure(settings)
        data = {}

        users = {}
        for key, value in settings.items():
            if not key.startswith("user."):
                continue
            users[key[len("user.") :]] = value
        data["users"] = users

        data["admins"] = aslist(settings.get("auth.admins", []))

        groups = {}
        for key, value in settings.items():
            if not key.startswith("group."):
                continue
            groups[key[len("group.") :]] = aslist(value)
        data["groups"] = groups

        packages = {}
        for key, value in settings.items():
            pieces = key.split(".")
            if len(pieces) != 4 or pieces[0] != "package":
                continue
            _, package, mode, entity = pieces
            pkg_perms = packages.setdefault(package, {"users": {}, "groups": {}})
            if mode == "user":
                pkg_perms["users"][entity] = cls._perms_from_short(value)
            elif mode == "group":
                pkg_perms["groups"][entity] = cls._perms_from_short(value)
        data["packages"] = packages

        kwargs["data"] = data
        return kwargs

    def _get_db(self):
        return self._data

    @staticmethod
    def _perms_from_short(value):
        """ Convert a 'r' or 'rw' specification to a list of permissions """
        value = value or ""
        if len(value) > 2:
            return aslist(value)
        perms = []
        if "r" in value:
            perms.append("read")
        if "w" in value:
            perms.append("write")
        return perms

    def load(self, data):
        lines = []
        admins = []
        for user in data["users"]:
            lines.append("user.{username} = {password}".format(**user))
            if user.get("admin"):
                admins.append(user["username"])

        if admins:
            lines.append("auth.admins =")
            for admin in admins:
                lines.append("    {0}".format(admin))

        for group, members in data["groups"].items():
            lines.append("group.{0} =".format(group))
            for member in members:
                lines.append("    {0}".format(member))

        def encode_permissions(perms):
            """ Encode a permissions list as the r/rw specification """
            ret = ""
            if "read" in perms:
                ret += "r"
            if "write" in perms:
                ret += "w"
            return ret

        for package, groups in data["packages"]["groups"].items():
            for group, permissions in groups.items():
                lines.append(
                    "package.{0}.group.{1} = {2}".format(
                        package, group, encode_permissions(permissions)
                    )
                )

        for package, users in data["packages"]["users"].items():
            for user, permissions in users.items():
                lines.append(
                    "package.{0}.user.{1} = {2}".format(
                        package, user, encode_permissions(permissions)
                    )
                )

        return "\n".join(lines)
