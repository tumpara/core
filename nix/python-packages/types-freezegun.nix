{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-freezegun";
  version = "1.1.6";

  src = fetchPypi {
    inherit pname version;
    sha256 = "XHCkt0RLjH3SgA4AY9b+chqxEgk5kmT6D3evJT3YsU8=";
  };

  pythonImportsCheck = [ "freezegun-stubs" ];
}
