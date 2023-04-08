{config, lib, ...}:

let
	inherit (lib) types;
	defaultUser = "tumpara";
	cfg = config.services.tumpara;

	mkPythonValueString = v:
		if true == v then "True"
		else if false == v then "False"
		else if null == v then "None"
		else if lib.isString v then "\"${lib.strings.escape ["\""] v}\""
		else if lib.isList then "[${lib.concatMapStringsSep "," mkPythonValueString v}]"
		else if lib.isAttrs then mkPythonKeyValue v
		else lib.mkValueStringDefault {} v;
	mkPythonKeyValue = lib.mkKeyValueDefault {
		mkValueString = mkPythonValueString;
	} ":";

	semanticConfType = with types;
		let
			confAtom = nullOr
				(oneOf [
					bool
					int
					float
					str
					path
				]) // {
				description = "Configuration value (null, bool, int, float, str or path)";
			};
		in
		attrsOf (either confAtom (listOf confAtom));
in
{
	options.services.tumpara = {
		enable = lib.mkEnableOption (lib.mdDoc "Tumpara");

		package = lib.mkOption {
			default = pkgs.tumpara;
			defaultText = lib.literalExpression "pkgs.tumpara";
			type = types.package;
			description = lib.mdDoc "Tumpara package to use.";
		};

		user = lib.mkOption {
			type = types.str;
			default = defaultUser;
			description = lib.mdDoc ''
				User under which the service should run. If this is the default value,
				the user will be created, with the specified group as the primary
				group.
			'';
		};

		group = lib.mkOption {
			type = types.str;
			default = defaultUser;
			description = lib.mdDoc ''
				Group under which the service should run. If this is the default value,
				the group will be created.
			'';
		};

		secretKeyFile = lib.mkOption {
      type = types.str;
      default = "/var/lib/tumpara/secret_key";
		};

		settings = lib.mkOption {
			freeformType = semanticConfType;

			defaultDatabase = {};

		};
	};
}
