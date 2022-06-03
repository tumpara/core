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
	version = "1.11.0";

	# https://pypi.org/project/django-stubs/
	src = fetchPypi {
		inherit pname version;
		sha256 = "EaSqCU09oBCNJoOG39C5pb9z/hq1kZtaKSYHZxMpvEs=";
	};

	propagatedBuildInputs = [
		django django-stubs-ext mypy typing-extensions types-pytz types-PyYAML
	];

	pythonImportsCheck = [ "django-stubs" ];
}
