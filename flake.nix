{
  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  outputs =
    inputs@{ self, ... }:
    let
      inherit (inputs.nixpkgs.lib) genAttrs;
      forEachSupportedSystem =
        f:
        genAttrs
          [
            "x86_64-linux"
            "aarch64-linux"
            "x86_64-darwin"
            "aarch64-darwin"
          ]
          (
            system:
            f {
              inherit system;
              pkgs = import inputs.nixpkgs { inherit system; };
            }
          );
    in
    {
      packages = forEachSupportedSystem (
        { pkgs, ... }:
        let
          pythonEnv = pkgs.python313.withPackages (ps: [ ps.websocket-client ]);
          obsDisplayMonitor = pkgs.writeShellApplication {
            name = "obs-display-monitor";
            runtimeInputs = [ pythonEnv ];
            text = ''
              exec python "${./obs_display_monitor.py}" "$@"
            '';
          };
        in
        {
          obs-display-monitor = obsDisplayMonitor;
          default = obsDisplayMonitor;
        }
      );

      apps = forEachSupportedSystem (
        { system, ... }:
        {
          obs-display-monitor = {
            type = "app";
            program = "${self.packages.${system}.obs-display-monitor}/bin/obs-display-monitor";
          };
          default = self.apps.${system}.obs-display-monitor;
        }
      );

      darwinModules.obs-unflakify = import ./nix/obs-unflakify.nix;

      devShells = forEachSupportedSystem (
        { pkgs, ... }:
        {
          default = pkgs.mkShellNoCC {
            packages = with pkgs; [
              python313
              python313Packages.websocket-client
            ];
          };
        }
      );
    };
}
