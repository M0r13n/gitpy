# My personal take on how to write my own Git

The code is based on the following three great resources:

- https://benhoyt.com/writings/pygit/
- https://kushagra.dev/blog/build-git-learn-git
- https://wyag.thb.lt

# Current state

The foundation is built and git cat already works:

#### Commands
**Git cat**
```sh
python gitpy.py cat-file blob bc0b50cebcdbe79d8b5cc86a138df029a92c54d2 
```

**Git hash**
```sh
python gitpy.py hash lib.py
```