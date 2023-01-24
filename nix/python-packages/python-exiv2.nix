{ lib
, stdenv
, buildPythonPackage
, fetchPypi
, cmake
, exiv2
, expat
, pkg-config
, zlib
}:

buildPythonPackage rec {
  pname = "exiv2";
  version = "0.13.1";

	src = fetchPypi {
		inherit pname version;
		format = "setuptools";
		extension = "zip";
		sha256 = "ox4ZHnSsR7vcUykbC48E6J9CMizs8oIemtkQki+yXG8=";
	};

  nativeBuildInputs = [
    cmake
    pkg-config
  ];

  buildInputs = [
    exiv2
    expat
    zlib
  ];

  dontUseCmakeConfigure = true;

  pythonImportsCheck = [ "exiv2" ];
}
