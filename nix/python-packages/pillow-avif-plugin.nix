{ buildPythonPackage
, fetchFromGitHub
, cython
, libavif
, libjpeg
, pkgconf
, pytestCheckHook

, pillow
}:

buildPythonPackage rec {
	pname = "pillow-avif-plugin";
	version = "1.3.1";

	src = fetchFromGitHub {
		owner = "fdintino";
		repo = "pillow-avif-plugin";
		rev = "v${version}";
		sha256 = "vmVu19WqThe9T4QXTJ9VSqSvQwxTKcuPBUC6An8q0oU=";
	};

	nativeBuildInputs = [ pkgconf ];
	buildInputs = [ cython libavif libjpeg ];
	propagatedBuildInputs = [ pillow ];

	# This currently fails:
	#   ImportError: /nix/store/cgk8nbxafs8l1igpyvnx0nrymv5hbabk-libyuv-1787/lib/libyuv.so: undefined symbol: jpeg_resync_to_restart
  doCheck = false;
#	checkInputs = [ pytestCheckHook ];
#	pythonImportsCheck = [ "pillow_avif" ];
}
