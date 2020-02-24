# My personal take on how to write my own Git

The code is based on the following three great resources:

- https://benhoyt.com/writings/pygit/
- https://kushagra.dev/blog/build-git-learn-git
- https://wyag.thb.lt

# Current state

The foundation is built and git cat already works:

This command is able to read, parse and decompress a real-world git command.
```sh
python gitpy.py cat-file blob bc0b50cebcdbe79d8b5cc86a138df029a92c54d2 
```