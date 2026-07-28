# from zk import ZK


# class PyZKConnector:

#     def connect(self, device):
#         pass

#     def disconnect(self, conn):
#         pass

#     def get_device_info(self, conn):
#         pass

#     def get_users(self, conn):
#         pass

#     def get_attendance(self, conn):
#         pass


from zk import ZK


class PyZKConnector:

    def connect(self, device):

        zk = ZK(
            device.ip_address,
            port=device.port,
            timeout=10,
            password=device.communication_password or 0
        )

        conn = zk.connect()

        conn.disable_device()

        return conn

    def disconnect(self, conn):

        if conn:
            conn.enable_device()
            conn.disconnect()