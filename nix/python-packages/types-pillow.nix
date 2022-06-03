{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
	pname = "types-pillow";
	version = "9.0.19";

	# https://pypi.org/project/types-Pillow/
	src = fetchPypi {
		inherit version;
		pname = "types-Pillow";
		sha256 = "utDeAf0rbP3PyrWA/EAl2ytQaOYjdwfY8vRJPNTE/hY=";
	};

	pythonImportsCheck = [ "PIL-stubs" ];
}
