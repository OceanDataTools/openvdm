import hashlib

def hashlib_md5():
    try:
        return hashlib.md5(usedforsecurity=False)
    except TypeError:
        # usedforsecurity is not supported
        return hashlib.md5()