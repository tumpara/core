{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
	pname = "types-pillow";
	version = "9.4.0.5";

	src = fetchPypi {
		inherit version;
		pname = "types-Pillow";
		sha256 = "lBzvqsL1KX19KpmJYzyVtAYxEmkNwhyWXUa9Wn//PHY=";
	};

	pythonImportsCheck = [ "PIL-stubs" ];
}
