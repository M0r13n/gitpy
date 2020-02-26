import argparse
from collections import OrderedDict
import configparser
import hashlib
import os
import re
import sys
import zlib

# CONSTANTS
ASCII_SPACE = b'\x20'
NULL_SEP = b'\x00'
GIT_OBJECTS = {}  # defined here, but filled later

# ALIASES

path_join = os.path.join
is_dir = os.path.isdir
path_exists = os.path.exists
md = os.makedirs


def _file_write(file_path: str, content: str, end: str = "\n", mode="w"):
    with open(file_path, mode) as f:
        f.write(content)
        f.write(end)


def _file_append(file_path: str, content: str, end: str = "\n"):
    with open(file_path, "a") as f:
        f.write(content)
        f.write(end)


def is_repo_base_dir(path):
    return is_dir(os.path.join(path, ".git"))


class GitObj(object):
    """
    A Git Object.

    Git objects are used to store:
        - files in VC (source code)
        - Commits
        - Tags

    Each object has a path that is the SHA-1 hash of it's content.
    The first two bytes of that hash are used as a directory and the remaining bytes as a file name.
    """

    __slots__ = (
        "repo",
        "data",
        "fmt"
    )

    def __init__(self, repo, data=None):
        if repo:
            assert isinstance(repo, GitRepository)
            self.repo = repo

        if data:
            self.data = self.deserialize(data)

    def serialize(self):
        raise NotImplementedError("Generic Git Object does not support serializing!")

    def deserialize(self, data):
        raise NotImplementedError("Generic Git Object does not support serializing!")

    def __len__(self):
        return str(len(self.serialize())).encode()

    @property
    def header(self):
        """
        Header structure:

        FMT + 0x20 + Length +  NULL_SEP + serialized data
        |commit 1086.tree|
        | 29ff16c9c14e265|
        |      ...       |
        """
        data = self.serialize()
        # don't use len to not serialize twice
        return self.fmt + ASCII_SPACE + str(len(data)).encode() + NULL_SEP + data

    def write(self, skip_write=False):
        """
        Write the git objects to its destination.
        The first two chars (bytes) are the folder name and the remaining part is the filename.
        ef9ff16c9c14e265 --> ef/9ff16c9c14e265

        Return the files hash
        """
        # Compute SHA-1 hash sumobject_write
        sha = hashlib.sha1(self.header).hexdigest()

        if not skip_write:
            # Compute path
            path = self.repo.repo_file("objects", sha[0:2], sha[2:], mkdir=True)
            with open(path, 'wb') as f:
                # Compress and write the header
                f.write(zlib.compress(self.header))
        return sha

    @staticmethod
    def hash(fd, fmt, repo=None):
        """
        Compute SHA-1 checksum of any file.

        :param fd: a open file descriptor
        :param fmt: the object type. [commit, blob, tag, tree]
        :param repo: optional repository instance. If provided the hash is stored inside the gitdir of that repo.
        :return:
        """
        raw = fd.read()
        if isinstance(fmt, str):
            fmt = fmt.encode('ascii')

        c = GIT_OBJECTS.get(fmt, None)
        if not c:
            raise ValueError(f"{fmt} is not a valid Git Object format.")

        c = c(repo, raw)
        return c.write(skip_write=not bool(repo))  # if repo is provided, actually write the the hash

    def __repr__(self):
        return f"<Basic GitObj>"


class GitCommit(GitObj):
    pass


class GitTree(GitObj):
    pass


class GitTag(GitObj):
    pass


class GitBlob(GitObj):
    """
    Data.

    Blobs store user content (source code).
    """

    def __init__(self, repo, data):
        self.fmt = b'blob'
        self.blob_data = None
        super().__init__(repo, data)

    def serialize(self):
        return self.blob_data

    def deserialize(self, data):
        self.blob_data = data
        return data


