class Mount(object):
    """
    Abstraction around /proc/mounts
    """
    DEVICE = 0
    MOUNT_POINT = 1
    FS_TYPE = 2
    OPTIONS = 3

    @staticmethod
    def mounted_filesystems():
        """
            Get all currently mounted filesystems from /proc/mounts
            :return: generator of mount info arrays: the constants can be utilized
            to get specific field information
        """
        with open('/proc/mounts', 'r') as proc_mount:
            for mounted_fs in proc_mount.readlines():
                yield mounted_fs.split(' ')