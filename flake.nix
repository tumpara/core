{
	description = "Tumpara server";

	inputs.nixpkgs.url = "nixpkgs/1710ed1f6f8ceb75cf7d1cf55ee0cc21760e1c7a";
	inputs.flake-utils.url = "github:numtide/flake-utils";

	outputs = { self, nixpkgs, flake-utils }:
		(flake-utils.lib.eachDefaultSystem (system:
			let
				pkgs = import nixpkgs { inherit system; };

				python = pkgs.python310.override {
					packageOverrides = self: super: {
						django = (super.django_4.override {
							withGdal = true;
						}).overridePythonAttrs (oldAttrs: {
							patches = oldAttrs.patches ++ [
								(pkgs.substituteAll {
									src = ./nix/django_4_set_spatialite_lib.patch;
									libspatialite = pkgs.libspatialite;
									extension = pkgs.stdenv.hostPlatform.extensions.sharedLibrary;
								})
							];
							postPatch = ''
								sed -ie 's,lib_path = ""/nix/store,lib_path = "/nix/store,g' django/contrib/gis/gdal/libgdal.py
							'';
						});

						django-stubs = super.django-stubs.overridePythonAttrs (oldAttrs: rec {
							version = "1.13.1";
							src = self.fetchPypi {
								inherit (oldAttrs) pname;
								inherit version;
								sha256 = "vMYYujU9q8VA2YK52sHVoZIWUvj8KhNlPVRaV9XjzA8=";
							};
						});

						django-stubs-ext = super.django-stubs-ext.overridePythonAttrs (oldAttrs: rec {
							version = "0.7.0";
							src = self.fetchPypi {
								inherit (oldAttrs) pname;
								inherit version;
								sha256 = "T9jNvGjRpCHyG7fg2edtUPaktQTTULp4ZAXa9TbpDCE=";
							};
						});

						strawberry-graphql = super.strawberry-graphql.overridePythonAttrs (oldAttrs: rec {
							version = "0.151.1";
							src = pkgs.fetchFromGitHub {
								owner = "strawberry-graphql";
								repo = "strawberry";
								rev = version;
								sha256 = "YzErCBocNeouCsyW58rKwxFbmsSFyuxZK2DqngRfgPM=";
							};
							# Strip down to only the essential dependencies as well as the
							# ones we need:
							# https://github.com/strawberry-graphql/strawberry/blob/0.142.0/pyproject.toml#L34-L57
							propagatedBuildInputs = [
								self.django
								self.asgiref
								self.backports-cached-property
								self.channels
								self.click
								self.graphql-core
								self.libcst
								self.pygments
								self.python-dateutil
								self.python-multipart
								self.rich
								self.typing-extensions
							];
						});

						# All the remaining packages in the overlay are ones that are not
						# yet ported in the official nixpkgs repo:

						# https://github.com/fdintino/pillow-avif-plugin
						pillow-avif-plugin = self.callPackage ./nix/python-packages/pillow-avif-plugin.nix { };
						# https://pypi.org/project/pygments-graphql/
						pygments-graphql = self.callPackage ./nix/python-packages/pygments-graphql.nix { };
						# https://pypi.org/project/exiv2
						python-exiv2 = self.callPackage ./nix/python-packages/python-exiv2.nix {
						  inherit (pkgs) pkg-config;
						};
						# https://pypi.org/project/rawpy/
						rawpy = self.callPackage ./nix/python-packages/rawpy.nix { };
						# https://pypi.org/project/types-Pillow/
						types-pillow = self.callPackage ./nix/python-packages/types-pillow.nix { };
						# https://pypi.org/project/types-six/
						types-six = self.callPackage ./nix/python-packages/types-six.nix { };
					};
				};

				runtimeDependencies = pythonPackages: with pythonPackages; [
					blurhash
					dateutil
					django
					django-stubs
					django-cors-headers
					inotifyrecursive
					pillow
					pillow-avif-plugin
					psycopg2
					python-exiv2
					rawpy
					strawberry-graphql
				];

				testDependencies = pythonPackages: with pythonPackages; [
					freezegun
					hypothesis
					mypy
					parameterized
					pylint
					pylint-django
					pytest
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

				developmentDependencies = pythonPackages: with pythonPackages; [
					black
					isort
				];

				documentationDependencies = pythonPackages: with pythonPackages; [
					furo
					pygments-graphql
					sphinx
				];

				allDependencies = pythonPackages:
					(runtimeDependencies pythonPackages)
					++ (testDependencies pythonPackages)
					++ (developmentDependencies pythonPackages)
					++ (documentationDependencies pythonPackages);
			in
			rec {
				packages = {
					#          tumpara = pkgs.python39Packages.buildPythonApplication rec {
					#            pname = "tumpara";
					#            version = "0.1.0";
					#            src = ./.;
					#            propagatedBuildInputs = runtimeDependencies pkgs.python39.pkgs;
					#            pythonImportsCheck = [ "tumpara" ];
					#          };
					tumpara = python.withPackages runtimeDependencies;

					libjpeg = pkgs.libjpeg;

					devEnv = python.withPackages allDependencies;
				};
				defaultPackage = packages.tumpara;

				apps = {
					tumpara = packages.tumpara;
				};
				defaultApp = apps.tumpara;

				devShell = packages.devEnv.env;
			}
		));
}
