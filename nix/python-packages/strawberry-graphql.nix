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
  version = "0.111.2";

	# https://pypi.org/project/strawberry-graphql/
  src = fetchPypi {
    inherit pname version;
    sha256 = "yrb4cYEkTE+6QkR4JNE7Tega2C/NXvlzix2pN0hfpFw=";
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
