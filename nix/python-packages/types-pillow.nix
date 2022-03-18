{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-pillow";
  version = "9.0.7";

  src = fetchPypi {
    inherit version;
    pname = "types-Pillow";
    sha256 = "nwfrNJVWlNS0yK9b2E2r5xziIl6wXoBzFibabaUMkxE=";
  };

  pythonImportsCheck = [ "PIL-stubs" ];
}
