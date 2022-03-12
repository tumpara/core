{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-pillow";
  version = "9.0.6";

  src = fetchPypi {
    inherit version;
    pname = "types-Pillow";
    sha256 = "ebNQsRiMCAwnVYQp8eEZ5pyfAguHeoLfdh2SgwcOAYU=";
  };

  pythonImportsCheck = [ "PIL-stubs" ];
}
