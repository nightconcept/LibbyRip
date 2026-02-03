{
  pkgs,
  lib,
  config,
  inputs,
  ...
}: {
  packages = [
    pkgs.ffmpeg
    pkgs.just
  ];

  languages.python = {
    enable = true;
    package = pkgs.python313;
  };
}
