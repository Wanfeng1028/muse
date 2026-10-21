"""A1-07: the platform half of Runtime managing the bundled MySQL.

`mysql_lifecycle.py` holds the *decisions*; this module holds the parts that
touch the machine: where the bundled server lives, how it is invoked, and how
its credential is created and stored.

Everything here is built so the risky parts are provable without a running
server:

- **argv, never a shell string.** Process launch takes an argument list, so a
  path containing a space or a quote cannot turn into a second command. This is
  the same rule the rest of the repo follows for service commands.
- **The socket lives inside One Memory Home.** Nothing else on the machine can
  reach it, so it needs no password exposed to other processes.
- **The credential is generated, not shipped**, and written owner-only.

What is NOT verified here: actually starting a mysqld. That needs a real
server binary, and this machine has none (`mysqld`/`mysql`/Docker are all
absent). So the startup call is built and tested as a command, and the
platform work that remains is supplying the binary — which is blocked on the
distribution licence question, not on this code.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

#: Sub-paths of One Memory Home used by the bundled server.
BIN_DIR = "mysql/bin"
DATA_DIR = "mysql/data"
RUN_DIR = "mysql/run"
SOCKET_NAME = "mysql.sock"
CONFIG_NAME = "mysql.cnf"
CREDENTIAL_NAME = "mysql-credential"

#: Executables the bundled install must provide.
#:
#: `mysqld` runs the server; `mysqldump` takes the backup; `mysql` restores it.
#: Restore needs the client because a dump is SQL, and there is no server-side
#: "load this dump" command — so a backup that cannot be restored is not a
#: backup, and all three are required rather than optional.
REQUIRED_BINARIES = ("mysqld", "mysqldump", "mysql")

#: MySQL reserves options in a separate file; the socket must be short enough
#: for the platform's unix socket path limit, which is why it sits directly
#: under the run dir rather than under a deep tree.
MAX_SOCKET_PATH = 103


@dataclass(frozen=True)
class Layout:
    """Paths the bundled server uses, all under One Memory Home."""

    home: Path

    @property
    def bin_dir(self) -> Path:
        return self.home / Path(BIN_DIR)

    @property
    def data_dir(self) -> Path:
        return self.home / Path(DATA_DIR)

    @property
    def run_dir(self) -> Path:
        return self.home / Path(RUN_DIR)

    @property
    def socket(self) -> Path:
        return self.run_dir / SOCKET_NAME

    @property
    def config(self) -> Path:
        return self.run_dir / CONFIG_NAME

    @property
    def credential(self) -> Path:
        return self.home / CREDENTIAL_NAME

    def binary(self, name: str) -> Path:
        return self.bin_dir / name


def layout_for(home: str | Path) -> Layout:
    return Layout(Path(home))


def missing_binaries(layout: Layout) -> tuple[str, ...]:
    """Binaries the install must provide but does not."""
    return tuple(name for name in REQUIRED_BINARIES if not layout.binary(name).exists())


def install_ready(layout: Layout) -> tuple[bool, str]:
    """Whether the bundled server can be started, and why not if it cannot.

    Refusing before launch matters more than failing during it: a half-started
    server holding the data directory is worse than "not installed yet".
    """
    absent = missing_binaries(layout)
    if absent:
        return False, f"bundled MySQL binaries missing: {', '.join(absent)}"
    if not layout.data_dir.exists():
        return False, "data directory has not been initialized"
    if len(str(layout.socket)) > MAX_SOCKET_PATH:
        return False, "socket path exceeds the platform limit"
    return True, ""


def config_text(layout: Layout, *, port: int | None = None) -> str:
    """The server options file.

    `skip-networking` unless a port is explicitly wanted: the architecture's
    default is socket-only, so the server is unreachable off this machine and
    the credential never has to defend against a network caller.

    A `[client]` section repeats the socket for the *client* tools. Without it
    they fall back to the compiled-in default path while the server listens on
    ours, and `mysqldump`/`mysql` fail with `ERROR 2002` — so a backup would
    silently produce nothing rather than a wrong-but-visible result. Found by
    running the real 8.4.4 binaries, not by reading them; see
    `docs/contracts/mysql-distribution-probe.md`.
    """
    lines = [
        "[mysqld]",
        f"datadir = {layout.data_dir}",
        f"socket = {layout.socket}",
        # Only the local account can read the data directory.
        "user = ",
        "skip-networking" if port is None else f"port = {port}",
        # Do not let the server resolve names: nothing here dials out.
        "skip-name-resolve",
        # The client tools (`mysql`, `mysqldump`) read their own section.
        "[client]",
        f"socket = {layout.socket}",
    ]
    return "\n".join(line for line in lines if line != "user = ") + "\n"


def start_argv(layout: Layout, *, initialize: bool = False) -> list[str]:
    """The exact argument list used to launch (or initialize) the server.

    Returned as a list so the caller passes it straight to a spawn call. No
    shell is involved, so a path with a space or a quote cannot inject a second
    command.
    """
    binary = str(layout.binary("mysqld"))
    argv = [binary, f"--defaults-file={layout.config}"]
    if initialize:
        argv += ["--initialize-insecure", f"--datadir={layout.data_dir}"]
    return argv


def new_credential() -> str:
    """A generated password. Never shipped, never derived from the host."""
    return secrets.token_urlsafe(32)


def write_credential(layout: Layout, password: str) -> None:
    """Write the credential owner-only.

    The file mode is the control here: the socket is already unreachable off
    this machine, so the remaining exposure is another process on this machine
    reading the file.
    """
    layout.run_dir.mkdir(parents=True, exist_ok=True)
    path = layout.credential
    # Create with the final mode rather than chmod after write: a briefly
    # world-readable credential file is a real window on a shared machine.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, password.encode("utf-8"))
    finally:
        os.close(descriptor)


def read_credential(layout: Layout) -> str | None:
    """Read the stored credential, or None when there is none yet."""
    try:
        return layout.credential.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def client_credential_text(password: str) -> str:
    """A `[client]` option file holding the password.

    The password is deliberately NOT passed on the command line: an argv entry
    is visible to any process that can read the process table, and a credential
    leaked that way cannot be revoked by rewriting a file. Passing it through a
    separate defaults file keeps rotation a file write.
    """
    return f"[client]\npassword = {password}\n"


def backup_argv(
    layout: Layout,
    *,
    destination: Path,
    credential_file: Path,
) -> list[str]:
    """Argument list for a logical backup.

    `--single-transaction` so the dump is consistent without locking the
    tables: the app keeps importing while a backup runs, and a backup that
    stalls the product is one nobody takes.
    """
    return [
        str(layout.binary("mysqldump")),
        f"--defaults-file={layout.config}",
        f"--defaults-extra-file={credential_file}",
        "--all-databases",
        "--single-transaction",
        f"--result-file={destination}",
    ]


def restore_argv(layout: Layout, *, source: Path, credential_file: Path) -> list[str]:
    """Argument list for restoring a backup through the mysql client.

    Restore uses the client reading the dumped SQL from stdin, so the dump
    itself never has to be a shell redirection — the caller owns the file
    handle and the argument list stays fixed.
    """
    return [
        str(layout.binary("mysql")),
        f"--defaults-file={layout.config}",
        f"--defaults-extra-file={credential_file}",
        "--force",
    ]


#: The extended attribute macOS sets on anything fetched from the network.
#:
#: Gatekeeper refuses to run a binary carrying it until it is removed or the
#: user approves it in System Settings, which is why a downloaded `mysqld`
#: needs this cleared before the first launch.
QUARANTINE_ATTR = "com.apple.quarantine"


def quarantine_probe_argv(layout: Layout, name: str) -> list[str]:
    """Argument list that prints the quarantine attribute if it is present.

    Exists because whether the flag is set at all depends on *how* the file
    arrived, and the difference is not cosmetic — measured on macOS 26 (this
    machine), same download, two arrival paths:

    - **Fetched by a programmatic HTTP client** (`curl`, and equally Node's
      `https`/`fetch` or Python `urllib`, which is what Runtime will use):
      the extracted `mysqld` carries no quarantine attribute and **executes
      normally**. Verified: archive downloaded by `curl`, extracted, ran
      `mysqld --version` -> exit 0.
    - **Quarantine attribute present** (the path Safari/Chrome produce, and
      what `xattr -w` reproduces): the same binary is **killed by Gatekeeper**
      with SIGKILL (exit 137), and removing the attribute restores exit 0.

    So the correct posture is to *check* rather than assume either way: it is
    a no-op on the common path and the fix on the other. This probe is how the
    caller asks; a non-zero exit means "not quarantined", which is a pass.
    """
    return ["/usr/bin/xattr", "-p", QUARANTINE_ATTR, str(layout.binary(name))]


def dequarantine_argv(layout: Layout, name: str) -> list[str]:
    """Argument list clearing the quarantine flag from ONE binary.

    Three deliberate limits, each guarding a way this goes wrong:

    - **One binary, not `-r` on the tree.** Recursing over the extracted
      directory clears files we were never asked about, including any the
      archive happened to carry.
    - **One attribute, not `-c`.** `-c` removes every extended attribute, not
      just the quarantine flag; narrowing to the named attribute keeps the
      blast radius equal to the actual problem.
    - **argv, not a shell string.** Same rule as every other launch here.

    This is a local metadata operation, so it changes nothing about the
    licence. It is also *not* a notarization substitute: it stops the
    Gatekeeper prompt, but whether a notarized host may execute an unsigned
    child binary is a separate question that must be checked on real hardware.

    **The caller must treat a non-zero exit as success when the attribute was
    simply absent** — `xattr -d` fails on a file that was never quarantined,
    and that is the expected state for anything we downloaded ourselves. Run
    `quarantine_probe_argv` first, or ignore "no such xattr"; do not surface it
    as an install failure, because it is the normal case.
    """
    return [
        "/usr/bin/xattr",
        "-d",
        QUARANTINE_ATTR,
        str(layout.binary(name)),
    ]
