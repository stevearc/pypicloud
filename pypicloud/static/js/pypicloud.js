String.prototype.endsWith = function(suffix) {
    return this.indexOf(suffix, this.length - suffix.length) !== -1;
};

var pypicloud = angular.module('pypicloud', ['ui.bootstrap', 'ngRoute', 'angularFileUpload', 'ngCookies'])
  .config(['$routeProvider', function($routeProvider) {
    $routeProvider.when('/', {
      templateUrl: STATIC + 'partial/index.html',
      controller: 'IndexCtrl'
    });

    $routeProvider.when('/package/:pkg', {
      templateUrl: STATIC + 'partial/package.html',
      controller: 'PackageCtrl'
    });

    $routeProvider.when('/new_admin', {
      templateUrl: STATIC + 'partial/new_admin.html',
      controller: 'NewAdminCtrl'
    });

    $routeProvider.when('/account', {
      templateUrl: STATIC + 'partial/account.html',
      controller: 'AccountCtrl'
    });

    $routeProvider.otherwise({
      redirectTo: '/',
    });
  }])
  .run(['$rootScope','$location', '$routeParams', function($rootScope, $location, $routeParams) {
    $rootScope.$on('$routeChangeSuccess', function(scope, current, pre) {
      $rootScope.location = {
        path: $location.path()
      };
    });
  }])
  .filter('startFrom', function() {
    return function(input, start) {
        start = parseInt(start, 10);
        return input.slice(start);
    }
  })
  .config(['$compileProvider', function($compileProvider) {
    $compileProvider.directive('compileUnsafe', ['$compile', function($compile) {
    return function(scope, element, attrs) {
      scope.$watch(
        function(scope) {
          // watch the 'compile' expression for changes
          return scope.$eval(attrs.compileUnsafe);
        },
        function(value) {
          // when the 'compile' expression changes
          // assign it into the current DOM element
          element.html(value);

          // compile the new DOM and link it to the current
          // scope.
          // NOTE: we only compile .childNodes so that
          // we don't get into infinite loop compiling ourselves
          $compile(element.contents())(scope);
        }
      );
    };
  }]);
}]);

pypicloud.controller('BaseCtrl', ['$rootScope', '$location', function($rootScope, $location) {
  $rootScope._ = _;
  $rootScope.USER = USER;
  $rootScope.ROOT = ROOT;
  $rootScope.API = ROOT + 'api/';
  $rootScope.ADMIN = ROOT + 'admin/';
  $rootScope.IS_ADMIN = IS_ADMIN;
  $rootScope.NEED_ADMIN = NEED_ADMIN;
  $rootScope.ACCESS_MUTABLE = ACCESS_MUTABLE;
  $rootScope.ALLOW_REGISTER = ALLOW_REGISTER;
  $rootScope.STATIC = STATIC;
  $rootScope.PARTIAL = STATIC + 'partial/';
  $rootScope.VERSION = VERSION;
  if (NEED_ADMIN) {
    $location.path('/new_admin');
  }

  $rootScope.getDevice = function() {
    var envs = ['xs', 'sm', 'md', 'lg'];

    var el = document.createElement('div');
    var body = document.getElementsByTagName('body')[0];
    body.appendChild(el);

    for (var i = envs.length - 1; i >= 0; i--) {
      var env = envs[i];

      el.setAttribute('class', 'hidden-' + env);
      if (el.offsetWidth === 0 && el.offsetHeight === 0) {
        el.remove();
        return env
      }
    };
  }

  $rootScope.device = $rootScope.getDevice();
  $rootScope.getWidth = function() {
    return window.innerWidth;
  };
  $rootScope.$watch($rootScope.getWidth, function(newValue, oldValue) {
    if (newValue != oldValue) {
      $rootScope.device = $rootScope.getDevice();
    }
  });
  window.onresize = function(){
    $rootScope.$apply();
  }
}]);

pypicloud.controller('NavbarCtrl', ['$scope', function($scope) {
  $scope.navCollapsed = $scope.device === 'xs';
  $scope.options = [];
}]);

