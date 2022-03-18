{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-freezegun";
  version = "1.1.7";

  src = fetchPypi {
    inherit pname version;
    sha256 = "6dEyfpjGyqj2XeABje0nQ0fo40GY1ZqppcJK2SZdXl4=";
  };

  pythonImportsCheck = [ "freezegun-stubs" ];
}
