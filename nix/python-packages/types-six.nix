{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-six";
  version = "1.16.15";

	# https://pypi.org/project/types-six/
  src = fetchPypi {
    inherit pname version;
    sha256 = "0kTwU32rDQVwpbxvimDE2n8FRtlgqGd1IOa/8hSmT7g=";
  };

  pythonImportsCheck = [ "six-stubs" ];
}
