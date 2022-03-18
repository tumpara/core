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
  version = "0.103.5";

  src = fetchPypi {
    inherit pname version;
    sha256 = "cpZVYRj8CM5bgTf+l25wGeWxrcnDxXm9pFv0ndx+ctk=";
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
