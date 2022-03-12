{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-six";
  version = "1.16.12";

  src = fetchPypi {
    inherit pname version;
    sha256 = "VXQ1+K1z6RVieXrH76yOZVTw+niTtkMbko3o7GNdhmo=";
  };

  pythonImportsCheck = [ "six-stubs" ];
}
