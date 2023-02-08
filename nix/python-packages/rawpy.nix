{ buildPythonPackage
, fetchFromGitHub
, cython
, libraw
, nose
, pkgconf
, opencv4

, numpy
}:

buildPythonPackage rec {
	pname = "rawpy";
	version = "0.18.0";

	src = fetchFromGitHub {
		owner = "letmaik";
		repo = "rawpy";
		rev = "v${version}";
		sha256 = "vSDzp/ttRloz3E3y2X87VMfQ+Wh+r4SAE5mXlDFmRqE=";
	};

	nativeBuildInputs = [ pkgconf ];
	buildInputs = [ cython libraw ];
	propagatedBuildInputs = [ numpy ];
	checkInputs = [ nose opencv4 ];

	pythonImportsCheck = [ "rawpy" ];
}
