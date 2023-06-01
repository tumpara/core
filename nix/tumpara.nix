{
  python,
  exiftool,
}:
python.pkgs.buildPythonPackage rec {
  pname = "tumpara";
  version = "0.1.0";

  src = ./..;

  postPatch = ''
    substituteInPlace "tumpara/settings/base.py" \
    	--replace "/usr/bin/exiftool" "${exiftool}/bin/exiftool"
  '';

  propagatedBuildInputs = with python.pkgs; [
    blurhash-python
    dateutil
    django
    django-stubs
    django-cors-headers
    inotifyrecursive
    pillow-avif-plugin
    psycopg2
    rawpy
    strawberry-graphql
  ];
  checkInputs = with python.pkgs; [
    freezegun
    hypothesis
    mypy
    parameterized
    pylint
    pylint-django
    pytestCheckHook
    pytest-cov
    pytest-django
    pytest-mypy-plugins
    pytest-subtests
    pyyaml
    selenium
    types-freezegun
    types-pillow
    types-dateutil
    types-setuptools
    types-six
    types-toml
    types-typed-ast
  ];

  pythonImportsCheck = ["tumpara"];

  passthru = {
    inherit checkInputs;
  };
}