class GitRepository(object):
    """
    This class represents a git repository

    Worktree tracks the actual source-files and their location on the file system.

    Gitdir stores all data concerning git itself. Such data is not sourcecode.
    """

    worktree = None
    gitdir = None
    conf = None

    def __init__(self, path, force=False):
        self.worktree = path
        self.gitdir = path_join(path, ".git")  # assume that the .git lies at the top

        if not (force or is_dir(self.gitdir)):
            raise Exception(f"{path} is not a Git repository")

        # Read configuration inside git dir
        self.conf = configparser.ConfigParser()
        cf = self.repo_file("config")

        if cf and path_exists(cf):
            self.conf.read([cf])

        elif not force:
            raise Exception(f"{path} does not contain a config file.")

        if not force:
            vers = int(self.conf.get("core", "repositoryformatversion"))
            if vers != 0:
                raise Exception(f"{vers} is a Unsupported repositoryformatversion")

    def __str__(self):
        return f"<GitRepo:: Worktree='{self.worktree}' | Gitdir='{self.gitdir}'>"

    def __repr__(self):
        return "<GitRepo>"

    # UTILITY FUNCTIONS

    def repo_path(self, *paths):
        """
        Compute path under repo's gitdir.

        >>> GitRepository().repo_path(("some", "path"))
        /.git/some/path
        """
        return path_join(self.gitdir, *paths)

    def repo_file(self, *paths, mkdir=False):
        """
        Get a file inside the repo dir.

        >>> GitRepository().repo_file(("some", "path"))

        """
        if self.repo_dir(*paths[:-1], mkdir=mkdir):
            return self.repo_path(*paths)

    def repo_dir(self, *path, mkdir=False):
        """
        Compute path under repo's gitdir or create it if mkdir is True.

        >>> GitRepository().repo_dir("does", "not", "exist")
        None

        >>> GitRepository().repo_dir("does", "not", "exist", mkdir=True)
        .git/does/not/exist
        """
        path = self.repo_path(*path)

        if path_exists(path):
            if is_dir(path):
                return path
            else:
                raise Exception(f"{path} is not a directory")

        if mkdir:
            os.makedirs(path)
            return path
        else:
            return None

    # GIT FUNCTIONS
    @staticmethod
    def default_config():
        ret = configparser.ConfigParser()
        ret.add_section("core")
        ret.set("core", "repositoryformatversion", "0")  # Gitdir Version format, currently 0 is supported
        ret.set("core", "filemode", "false")  # enable/disable tracking of file mode changes in the work tree.
        ret.set("core", "bare", "false")  # enable/disable external worktree
        return ret

    @classmethod
    def find_repo(cls, path="."):
        path = os.path.realpath(path)  # absolute path

        if is_repo_base_dir(path):  # does it have a .git dir?
            return cls(path)

        # move into parent dir
        parent = os.path.realpath(os.path.join(path, ".."))

        # iteratively go to parent up to base dir
        while parent != path:
            if is_repo_base_dir(parent):
                return cls(parent)

            parent = os.path.realpath(os.path.join(path, ".."))

        return None

    @classmethod
    def create_repository(cls, dest="."):
        """
        Create a new repository and initialize it.
        :param dest: Destination path for gitdir.
        """
        repo = cls(path=dest, force=True)

        # Check that work tree is clear
        if path_exists(repo.worktree):
            if not is_dir(repo.worktree):
                raise Exception(f"{repo.worktree} exists, but is not a directory!")
        else:
            md(repo.worktree)

        # Create all necessary repository dirs
        assert (repo.repo_dir("branches", mkdir=True))
        assert (repo.repo_dir("objects", mkdir=True))
        assert (repo.repo_dir("refs", "tags", mkdir=True))
        assert (repo.repo_dir("refs", "heads", mkdir=True))

        # .git/description
        _file_write(repo.repo_file("description"),
                    "Unnamed repository; edit this file 'description' to name the repository.")

        # .git/HEAD
        _file_write(repo.repo_file("HEAD"), "ref: refs/heads/master")

        # .git/config
        with open(repo.repo_file("config"), "w") as f:
            config = repo.default_config()
            config.write(f)

        return repo

    def object_read(self, sha):
        """
        Read object object_id from Git repository repo.
        Return a GitObject whose exact type depends on the object.

        Typical header could look like:
        |commit 1086.tree|
        | 29ff16c9c14e265|
        |2b22f8b78bb08a5a|
        |      ...       |

        """

        path = self.repo_file("objects", sha[0:2], sha[2:])
        with open(path, "rb") as f:  # read as binary
            raw = zlib.decompress(f.read())

            # Object type = first chars until ASCII_SPACE (0x20)
            x = raw.find(ASCII_SPACE)
            fmt = raw[0:x]

            # Object type is followed by the file size
            # file size is separated with NULL_SEP (0x00)
            y = raw.find(NULL_SEP, x)
            size = int(raw[x:y].decode("ascii"))
            if size != len(raw) - y - 1:
                raise Exception(f"Malformed object {sha}: bad length")

            # Pick constructor
            c = GIT_OBJECTS.get(fmt)  # fmt is already binary
            if not c:
                raise ValueError(f"{fmt} is not a valid format!")

            # Call constructor and return object
            return c(self, raw[y + 1:])

    def object_find(self, name, fmt=None, follow=True):
        """
        ATM: Stub method without real functionality
        """
        return name

    def cat(self, obj_sha, fmt=None):
        """
        Read and write the content of a Git Object to STDOUT.

        """
        obj = self.object_read(self.object_find(obj_sha, fmt))
        sys.stdout.buffer.write(obj.serialize())  # write binary data which is not possible with print


