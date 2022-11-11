{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
	pname = "types-six";
	version = "1.16.21.2";

	src = fetchPypi {
		inherit pname version;
		sha256 = "zVz1Zr14g7wQhj8phIelsgQUKzNinJevl5lnDMlabY4=";
	};

	pythonImportsCheck = [ "six-stubs" ];
}
