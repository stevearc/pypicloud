function permissionConfig($scope, $http, $location, permissions, allItems, pageType, pageId, itemType) {
  if (itemType === 'package') {
    var itemName = 'package';
    var title = '<i class="fa fa-gift" title="Packages"></i> Packages';
  } else if (itemType === 'user') {
    var itemName = 'username';
    var title = '<i class="fa fa-user" title="Users"></i> Users';
  } else if (itemType === 'group') {
    var itemName = 'group';
    var title = '<i class="fa fa-users" title="Groups"></i> Groups';
  }
  var editUrl = function(name, permission) {
    if (pageType === 'package') {
      return $scope.ADMIN + 'package/' + pageId + '/' + itemType + '/' + name + '/' + permission;
    } else {
      return $scope.ADMIN + 'package/' + name + '/' + pageType + '/' + pageId + '/' + permission;
    }
  };
  var deleteButtonElement = [
    '<div ng-show="showDelete">',
    '<button class="btn btn-danger btn-sm"',
    'ng-click="removePermission(item); $event.stopPropagation()">-</button> ',
    '<button class="btn btn-success btn-sm" ',
    'ng-style="_.contains(item.permissions, \'write\') ? {visibility: \'hidden\'} : {}" ',
    'ng-click="addPermission(item); $event.stopPropagation()">+</button>',
    '</div>'
  ].join('\n');
  var removePermission = function(item) {
    if (item.permissions.length === 1) {
      var idx = permissions.indexOf(item);
      permissions.splice(idx, 1);
      allItems.push(item[itemName]);
      $http({method: 'delete', url: editUrl(item[itemName], 'read')});
    } else {
      item.permissions.splice(1, 1);
      $http({method: 'delete', url: editUrl(item[itemName], 'write')});
    }
  };

  var addCallback = function(name) {
    var idx = allItems.indexOf(name);
    allItems.splice(idx, 1);
    var newItem = {
      permissions: ['read'],
    };
    newItem[itemName] = name;
    permissions.push(newItem);
    $http.put(editUrl(name, 'read'));
  };

  var addPermission = function(item) {
    item.permissions.push('write');
    $http.put(editUrl(item[itemName], 'write'));
  };

  var columns = [
    "{{ item." + itemName + " }}",
    "{{ item.permissions.join(' / ') }}"
  ];

  return {
    title: title,
    columns: columns,
    ordering: itemName,
    addItems: allItems,
    items: permissions,
    disableEdits: !ACCESS_MUTABLE,
    rowClick: function(item) {
      $location.path('/admin/' + itemType + '/' + item[itemName]);
    },
    addCallback: addCallback,
    deleteCallback: true,
    addPermission: addPermission,
    removePermission: removePermission,
    deleteButtonElement: deleteButtonElement
  }
};

angular.module('pypicloud')
.config(['$routeProvider', function($routeProvider) {
  $routeProvider.when('/admin', {
    templateUrl: STATIC + 'partial/admin/index.html',
    controller: 'AdminCtrl'
  });

  $routeProvider.when('/admin/user/:username', {
    templateUrl: STATIC + 'partial/admin/user.html',
    controller: 'AdminUserCtrl'
  });

  $routeProvider.when('/admin/group/:name', {
    templateUrl: STATIC + 'partial/admin/group.html',
    controller: 'AdminGroupCtrl'
  });

  $routeProvider.when('/admin/package/:name', {
    templateUrl: STATIC + 'partial/admin/package.html',
    controller: 'AdminPackageCtrl'
  });
}])

