{ buildPythonPackage
, fetchPypi
, django
, django-stubs-ext
, mypy
, toml
, typing-extensions
, types-pytz
, types-PyYAML
}:

buildPythonPackage rec {
	pname = "django-stubs";
	version = "1.10.1";

	# https://pypi.org/project/django-stubs/
	src = fetchPypi {
		inherit pname version;
		sha256 = "LsIfwU26OSFW4OyEOOGGPIbdspXxyNiO7Nfg4El3yEM=";
	};

	propagatedBuildInputs = [
		django django-stubs-ext mypy typing-extensions types-pytz types-PyYAML
	];

	pythonImportsCheck = [ "django-stubs" ];
}
