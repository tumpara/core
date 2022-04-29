{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-pillow";
  version = "9.0.11";

  src = fetchPypi {
    inherit version;
    pname = "types-Pillow";
    sha256 = "meMGu+H5eIS7b+nduHtnFfylpKNo2tQuk2b0aqWHfqc=";
  };

  pythonImportsCheck = [ "PIL-stubs" ];
}
