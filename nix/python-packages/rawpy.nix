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
  version = "0.17.1";

  src = fetchFromGitHub {
    owner = "letmaik";
    repo = "rawpy";
    rev = "v${version}";
    sha256 = "gAl+bKPdWrgJxQ7h6WJV8jFTFld4cVFoEyvX24XYgK8=";
  };

  nativeBuildInputs = [ pkgconf ];
  buildInputs = [ cython libraw ];
  propagatedBuildInputs = [ numpy ];
  checkInputs = [ nose opencv4 ];
}
