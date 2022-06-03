{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
	pname = "types-PyYAML";
	version = "6.0.8";

	# https://pypi.org/project/types-PyYAML/
	src = fetchPypi {
		inherit pname version;
		sha256 = "2UldN3u0+cU4esJ4d2QD6ztLs3aFECXZE+6kwitMZDg=";
	};

	pythonImportsCheck = [ "yaml-stubs" ];
}
