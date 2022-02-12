{ buildPythonPackage, fetchPypi, setuptools-scm }:

buildPythonPackage rec {
  pname = "backports_cached-property";
  version = "1.0.1";

  src = fetchPypi {
    pname = "backports.cached-property";
    inherit version;
    sha256 = "Gl7x51D4vH0CBMgHqujg9FDGVb4M9LMEB6Nf1LsnGGw=";
  };

  nativeBuildInputs = [ setuptools-scm ];
  
  doCheck = false;
  pythonImportsCheck = [ "backports.cached_property" ];
}
