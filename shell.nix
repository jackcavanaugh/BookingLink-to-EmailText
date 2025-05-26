{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python311
    python311Packages.flask
    python311Packages.requests
    python311Packages.beautifulsoup4
    python311Packages.selenium
    python311Packages.pytz
    python311Packages.gunicorn
  ];

  shellHook = ''
    export PYTHONPATH=$PWD:$PYTHONPATH
    echo "Python development environment is ready!"
  '';
} 