.controller('AdminCtrl', ['$rootScope', '$scope', '$http', '$location',
    function($rootScope, $scope, $http, $location) {
  $scope.users = null;
  $scope.pendingUsers = null;
  $scope.groups = null;
  $scope.packages = null;
  $scope.pageSize = 10;

  $scope.toggleAllowRegister = function() {
    ALLOW_REGISTER = !ALLOW_REGISTER;
    $rootScope.ALLOW_REGISTER = ALLOW_REGISTER;
    $http.post($scope.ADMIN + 'register', {allow: ALLOW_REGISTER});
  };

  function deleteUser(user) {
    $http({method: 'delete', url: $scope.ADMIN + 'user/' + user.username});
    var idx = $scope.users.indexOf(user);
    $scope.users.splice(idx, 1);
  }

  $http.get($scope.ADMIN + 'user').success(function(data, status, headers, config) {
    $scope.users = data;
    // Add 'admin' text so it's searchable
    for (var i=0; i < $scope.users.length; i++) {
      if ($scope.users[i].admin) {
        $scope.users[i].tags = ['admin'];
      }
    }
    $scope.userTableArgs = {
      title: '<i class="fa fa-user" title="Users"></i> Users',
      items: $scope.users,
      searchable: true,
      columns: [
        "{{ item.admin ? '<i class=\"fa fa-lock\" title=\"Admin\"></i>' : '' }} {{ item.username }}",
      ],
      rowClick: function(user) {
        $location.path('/admin/user/' + user.username);
      },
      disableEdits: !ACCESS_MUTABLE,
      ordering: 'username',
      deleteCallback: deleteUser
    };
  });

  function deleteGroup(group) {
    $http({method: 'delete', url: $scope.ADMIN + 'group/' + group});
    var idx = $scope.groups.indexOf(group);
    $scope.groups.splice(idx, 1);
  }
  function addGroup(group) {
    if (group === 'everyone' || group === 'authenticated') {
      return 'That group is reserved!';
    }
    if ($scope.groups.indexOf(group) >= 0) {
      return 'That group already exists!';
    }
    $scope.groups.push(group);
    $http.put($scope.ADMIN + 'group/' + group);
  }
  $http.get($scope.ADMIN + 'group').success(function(data, status, headers, config) {
    data.push('everyone'); data.push('authenticated');
    $scope.groups = data;
    $scope.groupTableArgs = {
      title: '<i class="fa fa-users" title="Groups"></i> Groups',
      items: $scope.groups,
      searchable: true,
      disableEdits: !ACCESS_MUTABLE,
      deleteButtonElement: [
        '<button ng-click="deleteCallback(item); $event.stopPropagation();" ',
        'ng-show="showDelete && !_.contains([\'everyone\', \'authenticated\'], item)"',
        'class="btn btn-danger btn-xs">',
        '{{ deleteText }}',
        '</button>'
      ].join('\n'),
      columns: [
        "{{ item }}"
      ],
      rowClick: function(group) {
        $location.path('/admin/group/' + group);
      },
      deleteCallback: deleteGroup,
      addCallback: addGroup
    };
  });

  var fetchPackages = function() {
    $scope.packages = null;
    $scope.packageTableArgs = null;
    $http.get($scope.API + 'package/').success(function(data, status, headers, config) {
      $scope.packages = data.packages;
      $scope.packageTableArgs = {
        title: '<i class="fa fa-gift" title="Packages"></i> Packages',
        items: $scope.packages,
        searchable: true,
        columns: [
          "{{ item }}"
        ],
        disableEdits: !ACCESS_MUTABLE,
        rowClick: function(pkg) {
          $location.path('/admin/package/' + pkg);
        }
      };
    });
  };
  fetchPackages();

  $scope.approveUser = function(username) {
    $http.post($scope.ADMIN + 'user/' + username + '/approve');
    var idx = $scope.pendingUsers.indexOf(username);
    $scope.pendingUsers.splice(idx, 1);
    var newUser = {
      'username': username,
      'admin': false
    };
    $scope.users.push(newUser);
  }

  $scope.rejectUser = function(username) {
    $http({method: 'delete', url: $scope.ADMIN + 'user/' + username});
    var idx = $scope.pendingUsers.indexOf(username);
    $scope.pendingUsers.splice(idx, 1);
  }

  if (ACCESS_MUTABLE) {
    $http.get($scope.ADMIN + 'pending_users').success(function(data, status, headers, config) {
      $scope.pendingUsers = data;
    });
  }

  $scope.rebuildPackages = function() {
    $scope.building = true;
    $http.get($scope.ADMIN + 'rebuild').success(function(data, status, headers, config) {
      $scope.building = false;
      fetchPackages();
    }).error(function(data, status, headers, config) {
      $scope.building = false;
    });
  }
}])

