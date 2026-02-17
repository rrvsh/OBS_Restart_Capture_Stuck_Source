{ config, lib, pkgs, ... }:

let
  cfg = config.services.obs-unflakify;
  inherit (lib) mkEnableOption mkIf mkOption types;
  pythonEnv = pkgs.python313.withPackages (ps: [ ps.websocket-client ]);
  defaultPackage = pkgs.writeShellApplication {
    name = "obs-display-monitor";
    runtimeInputs = [ pythonEnv ];
    text = ''
      exec python "${../obs_display_monitor.py}" "$@"
    '';
  };
  serviceScript = pkgs.writeShellApplication {
    name = "obs-unflakify-service";
    text = ''
      password_file=${lib.escapeShellArg (cfg.passwordFile or "")}
      password_value=${lib.escapeShellArg cfg.password}

      if [ -n "$password_file" ]; then
        if [ -r "$password_file" ]; then
          password="$(< "$password_file")"
          password_arg=(--password "$password")
        else
          echo "obs-unflakify: passwordFile not readable: $password_file" >&2
          exit 1
        fi
      elif [ -n "$password_value" ]; then
        password_arg=(--password "$password_value")
      else
        password_arg=()
      fi

      exec "${cfg.package}/bin/obs-display-monitor" \
        --source ${lib.escapeShellArg cfg.source} \
        --host ${lib.escapeShellArg cfg.host} \
        --port ${lib.escapeShellArg (toString cfg.port)} \
        --interval ${lib.escapeShellArg (toString cfg.interval)} \
        --threshold ${lib.escapeShellArg (toString cfg.threshold)} \
        --cooldown ${lib.escapeShellArg (toString cfg.cooldown)} \
        "${password_arg[@]}"
    '';
  };
in
{
  options.services.obs-unflakify = {
    enable = mkEnableOption "OBS display capture monitor";

    package = mkOption {
      type = types.package;
      default = defaultPackage;
      description = "Package that provides the obs-display-monitor executable.";
    };

    source = mkOption {
      type = types.str;
      default = "Safari";
      description = "OBS display capture source name.";
    };

    host = mkOption {
      type = types.str;
      default = "localhost";
      description = "OBS WebSocket host.";
    };

    port = mkOption {
      type = types.port;
      default = 4455;
      description = "OBS WebSocket port.";
    };

    password = mkOption {
      type = types.str;
      default = "";
      description = "OBS WebSocket password.";
    };

    passwordFile = mkOption {
      type = types.nullOr types.str;
      default = null;
      description = "Path to a file containing the OBS WebSocket password.";
    };

    interval = mkOption {
      type = types.float;
      default = 1.0;
      description = "Seconds between checks.";
    };

    threshold = mkOption {
      type = types.int;
      default = 1;
      description = "Identical frames before restart.";
    };

    cooldown = mkOption {
      type = types.int;
      default = 30;
      description = "Minimum seconds between restarts.";
    };
  };

  config = mkIf cfg.enable {
    launchd.user.agents.obs-unflakify = {
      serviceConfig = {
        ProgramArguments = [ "${serviceScript}/bin/obs-unflakify-service" ];
        KeepAlive = true;
        RunAtLoad = true;
        WorkingDirectory = "/tmp";
        StandardOutPath = "/tmp/obs-unflakify.log";
        StandardErrorPath = "/tmp/obs-unflakify.err";
      };
    };
  };
}
