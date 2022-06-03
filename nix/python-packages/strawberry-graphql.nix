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
	version = "0.114.0";

	# https://pypi.org/project/strawberry-graphql/
	src = fetchPypi {
		inherit pname version;
		sha256 = "k89hf7gw+X71+tZ2Vd5eb5B5w3JxxpbvvbH8KZo/8PA=";
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