.controller('AdminUserCtrl', ['$scope', '$http', '$routeParams', '$location',
    function($scope, $http, $routeParams, $location) {
  $scope.username = $routeParams.username;
  $scope.user = null;
  $scope.permissions = null;

  $scope.toggleAdmin = function() {
    $scope.user.admin = !$scope.user.admin;
    $http.post($scope.ADMIN + 'user/' + $scope.username + '/admin', {admin: $scope.user.admin});
  };

  $http.get($scope.ADMIN + 'user/' + $scope.username).success(function(data, status, headers, config) {
    $scope.user = data;
    $scope.user.groups.push('everyone'); $scope.user.groups.push('authenticated');


    $http.get($scope.ADMIN + 'group').success(function(data, status, headers, config) {
      $scope.groups = _.difference(data, $scope.user.groups);
      var editUrl = function(group) {
        return $scope.ADMIN + 'user/' + $scope.username + '/group/' + group;
      };
      $scope.groupTableArgs = {
        title: '<i class="fa fa-users" title="Groups"></i> Groups',
        items: $scope.user.groups,
        columns: [
          "{{ item }}"
        ],
        rowClick: function(group) {
          $location.path('/admin/group/' + group);
        },
        addItems: $scope.groups,
        disableEdits: !ACCESS_MUTABLE,
        deleteButtonElement: [
          '<button ng-click="deleteCallback(item); $event.stopPropagation();" ',
          'ng-show="showDelete && !_.contains([\'everyone\', \'authenticated\'], item)"',
          'class="btn btn-danger btn-xs">',
          '{{ deleteText }}',
          '</button>'
        ].join('\n'),
        addCallback: function(group) {
          var idx = $scope.groups.indexOf(group);
          $scope.groups.splice(idx, 1);
          $scope.user.groups.push(group);
          $http.put(editUrl(group));
        },
        deleteCallback: function(group) {
          var idx = $scope.user.groups.indexOf(group);
          $scope.user.groups.splice(idx, 1);
          $scope.groups.push(group);
          $http({method: 'delete', url: editUrl(group)});
        }
      };
    });
  });


  $http.get($scope.ADMIN + 'user/' + $scope.username + '/permissions').success(function(data, status, headers, config) {
    $scope.permissions = data;
    $http.get($scope.API + 'package').success(function(data, status, headers, config) {
      $scope.packages = _.difference(data.packages, _.pluck($scope.permissions, 'package'));

      $scope.packageTableArgs = permissionConfig($scope, $http, $location, $scope.permissions,
                                $scope.packages, 'user', $scope.username,
                                'package');
    });
  });
}])

.controller('AdminGroupCtrl', ['$scope', '$http', '$routeParams', '$location',
    function($scope, $http, $routeParams, $location) {
  $scope.name = $routeParams.name;
  $scope.members = null;
  $scope.packages = null;
  if ($scope.name === 'everyone') {
    $scope.special = true;
  } else if ($scope.name === 'authenticated') {
    $scope.special = true;
  }

  var url = $scope.ADMIN + 'group/' + $routeParams.name;
  $http.get(url).success(function(data, status, headers, config) {
    $scope.members = data.members;
    $scope.permissions = data.packages;

    $http.get($scope.ADMIN + 'user').success(function(data, status, headers, config) {
      $scope.users = _.difference(_.pluck(data, 'username'), $scope.members);
      var editUrl = function(username) {
        return $scope.ADMIN + 'user/' + username + '/group/' + $scope.name;
      };
      $scope.userTableArgs = {
        title: '<i class="fa fa-user" title="Members"></i> Members',
        items: $scope.members,
        columns: [
          "{{ item }}"
        ],
        rowClick:  function(user) {
          $location.path('/admin/user/' + user);
        },
        addItems: $scope.users,
        disableEdits: !ACCESS_MUTABLE,
        addCallback: function(user) {
          var idx = $scope.users.indexOf(user);
          $scope.users.splice(idx, 1);
          $scope.members.push(user);
          $http.put(editUrl(user));
        },
        deleteCallback: function(user) {
          var idx = $scope.members.indexOf(user);
          $scope.members.splice(idx, 1);
          $scope.users.push(user);
          $http({method: 'delete', url: editUrl(user)})
        }
      };
    });

    $http.get($scope.API + 'package').success(function(data, status, headers, config) {
      $scope.packages = _.difference(data.packages, _.pluck($scope.permissions, 'package'));
      $scope.packageTableArgs = permissionConfig($scope, $http, $location, $scope.permissions,
                                $scope.packages, 'group', $scope.name, 'package');
    });
  });
}])

.controller('AdminPackageCtrl', ['$scope', '$http', '$routeParams', '$location',
    function($scope, $http, $routeParams, $location) {
  $scope.name = $routeParams.name;
  $scope.userPermissions = null;
  $scope.groupPermissions = null;

  var url = $scope.ADMIN + 'package/' + $routeParams.name;
  $http.get(url).success(function(data, status, headers, config) {
    $scope.userPermissions = data.user;
    $scope.groupPermissions = data.group;

    $http.get($scope.ADMIN + 'user').success(function(data, status, headers, config) {
      $scope.users = _.difference(_.pluck(data, 'username'),
                                  _.pluck($scope.userPermissions, 'username'));
      $scope.userTableArgs = permissionConfig($scope, $http, $location, $scope.userPermissions,
                                $scope.users, 'package', $scope.name, 'user');
    });

    $http.get($scope.ADMIN + 'group').success(function(data, status, headers, config) {
      data.push('everyone'); data.push('authenticated');
      $scope.groups = _.difference(data, _.pluck($scope.groupPermissions, 'group'));
      $scope.groupTableArgs = permissionConfig($scope, $http, $location, $scope.groupPermissions,
                                $scope.groups, 'package', $scope.name, 'group');
    });
  });
}]);
