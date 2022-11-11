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
	version = "0.17.3";

	src = fetchFromGitHub {
		owner = "letmaik";
		repo = "rawpy";
		rev = "v${version}";
		sha256 = "i4OTw8rkL4H57JbrR6WlYXpXucsMLd5FRV6asS0vit0=";
	};

	nativeBuildInputs = [ pkgconf ];
	buildInputs = [ cython libraw ];
	propagatedBuildInputs = [ numpy ];
	checkInputs = [ nose opencv4 ];
}
