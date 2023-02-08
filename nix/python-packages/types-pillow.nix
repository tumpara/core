{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
	pname = "types-pillow";
	version = "9.4.0.8";

	src = fetchPypi {
		inherit version;
		pname = "types-Pillow";
		sha256 = "NT2hzHPiDRh4MsWFuf2Koq1XhbfyWJXkrp3exL6xPYE=";
	};

	pythonImportsCheck = [ "PIL-stubs" ];
}
