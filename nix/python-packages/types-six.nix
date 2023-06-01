{
  buildPythonPackage,
  fetchPypi,
}:
buildPythonPackage rec {
  pname = "types-six";
  version = "1.16.21.8";

  src = fetchPypi {
    inherit pname version;
    sha256 = "AqiS/49CPExdFd58b01DPmQ8hjvL76vRklG0eMuyhKs=";
  };

  pythonImportsCheck = ["six-stubs"];
}