pypicloud.controller('IndexCtrl', ['$scope', '$http', '$location', '$cookies',
    function($scope, $http, $location, $cookies) {
  $scope.$cookies = $cookies;
  $scope.packages = null;
  $scope.pageSize = 10;
  $scope.maxSize = 8;
  $scope.currentPage = 1;
  if (NEED_ADMIN) {
    $location.path('/new_admin');
  }

  $http.get($scope.API + 'package/', {params: {verbose: true}})
      .success(function(data, status, headers, config) {
    $scope.packages = data.packages;
  });

  $scope.showPackage = function(pkg) {
    $location.path('/package/' + pkg);
  }

  $scope.uploadFinished = function(response) {
    if ($scope.packages.indexOf(response.name) < 0) {
      $scope.packages.push(response.name);
    }
    $scope.uploadCollapsed = true;
  };

  $scope.closePipHelp = function() {
    $cookies.seenPipHelp = 'true';
  };
}]);

pypicloud.controller('LoginCtrl', ['$scope', '$http', function($scope, $http) {
  $scope.error = false;
  $scope.submit = function(username, password) {
    var data = {
      username: username,
      password: password
    };
    $http.post(ROOT + 'login', data).success(function(data, status, headers, config) {
      $scope.error = false;
      window.location = data.next;
    }).error(function(data, status, headers, config) {
      $scope.error = true;
      $scope.errorMsg = 'Username or password invalid';
    });
  };

  $scope.register = function(username, password) {
    var data = {
      username: username,
      password: password
    };
    $http.put(ROOT + 'login', data).success(function(data, status, headers, config) {
      $scope.error = false;
      $scope.registered = username;
    }).error(function(data, status, headers, config) {
      $scope.error = true;
      $scope.errorMsg = 'User already exists';
    });
  };
}]);

pypicloud.controller('PackageCtrl', ['$scope', '$http', '$route', '$fileUploader',
    function($scope, $http, $route, $fileUploader) {
  $scope.package_name = $route.current.params.pkg;
  $scope.showPreRelease = true;
  $scope.packages = null;
  $scope.pageSize = 10;
  $scope.maxSize = 8;
  $scope.currentPage = 1;

  $scope.filterPreRelease = function(pkg) {
    if ($scope.showPreRelease) {
      return true;
    }
    return pkg.version.match(/^\d+(\.\d+)*$/);
  };

  $http.get($scope.API + 'package/' + $scope.package_name).success(function(data, status, headers, config) {
    $scope.packages = data.packages;
    $scope.filtered = data.packages;
    $scope.can_write = data.write;
  })

  $scope.deletePackage = function(pkg) {
    var index = $scope.packages.indexOf(pkg);
    pkg.deleting = true;
    var data = {
      name: $scope.package_name,
    }
    var url = $scope.API + 'package/' + $scope.package_name + '/' + pkg.version;
    $http({method: 'delete', url: url}).success(function(data, status, headers, config) {
      $scope.packages.splice(index, 1);
    }).error(function(data, status, headers, config) {
      pkg.deleting = false;
    });
  };

  $scope.uploadFinished = function(response) {
    $scope.packages.push(response);
    $scope.uploadCollapsed = true;
  };
}]);