# BRIDGE FUNCTIONS
def cmd_init(*args):
    return GitRepository.create_repository()


def cmd_cat_file(args):
    repo = GitRepository.find_repo()
    repo.cat(args.object, fmt=args.type.encode())


def cmd_hash(args):
    repo = GitRepository.find_repo() if args.write else None
    with open(args.path, 'rb') as f:
        sha_sum = GitObj.hash(f, args.type, repo)
        print(sha_sum)


# update already defined var with real data
GIT_OBJECTS.update({
    b'commit': GitCommit,
    b'tree': GitTree,
    b'tag': GitTag,
    b'blob': GitBlob,

})


def main(*args):
    # Main parser
    parser = argparse.ArgumentParser(description="The stupid content tracker")
    # Sub parsers
    subparsers = parser.add_subparsers(title="commands", dest="command")

    # GIT INIT
    argsp = subparsers.add_parser("init", help="Create/Initialize a new, empty repository.")
    argsp.add_argument("path",
                       metavar="directory",
                       nargs="?",
                       default=".",
                       help="Where is the repository located?")

    # GIT CAT: gitpy.py cat-file blob bc0b50cebcdbe79d8b5cc86a138df029a92c54d2
    argsp = subparsers.add_parser("cat-file",
                                  help="Provide content of repository objects")

    argsp.add_argument("type",
                       metavar="type",
                       choices=["blob", "commit", "tag", "tree"],
                       help="Specify the type")

    argsp.add_argument("object",
                       metavar="object",
                       help="The object to display")

    # GIT HASH: gitpy.py hash [-w] [-t TYPE] FILE
    argsp = subparsers.add_parser(
        "hash",
        help="Compute object ID and optionally creates a blob from a file")

    argsp.add_argument("-t",
                       metavar="type",
                       dest="type",
                       choices=["blob", "commit", "tag", "tree"],
                       default="blob",
                       help="Specify the type")

    argsp.add_argument("-w",
                       dest="write",
                       action="store_true",
                       help="Actually write the object into the database")

    argsp.add_argument("path",
                       help="Read object from <file>")

    # PARSE
    parsed_args = parser.parse_args(args)

    if parsed_args.command == "init":
        cmd_init(parsed_args)
    elif parsed_args.command == "cat-file":
        cmd_cat_file(parsed_args)
    elif parsed_args.command == "hash":
        cmd_hash(parsed_args)
