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
	version = "0.18.1";

	src = fetchFromGitHub {
		owner = "letmaik";
		repo = "rawpy";
		rev = "v${version}";
		sha256 = "ErQSVtv+pxKIgqCPrh74PbuWv4BKwqhLlBxtljmTCFM=";
	};

	nativeBuildInputs = [ pkgconf ];
	buildInputs = [ cython libraw ];
	propagatedBuildInputs = [ numpy ];
	checkInputs = [ nose opencv4 ];

	pythonImportsCheck = [ "rawpy" ];
}
