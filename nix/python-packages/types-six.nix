{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
	pname = "types-six";
	version = "1.16.21.4";

	src = fetchPypi {
		inherit pname version;
		sha256 = "2q8bUGE303JX+tenR4V8V9UzFhGRnQ2UuBlaBr28Aq8=";
	};

	pythonImportsCheck = [ "six-stubs" ];
}
