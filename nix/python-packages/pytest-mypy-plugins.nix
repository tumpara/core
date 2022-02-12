{ buildPythonPackage
, fetchFromGitHub
, chevron
, decorator
, mypy
, pytest
, pytestCheckHook
, pyyaml
, regex
}:

buildPythonPackage rec {
  pname = "pytest-mypy-plugins";
  version = "1.9.3";

  src = fetchFromGitHub {
    owner = "typeddjango";
    repo = "pytest-mypy-plugins";
    rev = version;
    sha256 = "4hG3atahb+dH2dRGAxguJW3vvEf0TUGUJ3G5ymrf3Vg=";
  };

  propagatedBuildInputs = [ chevron decorator mypy pytest pyyaml regex ];
  checkInputs = [ mypy pytestCheckHook ];
}
