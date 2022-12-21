{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
	pname = "types-pillow";
	version = "9.3.0.4";

	src = fetchPypi {
		inherit version;
		pname = "types-Pillow";
		sha256 = "wY1GbcGFUNlri0onn/lPDLrWloJbWtVUZmBPHa9XCd4=";
	};

	pythonImportsCheck = [ "PIL-stubs" ];
}
