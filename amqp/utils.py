from __future__ import absolute_import

try:
    import fcntl
except ImportError:
    fcntl = None   # noqa


try:
    from os import set_cloexec  # Python 3.4?
except ImportError:
    def set_cloexec(fd, cloexec):
        try:
            FD_CLOEXEC = fcntl.FD_CLOEXEC
        except AttributeError:
            raise NotImplementedError(
                'close-on-exec flag not supported on this platform',
            )
        flags = fcntl.fcntl(fd, fcntl.F_GETFD)
        if cloexec:
            flags |= FD_CLOEXEC
        else:
            flags &= ~FD_CLOEXEC
        return fcntl.fcntl(fd, fcntl.F_SETFD, flags)
