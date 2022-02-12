{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-PyYAML";
  version = "6.0.4";

  src = fetchPypi {
    inherit pname version;
    sha256 = "YlL2LXhecw5FTfoMnw+5nY2uJUxcPGhpA8+HjqJ8BLc=";
  };

  pythonImportsCheck = [ "yaml-stubs" ];
}
