{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-freezegun";
  version = "1.1.8";

  src = fetchPypi {
    inherit pname version;
    sha256 = "9LsIxUqkaBbHehtceipU9Tk8POWOfUAC5n+QgbQR6SE=";
  };

  pythonImportsCheck = [ "freezegun-stubs" ];
}
