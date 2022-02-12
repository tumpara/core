{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-pillow";
  version = "8.3.11";

  src = fetchPypi {
    inherit version;
    pname = "types-Pillow";
    sha256 = "qpanORhPSPaebzAhhABiP8WpX1/sGZxEdmOjJThEBAU=";
  };

  pythonImportsCheck = [ "PIL-stubs" ];
}
