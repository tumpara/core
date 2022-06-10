{
	description = "Tumpara server";

	inputs.nixpkgs.url = "nixpkgs/nixos-unstable";
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

						# All the remaining packages in the overlay are ones that are not
						# yet ported in the official nixpkgs repo:

						backports_cached-property = self.callPackage ./nix/python-packages/backports_cached-property.nix { };
						django-stubs = self.callPackage ./nix/python-packages/django-stubs.nix { };
						django-stubs-ext = self.callPackage ./nix/python-packages/django-stubs-ext.nix { };
						pygments-graphql = self.callPackage ./nix/python-packages/pygments-graphql.nix { };
						rawpy = self.callPackage ./nix/python-packages/rawpy.nix { };
						singledispatch = self.callPackage ./nix/python-packages/singledispatch.nix { };
						strawberry-graphql = self.callPackage ./nix/python-packages/strawberry-graphql.nix { };
						types-pillow = self.callPackage ./nix/python-packages/types-pillow.nix { };
						types-PyYAML = self.callPackage ./nix/python-packages/types-pyyaml.nix { };
						types-selenium = self.callPackage ./nix/python-packages/types-selenium.nix { };
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
					psycopg2
					py3exiv2
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
