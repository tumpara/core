{
  description = "Tumpara server";

  inputs.nixpkgs.url = "nixpkgs/nixpkgs-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }: (flake-utils.lib.eachDefaultSystem (
    system: let
      pkgs = import nixpkgs {inherit system;};

      python = pkgs.python311.override {
        packageOverrides = self: super: {
          django =
            (super.django_4.override {
              withGdal = true;
            })
            .overridePythonAttrs (oldAttrs: {
              patches =
                oldAttrs.patches
                ++ [
                  (pkgs.substituteAll {
                    src = ./nix/django_4_set_spatialite_lib.patch;
                    libspatialite = pkgs.libspatialite;
                    extension = pkgs.stdenv.hostPlatform.extensions.sharedLibrary;
                  })
                ];
            });

          strawberry-graphql = super.strawberry-graphql.overridePythonAttrs (oldAttrs: rec {
            version = "0.180.1";
            src = pkgs.fetchFromGitHub {
              owner = "strawberry-graphql";
              repo = "strawberry";
              rev = version;
              sha256 = "w4i7HS6cYsTMRigCd8L2R8xpC6S6K8Mjp42TElawYgE=";
            };
            # Strip down to only the essential dependencies as well as the
            # ones we need:
            # https://github.com/strawberry-graphql/strawberry/blob/0.180.0/pyproject.toml#L36-L64
            propagatedBuildInputs = [
              self.django
              self.asgiref
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
            disabledTestPaths =
              oldAttrs.disabledTestPaths
              ++ [
                # The OpenTelemetry dependency isn't packaged yet and we don't
                # use it anyway.
                "tests/extensions/test_custom_objects_for_setting_attribute.py"
                "tests/schema/extensions/test_opentelemetry.py"
              ];
          });

          # All the remaining packages in the overlay are ones that are not
          # yet ported in the official nixpkgs repo:

          # https://pypi.org/project/blurhash-python/
          # https://github.com/woltapp/blurhash-python
          blurhash-python = self.callPackage ./nix/python-packages/blurhash-python.nix {};
          # https://github.com/fdintino/pillow-avif-plugin
          pillow-avif-plugin = self.callPackage ./nix/python-packages/pillow-avif-plugin.nix {};
          # https://pypi.org/project/pygments-graphql/
          pygments-graphql = self.callPackage ./nix/python-packages/pygments-graphql.nix {};
          # https://pypi.org/project/rawpy/
          rawpy = self.callPackage ./nix/python-packages/rawpy.nix {};
          # https://pypi.org/project/types-six/
          types-six = self.callPackage ./nix/python-packages/types-six.nix {};
        };
      };

      developmentDependencies = with python.pkgs; [
        black
        isort
        pytest
        python-lsp-server
        python-lsp-server.optional-dependencies.all
      ];
      documentationDependencies = with python.pkgs; [
        furo
        pygments-graphql
        sphinx
      ];
      productionDependencies = with python.pkgs; [
        gunicorn
      ];
    in rec {
      packages = {
        tumpara = pkgs.callPackage ./nix/tumpara.nix {inherit python;};

        exiftool = pkgs.exiftool;
        postgresql = pkgs.postgresql.withPackages (ps:
          with ps; [
            postgis
          ]);

        devEnv = pkgs.buildEnv {
          name = "tumpara-dev";
          paths = with packages; [
            exiftool
            postgresql
            (python.withPackages
              (_: (packages.tumpara.propagatedBuildInputs
                ++ packages.tumpara.checkInputs
                ++ developmentDependencies
                ++ documentationDependencies
                ++ productionDependencies)))
          ];
        };
      };
      defaultPackage = packages.tumpara;

      apps = {
        tumpara = {
          name = "tumpara";
          program = "${packages.tumpara}/bin/tumpara";
        };
      };
      defaultApp = apps.tumpara;

      devShells.default = pkgs.mkShell {
        name = "tumpara-dev-shell";
        packages = [packages.devEnv];
      };
    }
  ));
}
