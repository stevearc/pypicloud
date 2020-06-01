""" Access backend for storing permissions in using SQLAlchemy """
import zope.sqlalchemy
from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    String,
    Table,
    Text,
    engine_from_config,
    orm,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, sessionmaker

from .base import IMutableAccessBackend

# pylint: disable=C0103,W0231
Base = declarative_base()

association_table = Table(
    "pypicloud_user_groups",
    Base.metadata,
    Column(
        "username",
        String(length=255),
        ForeignKey("pypicloud_users.username", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "group",
        String(length=255),
        ForeignKey("pypicloud_groups.name", ondelete="CASCADE"),
        primary_key=True,
    ),
)
# pylint: enable=C0103


class KeyVal(Base):

    """ Simple model for storing key-value pairs """

    __tablename__ = "pypicloud_keyvals"
    key = Column(String(length=255), primary_key=True)
    value = Column(Text())

    def __init__(self, key, value):
        self.key = key
        self.value = value


class User(Base):

    """ User record """

    __tablename__ = "pypicloud_users"
    username = Column(String(length=255), primary_key=True)
    password = Column("password", Text(), nullable=False)
    admin = Column(Boolean(), nullable=False)
    pending = Column(Boolean(), nullable=False)
    groups = orm.relationship(
        "Group",
        secondary=association_table,
        cascade="all",
        collection_class=set,
        backref=backref("users", collection_class=set),
    )

    def __init__(self, username, password, pending=True):
        self.username = username
        self.password = password
        self.groups = set()
        self.permissions = []
        self.admin = False
        self.pending = pending


class Group(Base):

    """ Group record """

    __tablename__ = "pypicloud_groups"
    name = Column(String(length=255), primary_key=True)

    def __init__(self, name):
        self.name = name
        self.users = set()
        self.permissions = []


class Permission(Base):

    """ Base class for user and group permissions """

    __abstract__ = True
    package = Column(String(length=255), primary_key=True)
    read = Column(Boolean())
    write = Column(Boolean())

    def __init__(self, package, read, write):
        self.package = package
        self.read = read
        self.write = write

    @property
    def permissions(self):
        """ Construct permissions list """
        perms = []
        if self.read:
            perms.append("read")
        if self.write:
            perms.append("write")
        return perms


class UserPermission(Permission):

    """ Permissions for a user on a package """

    __tablename__ = "pypicloud_user_permissions"
    username = Column(
        String(length=255),
        ForeignKey(User.username, ondelete="CASCADE"),
        primary_key=True,
    )
    user = orm.relationship(
        "User", backref=backref("permissions", cascade="all, delete-orphan")
    )

    def __init__(self, package, username, read=False, write=False):
        super(UserPermission, self).__init__(package, read, write)
        self.username = username


class GroupPermission(Permission):

    """ Permissions for a group on a package """

    __tablename__ = "pypicloud_group_permissions"
    groupname = Column(
        String(length=255), ForeignKey(Group.name, ondelete="CASCADE"), primary_key=True
    )
    group = orm.relationship(
        "Group", backref=backref("permissions", cascade="all, delete-orphan")
    )

    def __init__(self, package, groupname, read=False, write=False):
        super(GroupPermission, self).__init__(package, read, write)
        self.groupname = groupname


class SQLAccessBackend(IMutableAccessBackend):

    """
    This backend allows you to store all user and package permissions in a SQL
    database

    """

    def __init__(self, request=None, dbmaker=None, **kwargs):
        super(SQLAccessBackend, self).__init__(request, **kwargs)
        self._db = None
        self._dbmaker = dbmaker

    @property
    def db(self):
        """ Lazy-create the DB session """
        if self._db is None:
            self._db = self._dbmaker()
            if self.request is not None:
                zope.sqlalchemy.register(self._db, transaction_manager=self.request.tm)
        return self._db

    @classmethod
    def configure(cls, settings):
        kwargs = super(SQLAccessBackend, cls).configure(settings)
        engine = engine_from_config(settings, prefix="auth.db.")
        kwargs["dbmaker"] = sessionmaker(bind=engine)
        # Create SQL schema if not exists
        Base.metadata.create_all(bind=engine)
        return kwargs

    @classmethod
    def postfork(cls, **kwargs):
        # Have to dispose of connections after uWSGI forks,
        # otherwise they'll get corrupted.
        kwargs["dbmaker"].kw["bind"].dispose()

    def allow_register(self):
        ret = self.db.query(KeyVal).filter_by(key="allow_register").first()
        return ret is not None and ret.value == "true"

    def set_allow_register(self, allow):
        if allow:
            k = KeyVal("allow_register", "true")
            self.db.merge(k)
        else:
            self.db.query(KeyVal).filter_by(key="allow_register").delete()

    def _get_password_hash(self, username):
        user = self.db.query(User).filter_by(username=username).first()
        if user:
            return user.password

    def groups(self, username=None):
        if username is None:
            query = self.db.query(Group)
            return [g.name for g in query]
        else:
            user = self.db.query(User).filter_by(username=username).first()
            if user is None:
                return []
            return [g.name for g in user.groups]

    def group_members(self, group):
        g = self.db.query(Group).filter_by(name=group).first()
        if not g:
            return []
        return [u.username for u in g.users]

    def is_admin(self, username):
        user = self.db.query(User).filter_by(username=username).first()
        return user and user.admin

    def group_permissions(self, package):
        query = self.db.query(GroupPermission).filter_by(package=package)
        perms = {}

        for perm in query:
            perms[perm.groupname] = perm.permissions
        return perms

    def user_permissions(self, package):
        query = self.db.query(UserPermission).filter_by(package=package)
        perms = {}
        for perm in query:
            perms[perm.username] = perm.permissions
        return perms

    def user_package_permissions(self, username):
        query = self.db.query(UserPermission).filter_by(username=username)
        packages = []
        for perm in query:
            packages.append({"package": perm.package, "permissions": perm.permissions})
        return packages

    def group_package_permissions(self, group):
        query = self.db.query(GroupPermission).filter_by(groupname=group)
        packages = []
        for perm in query:
            packages.append({"package": perm.package, "permissions": perm.permissions})
        return packages

    def user_data(self, username=None):
        if username is None:
            query = self.db.query(User).filter_by(pending=False)
            users = []
            for user in query:
                users.append({"username": user.username, "admin": user.admin})
            return users
        else:
            user = (
                self.db.query(User).filter_by(username=username, pending=False).first()
            )
            if user is not None:
                return {
                    "username": user.username,
                    "admin": user.admin,
                    "groups": [g.name for g in user.groups],
                }

    def need_admin(self):
        return self.db.query(User).filter_by(admin=True).first() is None

    def _register(self, username, password):
        user = User(username, password)
        self.db.add(user)

    def pending_users(self):
        query = self.db.query(User).filter_by(pending=True)
        return [u.username for u in query]

    def approve_user(self, username):
        user = self.db.query(User).filter_by(username=username).first()
        if user is not None:
            user.pending = False

    def _set_password_hash(self, username, password_hash):
        user = self.db.query(User).filter_by(username=username).first()
        if user is not None:
            user.password = password_hash

    def delete_user(self, username):
        self.db.query(User).filter_by(username=username).delete()
        clause = association_table.c.username == username
        self.db.execute(association_table.delete(clause))

    def set_user_admin(self, username, admin):
        user = self.db.query(User).filter_by(username=username).first()
        if user is not None:
            user.admin = admin

    def edit_user_group(self, username, groupname, add):
        user = self.db.query(User).filter_by(username=username).first()
        group = self.db.query(Group).filter_by(name=groupname).first()
        if user is not None and group is not None:
            if add:
                user.groups.add(group)
            else:
                user.groups.remove(group)

    def create_group(self, group):
        self.db.add(Group(group))

    def delete_group(self, group):
        self.db.query(Group).filter_by(name=group).delete()
        clause = association_table.c.group == group
        self.db.execute(association_table.delete(clause))

    def edit_user_permission(self, package, username, perm, add):
        record = (
            self.db.query(UserPermission)
            .filter_by(package=package, username=username)
            .first()
        )
        if record is None:
            if not add:
                return
            record = UserPermission(package, username)
            self.db.add(record)
        if perm == "read":
            record.read = add
        elif perm == "write":
            record.write = add
        else:
            raise ValueError("Unrecognized permission '%s'" % perm)
        if not record.read and not record.write:
            self.db.delete(record)

    def edit_group_permission(self, package, group, perm, add):
        record = (
            self.db.query(GroupPermission)
            .filter_by(package=package, groupname=group)
            .first()
        )
        if record is None:
            if not add:
                return
            record = GroupPermission(package, group)
            self.db.add(record)
        if perm == "read":
            record.read = add
        elif perm == "write":
            record.write = add
        else:
            raise ValueError("Unrecognized permission '%s'" % perm)
        if not record.read and not record.write:
            self.db.delete(record)

    def check_health(self):
        try:
            self.db.query(KeyVal).first()
        except SQLAlchemyError as e:
            return (False, str(e))
        else:
            return (True, "")
