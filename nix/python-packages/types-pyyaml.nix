{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
	pname = "types-PyYAML";
	version = "6.0.7";

	# https://pypi.org/project/types-PyYAML/
	src = fetchPypi {
		inherit pname version;
		sha256 = "WUgM9EWV2DaqrgUPNePDnxl/OoM2ee85eNl6qfL7fe8=";
	};

	pythonImportsCheck = [ "yaml-stubs" ];
}
