import os
import errno
import logging

def create_directories(directorylist):
    """
    Create the directories in the provide directory list
    """

    reasons = []
    for directory in directorylist:
        try:
            os.makedirs(directory)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                logging.error("Unable to create directory: %s", directory)
                reasons.append("Unable to create directory: %s", directory)

    if len(reasons) > 0:
        return {'verdict': False, 'reason': '\n'.join(reasons)}

    return {'verdict': True}


def lockdown_directory(base_dir, exempt_dir):
    """
    Lockdown permissions on the base directory, skip the exempt directory if present
    """

    dir_contents = [ os.path.join(base_dir,f) for f in os.listdir(base_dir)]
    files = filter(os.path.isfile, dir_contents)
    for file in files:
        os.chmod(file, 0o600)

    directories = filter(os.path.isdir, dir_contents)
    for directory in directories:
        if not directory == exempt_dir:
            os.chmod(directory, 0o700)
