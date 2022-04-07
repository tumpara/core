{ buildPythonPackage
, fetchPypi
, backports_cached-property
, django
, asgiref
, click
, graphql-core
, pygments
, python-dateutil
, python-multipart
, sentinel
, typing-extensions
}:

buildPythonPackage rec {
  pname = "strawberry-graphql";
  version = "0.105.0";

  src = fetchPypi {
    inherit pname version;
    sha256 = "F/lkBxxzqKmOGXupVTe0w/xeeGQvUagyfpBu8h1Jzk8=";
  };

  propagatedBuildInputs = [
    backports_cached-property
    django
    asgiref
    click
    graphql-core
    pygments
    python-dateutil
    python-multipart
    sentinel
    typing-extensions
  ];

  doCheck = false;
  pythonImportsCheck = [ "strawberry" ];
}
