{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
	pname = "types-pillow";
	version = "9.5.0.2";

	src = fetchPypi {
		inherit version;
		pname = "types-Pillow";
		sha256 = "s/n2IfJZVmwZwd7KIZAQF8ix4+IA7S5J4KLYPApRdds=";
	};

	pythonImportsCheck = [ "PIL-stubs" ];
}
