{ buildPythonPackage
, fetchFromGitHub
, cython
, libraw
, numpy
, nose
, pkgconf
, opencv4
}:

buildPythonPackage rec {
  pname = "rawpy";
  version = "0.17.0";

  src = fetchFromGitHub {
    owner = "letmaik";
    repo = "rawpy";
    rev = "v${version}";
    sha256 = "Hy7EEefF3p6TWq/z8ArbnIPaErpBQV1LG3anqpChMFE=";
  };

  nativeBuildInputs = [ pkgconf ];
  buildInputs = [ cython libraw ];
  propagatedBuildInputs = [ numpy ];
  checkInputs = [ nose opencv4 ];
}
