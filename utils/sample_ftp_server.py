#!/usr/bin/env python3
"""Local FTP server for testing FTP transfers against the OpenVDM sample data.

Serves the sample data's `ftp_source` and `ftp_destination` directories on
localhost for the FTP collection system and cruise data transfer types. It is
installed and run under Supervisor by `install-openvdm.sh` when the sample data
is installed, and is not meant for production use.

Two servers run in one process with the same accounts:

- the main port supports `MLSD`/`MLST`, so clients get exact modification times;
- the legacy port (main port + 1) disables `MLSD`/`MLST`, so clients fall back to
  `LIST`/`MDTM`, as with many older instrument FTP servers.

Accounts:

- the authenticated user (password read from `--password-file`) has its home at
  the sample data root. It can read everything there, and write only in
  `ftp_destination`, so writing to `ftp_source` is the read-only failure case.
- `anonymous` has read-only access to `ftp_source`.
"""

# pylint: disable=too-few-public-methods
import argparse
import logging
import os
import sys

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

READ_PERMS = 'elr'
WRITE_PERMS = 'elradfmwMT'


class SampleFTPHandler(FTPHandler):
    """FTP handler that reports missing directories like common FTP servers."""

    def ftp_MLSD(self, path):  # pylint: disable=invalid-name
        """List a directory, replying 550 if it doesn't exist.

        pyftpdlib replies 501 for a missing directory; vsftpd, ProFTPD and
        others reply 550, which is what rclone expects before creating it.

        Args:
            path: Filesystem path of the directory to list.

        Returns:
            The listed path on success, else None.
        """
        if not self.fs.lexists(path):
            self.respond('550 No such file or directory.')
            return None
        return super().ftp_MLSD(path)


class LegacyFTPHandler(SampleFTPHandler):
    """FTP handler without `MLSD`/`MLST`, like servers that only support `LIST`."""

    proto_cmds = {cmd: info for cmd, info in FTPHandler.proto_cmds.items()
                  if cmd not in ('MLSD', 'MLST')}


def build_authorizer(root: str, user: str, password: str) -> DummyAuthorizer:
    """Create the sample FTP accounts.

    Args:
        root: Sample data root directory, containing `ftp_source` and
            `ftp_destination`.
        user: Name of the authenticated user.
        password: Password of the authenticated user.

    Returns:
        An authorizer with the authenticated and anonymous accounts.
    """
    source = os.path.join(root, 'ftp_source')
    destination = os.path.join(root, 'ftp_destination')

    authorizer = DummyAuthorizer()
    authorizer.add_user(user, password, root, perm=READ_PERMS)
    authorizer.override_perm(user, destination, WRITE_PERMS, recursive=True)
    authorizer.add_anonymous(source, perm=READ_PERMS)
    return authorizer


def main() -> None:
    """Parse the command line and serve until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
    parser.add_argument('--root', required=True,
                        help='sample data root, containing ftp_source and ftp_destination')
    parser.add_argument('--user', required=True, help='authenticated user name')
    parser.add_argument('--password-file', required=True,
                        help='file containing the authenticated user\'s password')
    parser.add_argument('--host', default='127.0.0.1', help='address to listen on')
    parser.add_argument('--port', type=int, default=2121,
                        help='main port; the legacy (no MLSD) server uses port + 1')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')

    for directory in ('ftp_source', 'ftp_destination'):
        if not os.path.isdir(os.path.join(args.root, directory)):
            sys.exit(f'Missing directory: {os.path.join(args.root, directory)}')

    with open(args.password_file, encoding='utf-8') as password_file:
        password = password_file.read().strip()

    SampleFTPHandler.authorizer = build_authorizer(args.root, args.user, password)

    # Both servers share pyftpdlib's default IOLoop, so serving one serves both.
    FTPServer((args.host, args.port + 1), LegacyFTPHandler)
    server = FTPServer((args.host, args.port), SampleFTPHandler)
    server.serve_forever()


if __name__ == '__main__':
    main()
