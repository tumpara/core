{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
	pname = "types-pillow";
	version = "9.0.15";

	# https://pypi.org/project/types-Pillow/
	src = fetchPypi {
		inherit version;
		pname = "types-Pillow";
		sha256 = "0uOF/lwZLnWXDxiszOafXCqfGG8/61eKm5HNb99kIR0=";
	};

	pythonImportsCheck = [ "PIL-stubs" ];
}
