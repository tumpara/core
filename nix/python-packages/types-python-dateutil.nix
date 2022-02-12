{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-python-dateutil";
  version = "2.8.9";

  src = fetchPypi {
    inherit pname version;
    sha256 = "kPlaa21Pq6NZKH8XosrlEczJ1KvImwGWm9rBGFgVwF0=";
  };

  pythonImportsCheck = [ "dateutil-stubs" ];
}
