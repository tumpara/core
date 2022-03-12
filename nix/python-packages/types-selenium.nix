{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-selenium";
  version = "3.141.9";

  src = fetchPypi {
    inherit pname version;
#    sha256 = "sha256-uWvZEfh9FSWMOOEO4/CSHDKIel0i5Bw50VcHtNDk0PE=";
  };

  pythonImportsCheck = [ "selenium-stubs" ];
}