pypicloud.controller('UploadCtrl', ['$scope', '$fileUploader', function($scope, $fileUploader) {
  if ($scope.package_name) {
    $scope.package_preset = true;
  }
  var uploader = $scope.uploader = $fileUploader.create({
      scope: $scope,
      alias: 'content',
  });

  $scope.canUpload = function() {
    return (uploader.queue.length === 1 &&
      $scope.version && $scope.version.length > 0 &&
      $scope.package_name && $scope.package_name.length > 0 &&
      !$scope.uploading);
  }

  $scope.uploadPackage = function() {
    $scope.uploading = true;
    var item = uploader.queue[0];
    item.url = $scope.API + 'package/' + $scope.package_name + '/' + $scope.version;
    item.upload();
  }

  uploader.bind('changedqueue', function (event, items) {
    if (uploader.queue.length === 0) {
      $scope.version = '';
      if (!$scope.package_preset) {
        $scope.package_name = '';
      }
    } else {
      var pieces = items[0].file.name.split('-');
      if (!$scope.package_preset) {
        $scope.package_name = pieces[0];
      }
      pieces.splice(0, 1);
      $scope.version = pieces.join('-');
      $scope.version = $scope.version.substr(0, $scope.version.lastIndexOf('.'));
      if ($scope.version.endsWith('.tar')) {
        $scope.version = $scope.version.slice(0, -4);
      }
      $scope.$apply();
    }
  });

  uploader.bind('success', function (event, xhr, item, response) {
    uploader.clearQueue();
    $scope.version = '';
    $scope.uploading = false;
    if (!$scope.package_preset) {
      $scope.package_name = '';
    }
    if ($scope.uploadFinished !== undefined) {
      $scope.uploadFinished(response);
    }
  });

  uploader.bind('error', function (event, xhr, item, response) {
    $scope.uploading = false;
    alert("Error during upload! " + response);
  });
}]);

pypicloud.controller('TableCtrl', ['$scope', '$sce', '$interpolate', function($scope, $sce, $interpolate) {
  $scope.currentPage = 1;
  $scope.searchable = false;
  $scope.searchStrict = false;
  $scope.pageSize = 10;
  $scope.maxSize = 8;
  $scope.items = [];
  $scope.columns = [];
  $scope.title = '';
  $scope.ordering = 'toString()';
  $scope.rowClick = null;

  // For making the table mutable
  $scope.disableEdits = false;
  $scope.addItems = null;
  $scope.addCallback = null;
  $scope.deleteText = 'Delete';
  $scope.deleteCallback = null;
  $scope.deleteButtonElement = null;

  // Set arguments from parent scope
  if (_.isObject($scope.tableArgs)) {
    _.each($scope.tableArgs, function(value, key) {
      $scope[key] = value;
    });
  }

  if ($scope.rowClick === null) {
    $scope.rowClick = function(){};
    $scope.clickable = false;
  } else {
    $scope.clickable = true;
  }

  // TODO: put a scope.watch() on tableArgs

  $scope.compile = function(html, item) {
    return $sce.trustAsHtml($interpolate(html)({item: item}));
  };

  $scope.toggleShowAdd = function() {
    $scope.showAdd = !$scope.showAdd;
    if (!$scope.showAdd) {
      $scope.newItem = '';
      $scope.errorMsg = undefined;
      $scope.showAdd = false;
    }
  };

  $scope.addItem = function() {
    $scope.errorMsg = $scope.addCallback($scope.newItem);
    if ($scope.errorMsg === undefined) {
      $scope.newItem = '';
    }
  };
}]);

pypicloud.controller('NewAdminCtrl', ['$scope', '$http', '$location', function($scope, $http, $location) {
  $scope.register = function(username, password) {
    $http.put($scope.API + 'user/' + username, {password:password}).success(function(data, status, headers, config) {
      window.location = ROOT;
    });
  };
}]);

pypicloud.controller('AccountCtrl', ['$scope', '$http', function($scope, $http) {

  $scope.changePassword = function(oldPassword, newPassword) {
    if (!oldPassword || !newPassword || oldPassword.length === 0 || newPassword.length === 0) {
      $scope.passError = 'Password cannot be blank!';
      return;
    }
    var data = {
      new_password: newPassword,
      old_password: oldPassword
    };
    $scope.changingPasswordNetwork = true;
    $http.post($scope.API + 'user/password', data).success(function(data, status, headers, config) {
      $scope.changingPasswordNetwork = false;
      $scope.changingPassword = false;
      $scope.newPassword = '';
      $scope.oldPassword = '';
      $scope.passError = null;
    }).error(function(data, status, headers, config) {
      $scope.changingPasswordNetwork = false;
      $scope.passError = 'Invalid password!';
    });
  };
}]);
