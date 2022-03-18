{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-python-dateutil";
  version = "2.8.10";

  src = fetchPypi {
    inherit pname version;
    sha256 = "a886rnJC5Xk7r9eyvPtOJV63srMUSs0N8OGC3OWMytM=";
  };

  pythonImportsCheck = [ "dateutil-stubs" ];
}
