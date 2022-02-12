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
  version = "0.95.1";

  src = fetchPypi {
    inherit pname version;
    sha256 = "EOICFcVj1BmZ4w0LAvUgmBoVBbIGPHqN4Vf0aA7fOtQ=";
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
