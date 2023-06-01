{
  lib,
  buildPythonPackage,
  fetchFromGitHub,
  libffi,
  cffi,
  pillow,
  six,
  setuptools,
  setuptools-scm,
  pytestCheckHook,
}:
buildPythonPackage rec {
  pname = "blurhash";
  version = "1.2.0";

  src = fetchFromGitHub {
    owner = "woltapp";
    repo = "blurhash-python";
    rev = "v${version}";
    sha256 = "a7c06KtzuPtizVTNG110qYTa9ip4n4Fb7+1RoSPqEQ0=";
  };

  postPatch = ''
    sed -i '/^addopts/d' setup.cfg
  '';

  SETUPTOOLS_SCM_PRETEND_VERSION = version;

  nativeBuildInputs = [
    setuptools
    setuptools-scm
  ];
  buildInputs = [
    libffi
  ];
  propagatedBuildInputs = [
    cffi
    six
    pillow
  ];
  checkInputs = [pytestCheckHook];

  pythonImportsCheck = ["blurhash"];
}
