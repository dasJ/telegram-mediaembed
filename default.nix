{ pkgs ? import <nixpkgs> {} }: pkgs.stdenv.mkDerivation {
  name = "mediaembed-bot";

  buildInputs = with pkgs; [
    (python3.withPackages (ps: with ps; [
      wheel
      pkgs.python3Packages.pyTelegramBotAPI
      requests
    ]))
    ffmpeg
    youtube-dl
  ];
}
