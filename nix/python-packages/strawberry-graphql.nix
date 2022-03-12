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
  version = "0.102.2";

  src = fetchPypi {
    inherit pname version;
    sha256 = "+BNPSBdZ4qal/XbFimtZe+9mcwLthVooNkN++tNqrpM=";
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
