{
  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  outputs =
    inputs:
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
