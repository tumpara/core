{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
	pname = "types-pillow";
	version = "9.3.0.1";

	src = fetchPypi {
		inherit version;
		pname = "types-Pillow";
		sha256 = "87fK2j+klseNdSU8ax8HqEPWJfQuVjmzIKcqyv9vfPs=";
	};

	pythonImportsCheck = [ "PIL-stubs" ];
}
