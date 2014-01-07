String.prototype.endsWith = function(suffix) {
    return this.indexOf(suffix, this.length - suffix.length) !== -1;
};

var pypicloud = angular.module('pypicloud', ['ui.bootstrap', 'ngRoute', 'angularFileUpload', 'ngCookies'])
  .config(['$routeProvider', function($routeProvider) {
    $routeProvider.when('/', {
      templateUrl: STATIC + 'partial/index.html',
      controller: 'IndexCtrl'
    });

    $routeProvider.when('/admin', {
      templateUrl: STATIC + 'partial/admin.html',
      controller: 'AdminCtrl'
    });

    $routeProvider.when('/package/:pkg', {
      templateUrl: STATIC + 'partial/package.html',
      controller: 'PackageCtrl'
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
});

pypicloud.controller('BaseCtrl', ['$rootScope', function($rootScope) {
  $rootScope.USER = USER;
  $rootScope.ROOT = ROOT;
  $rootScope.API = ROOT + 'api/';
  $rootScope.ADMIN = ADMIN;
  $rootScope.STATIC = STATIC;
  $rootScope.PARTIAL = STATIC + 'partial/';
}]);

pypicloud.controller('NavbarCtrl', ['$scope', function($scope) {
  $scope.options = [];
  if ($scope.ADMIN) {
    $scope.options.push({
      title: 'Admin',
      path: '/admin',
    });
  }
}]);

pypicloud.controller('IndexCtrl', ['$scope', '$http', '$location', '$cookies',
    function($scope, $http, $location, $cookies) {
  $scope.$cookies = $cookies;
  $scope.VERSION = VERSION;
  $scope.packages = null;
  $scope.pageSize = 10;
  $scope.maxSize = 8;
  $scope.currentPage = 1;

  $http.get($scope.API + 'package/').success(function(data, status, headers, config) {
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
  $scope.submit = function() {
    var data = {
      username: $scope.username,
      password: $scope.password
    };
    $http.post(ROOT + 'login', data).success(function(data, status, headers, config) {
      $scope.error = false;
      window.location = data.next;
    }).error(function(data, status, headers, config) {
      $scope.error = true;
    });
  }
}]);

pypicloud.controller('PackageCtrl', ['$scope', '$http', '$route', '$fileUploader',
    function($scope, $http, $route, $fileUploader) {
  $scope.package_name = $route.current.params.pkg;
  $scope.packages = null;
  $scope.pageSize = 10;
  $scope.maxSize = 8;
  $scope.currentPage = 1;

  $http.get($scope.API + 'package/' + $scope.package_name).success(function(data, status, headers, config) {
    $scope.packages = data.packages;
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

pypicloud.controller('AdminCtrl', ['$scope', '$http', function($scope, $http) {
  $scope.rebuildPackages = function() {
    $scope.building = true;
    $http.get($scope.API + 'rebuild').success(function(data, status, headers, config) {
      $scope.building = false;
    }).error(function(data, status, headers, config) {
      $scope.building = false;
    });
  }
}]);
