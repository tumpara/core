{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-six";
  version = "1.16.10";

  src = fetchPypi {
    inherit pname version;
    sha256 = "eObA/kDClY4qlaseGt+/PatWiU3Iz1kNrhj9afMXnv8=";
  };

  pythonImportsCheck = [ "six-stubs" ];
}
