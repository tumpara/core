{ buildPythonPackage
, fetchFromGitHub
, substituteAll
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

	postPatch = ''
		substituteInPlace "tests/test_file_avif.py" \
			--replace "12.0" "13.0"
	'';

	nativeBuildInputs = [ pkgconf ];
	buildInputs = [ cython libavif libjpeg ];
	propagatedBuildInputs = [ pillow ];

	NIX_CFLAGS_LINK = [ "-ljpeg" ];

	checkInputs = [ pytestCheckHook ];
	pythonImportsCheck = [ "pillow_avif" ];
}
